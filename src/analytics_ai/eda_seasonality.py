"""Sazonalidade por produto (análise complementar às Etapas 1 e 2 do plano de previsão).

Mede, para cada produto (vendas somadas nas lojas), se a demanda repete um
padrão de mês do ano. Tudo é pandas puro: o notebook faz uma única consulta
ao Databricks (demanda mensal por produto) e o resto roda localmente.

Método (mesma ideia do índice sazonal de int_high_season_months, mas por
produto e descontando a tendência):

1. Tendência: média móvel centrada de 12 meses (2x12).
2. Razão = venda do mês ÷ tendência. 1,0 = mês típico; 1,5 = 50% acima.
3. Índice sazonal: média das razões de cada mês do ano ÷ média dos 12 meses.
4. Força sazonal: fração da variação das razões explicada só pelo mês do ano
   (eta ao quadrado, de 0 a 1).
5. Acaso: embaralha as razões entre os meses e vê quantas vezes o embaralhado
   chega a uma força igual ou maior (teste de permutação).
6. Consistência: o padrão de um ano se parece com o padrão dos outros anos?

No fim do módulo há funções pequenas sobre a série mensal de um único produto
(unidades por ano × mês, alta temporada × resto, perfil em torno do pico).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import false_discovery_control

MIN_HISTORY_MONTHS = 36
N_PERMUTATIONS = 500
SIGNIFICANCE = 0.05
# Alta temporada náutica (dim_date.is_high_season): novembro a abril.
HIGH_SEASON_MONTHS = (11, 12, 1, 2, 3, 4)
_METRIC_COLUMNS = (
    "n_months",
    "total_demand",
    "mean_demand",
    "strength",
    "null_mean",
    "p_value",
    "consistency",
    "peak_month",
    "trough_month",
    "peak_index",
    "trough_index",
    "amplitude",
    "corr_global",
)
MONTH_LABELS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def product_month_matrix(
    monthly: pd.DataFrame,
    id_col: str = "sk_product",
    date_col: str = "month",
    value_col: str = "demand",
) -> pd.DataFrame:
    """Matriz mês × produto densa: meses sem venda viram 0 depois do primeiro mês do produto.

    Antes do primeiro mês com registro o valor fica NaN (o produto ainda não
    existia, não é "venda zero").

    Args:
        monthly: Uma linha por produto × mês (só meses completos).
        id_col: Coluna do produto.
        date_col: Coluna do primeiro dia do mês.
        value_col: Coluna de demanda.

    Returns:
        DataFrame com índice mensal contínuo e uma coluna por produto.
    """
    wide = monthly.pivot_table(index=date_col, columns=id_col, values=value_col, aggfunc="sum")
    wide.index = pd.to_datetime(wide.index)
    wide = wide.reindex(pd.date_range(wide.index.min(), wide.index.max(), freq="MS"))
    first_month = wide.notna().idxmax()
    started = wide.index.to_numpy()[:, None] >= first_month.to_numpy()[None, :]
    return wide.mask(started & wide.isna(), 0.0)


def seasonal_ratios(y: pd.Series) -> pd.Series:
    """Venda ÷ tendência (média móvel centrada 2x12); perde 6 meses em cada ponta."""
    trend = y.rolling(12).mean().rolling(2).mean().shift(-6)
    return (y / trend.where(trend > 0)).dropna()


def seasonal_index(ratios: pd.Series) -> pd.Series:
    """Índice sazonal por mês do ano (1–12): média das razões ÷ média dos 12 meses."""
    by_month = ratios.groupby(ratios.index.month).mean().reindex(range(1, 13))
    return by_month / by_month.mean()


def _strength_and_null(ratios: pd.Series, n_permutations: int, rng: np.random.Generator):
    """Força sazonal observada, média esperada ao acaso e p-valor de permutação."""
    values = ratios.to_numpy(dtype=float)
    months = ratios.index.month.to_numpy() - 1
    one_hot = np.eye(12)[months]
    counts = one_hot.sum(axis=0)
    seen = counts > 0
    total_ss = ((values - values.mean()) ** 2).sum()
    if total_ss == 0:
        return np.nan, np.nan, np.nan, np.array([])

    def strength(matrix: np.ndarray) -> np.ndarray:
        means = (matrix @ one_hot)[:, seen] / counts[seen]
        between = (counts[seen] * (means - matrix.mean(axis=1, keepdims=True)) ** 2).sum(axis=1)
        return between / total_ss

    observed = float(strength(values[None, :])[0])
    shuffled = strength(rng.permuted(np.tile(values, (n_permutations, 1)), axis=1))
    p_value = float((1 + (shuffled >= observed).sum()) / (1 + n_permutations))
    return observed, float(shuffled.mean()), p_value, shuffled


def year_consistency(ratios: pd.Series, min_months: int = 6) -> float:
    """Média, por ano, da correlação entre o ano e o padrão médio dos outros anos.

    Perto de 1 = todo ano repete o mesmo desenho; perto de 0 = cada ano é
    diferente (o "padrão" médio é só coincidência).
    """
    correlations = []
    for year in sorted(set(ratios.index.year)):
        this_year = ratios[ratios.index.year == year]
        others = ratios[ratios.index.year != year]
        if len(this_year) < min_months or others.empty:
            continue
        profile = others.groupby(others.index.month).mean()
        pair = pd.concat([this_year.groupby(this_year.index.month).mean(), profile], axis=1).dropna()
        if len(pair) >= min_months and pair.iloc[:, 0].std() > 0 and pair.iloc[:, 1].std() > 0:
            correlations.append(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
    return float(np.mean(correlations)) if correlations else np.nan


def seasonality_metrics(
    y: pd.Series,
    global_index: pd.Series | None = None,
    n_permutations: int = N_PERMUTATIONS,
    seed: int = 0,
) -> dict | None:
    """Todas as medidas de sazonalidade de uma série mensal de um produto.

    Args:
        y: Demanda mensal do produto (índice mensal contínuo, sem NaN).
        global_index: Índice sazonal de todos os produtos, para comparar.
        n_permutations: Embaralhamentos do teste de acaso.
        seed: Semente do sorteio (resultado reproduzível).

    Returns:
        Dicionário com strength, null_mean, p_value, consistency, picos,
        amplitude e corr_global; None se a série não permite calcular o
        índice (venda constante ou algum mês do ano sem dado).
    """
    ratios = seasonal_ratios(y)
    index = seasonal_index(ratios)
    if ratios.nunique() < 2 or index.isna().any():
        return None
    strength, null_mean, p_value, _ = _strength_and_null(ratios, n_permutations, np.random.default_rng(seed))
    peak, trough = index.idxmax(), index.idxmin()
    return {
        "n_months": len(y),
        "total_demand": float(y.sum()),
        "mean_demand": float(y.mean()),
        "strength": strength,
        "null_mean": null_mean,
        "p_value": p_value,
        "consistency": year_consistency(ratios),
        "peak_month": int(peak),
        "trough_month": int(trough),
        "peak_index": float(index[peak]),
        "trough_index": float(index[trough]),
        "amplitude": float(index[peak] / index[trough]) if index[trough] > 0 else np.nan,
        "corr_global": float(index.corr(global_index)) if global_index is not None else np.nan,
    }


def seasonality_table(
    wide: pd.DataFrame,
    global_index: pd.Series | None = None,
    min_history: int = MIN_HISTORY_MONTHS,
    n_permutations: int = N_PERMUTATIONS,
) -> pd.DataFrame:
    """Uma linha por produto com histórico suficiente, com p-valor corrigido (q_value).

    O q_value corrige o fato de testar centenas de produtos de uma vez: sem
    isso, ~5% dos produtos pareceriam sazonais só por sorte.

    Args:
        wide: Saída de product_month_matrix.
        global_index: Índice sazonal geral, para a correlação de cada produto.
        min_history: Meses mínimos de histórico (desde o primeiro mês do produto).
        n_permutations: Embaralhamentos por produto.

    Returns:
        DataFrame indexado pelo produto, ordenado pela força sazonal.
    """
    rows = {}
    for product, series in wide.items():
        y = series.dropna()
        if len(y) >= min_history:
            metrics = seasonality_metrics(y, global_index, n_permutations, seed=0)
            if metrics is not None:
                rows[product] = metrics
    if not rows:
        # Nenhum produto com histórico e variação suficientes: tabela vazia, com as colunas de sempre.
        empty = pd.DataFrame(columns=[*_METRIC_COLUMNS, "q_value", "is_seasonal"])
        empty.index.name = wide.columns.name
        return empty
    table = pd.DataFrame.from_dict(rows, orient="index")
    table.index.name = wide.columns.name
    valid = table["p_value"].notna()
    table["q_value"] = np.nan
    table.loc[valid, "q_value"] = false_discovery_control(table.loc[valid, "p_value"].to_numpy(), method="bh")
    table["is_seasonal"] = table["q_value"] < SIGNIFICANCE
    return table.sort_values("strength", ascending=False)


def strength_label(strength: float) -> str:
    """Rótulo de regra prática: fraca (< 0,2), moderada (0,2–0,5) ou forte (≥ 0,5); NaN é indefinida."""
    if np.isnan(strength):
        return "indefinida"
    if strength < 0.2:
        return "fraca"
    return "moderada" if strength < 0.5 else "forte"


def null_distribution(y: pd.Series, n_permutations: int = N_PERMUTATIONS, seed: int = 0) -> np.ndarray:
    """Forças sazonais obtidas embaralhando as razões: o que o acaso produz sozinho."""
    return _strength_and_null(seasonal_ratios(y), n_permutations, np.random.default_rng(seed))[3]


def year_month_grid(y: pd.Series) -> pd.DataFrame:
    """Razão venda ÷ tendência em uma grade ano (linhas) × mês (colunas 1–12)."""
    ratios = seasonal_ratios(y)
    grid = ratios.groupby([ratios.index.year, ratios.index.month]).mean().unstack()
    return grid.reindex(columns=range(1, 13))


# ── Um produto: quando vende e o que vem depois do pico ─────────────


def year_month_matrix(y: pd.Series) -> pd.DataFrame:
    """Unidades por ano (linhas) e mês do ano (colunas 1–12); NaN onde o mês não existe na série.

    Args:
        y: Demanda mensal do produto, com índice mensal (primeiro dia do mês).
    """
    frame = pd.DataFrame({"q": y.to_numpy(), "ano": y.index.year, "mes": y.index.month})
    return frame.pivot(index="ano", columns="mes", values="q").reindex(columns=range(1, 13))


def month_summary(matrix: pd.DataFrame) -> pd.DataFrame:
    """Resumo por mês do ano: média, mediana e em quantos anos o mês ficou acima da média do próprio ano.

    Comparar o mês com a média do próprio ano tira o efeito do crescimento: um
    mês só conta como "alto" se foi alto naquele ano.

    Args:
        matrix: Saída de year_month_matrix.

    Returns:
        Uma linha por mês do ano com media, mediana, anos (observados) e anos_acima.
    """
    above = matrix.gt(matrix.mean(axis=1), axis=0).where(matrix.notna())
    return pd.DataFrame(
        {
            "media": matrix.mean(),
            "mediana": matrix.median(),
            "anos": matrix.notna().sum(),
            "anos_acima": above.sum().astype(int),
        }
    )


def season_vs_offseason(y: pd.Series) -> pd.DataFrame:
    """Média mensal da alta temporada (nov–abr) e da baixa (mai–out) em cada temporada.

    Novembro e dezembro contam para a temporada do ano seguinte: a temporada
    2023 é nov/2022 a abr/2023 (alta) mais mai a out/2023 (baixa).

    Returns:
        Uma linha por temporada com meses_alta, media_alta, meses_baixa e media_baixa.
    """
    frame = pd.DataFrame({"q": y.to_numpy()}, index=y.index)
    frame["temporada"] = y.index.year + (y.index.month >= 11)
    frame["alta"] = y.index.month.isin(HIGH_SEASON_MONTHS)
    grouped = frame.groupby(["temporada", "alta"])["q"].agg(["mean", "count"]).unstack("alta")
    # Série só de alta (ou só de baixa) temporada: garante as quatro colunas, vazias onde não há mês.
    grouped = grouped.reindex(columns=pd.MultiIndex.from_product([["mean", "count"], [True, False]]))
    return pd.DataFrame(
        {
            "meses_alta": grouped[("count", True)],
            "media_alta": grouped[("mean", True)],
            "meses_baixa": grouped[("count", False)],
            "media_baixa": grouped[("mean", False)],
        }
    )


def peak_profile(y: pd.Series, offsets: range = range(-2, 4)) -> pd.DataFrame:
    """Demanda em volta do mês de pico de cada ano, relativa à média do ano.

    Só entram anos completos (12 meses). Para cada ano acha o mês com mais
    unidades (t = 0) e mede os meses de t-2 a t+3 dividindo pela média mensal
    daquele ano: 1,0 = mês normal; 3,0 = três vezes o normal.

    Returns:
        Uma linha por ano, com mes_pico e uma coluna por deslocamento em meses.
    """
    full_years = year_month_matrix(y).dropna()
    rows = {}
    for year, months in full_years.iterrows():
        peak_month = int(months.idxmax())
        peak = pd.Timestamp(year=int(year), month=peak_month, day=1)
        row = {"mes_pico": peak_month}
        # Ano sem venda nenhuma (média 0): o perfil relativo à média não existe.
        year_mean = months.mean() if months.mean() > 0 else np.nan
        for k in offsets:
            row[k] = y.get(peak + pd.DateOffset(months=k), np.nan) / year_mean
        rows[year] = row
    return pd.DataFrame.from_dict(rows, orient="index")
