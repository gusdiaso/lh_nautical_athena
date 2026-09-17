"""Médias móveis como régua da previsão de 3 meses (Etapa 2 do plano de previsão).

Monta um painel com uma linha por série produto × loja × mês de corte, com as
somas móveis do passado e o alvo (total dos 3 meses seguintes), e calcula as
réguas de previsão e os erros. Tudo usa só meses completos de
agg_demand_monthly; o índice sazonal e a tendência são recalculados em cada
corte com dados até o próprio corte, para não usar informação do futuro.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd
from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

DEFAULT_ID_COLS = ("sk_product", "sk_location")
DEFAULT_TARGET_COL = "demand_quantity"
DEFAULT_DATE_COL = "month_start_date"
HORIZON = 3

# Distância, em meses, entre o centro da janela da MM12 (5,5 meses antes do
# corte) e o centro dos 3 meses previstos (2 meses depois do corte).
MM12_LAG_MONTHS = 7.5


def add_months(month: dt.date, n: int) -> dt.date:
    """Soma n meses a uma data que é sempre o dia 1 do mês."""
    index = month.year * 12 + month.month - 1 + n
    return dt.date(index // 12, index % 12 + 1, 1)


def cutoff_months(last_complete_month: dt.date, n_cutoffs: int = 12, horizon: int = HORIZON) -> list[dt.date]:
    """Os n últimos meses de corte cujo alvo de `horizon` meses já aconteceu.

    Args:
        last_complete_month: Último mês completo do dataset.
        n_cutoffs: Quantidade de cortes.
        horizon: Meses somados no alvo.

    Returns:
        Lista de meses de corte, do mais antigo ao mais recente.
    """
    last_cutoff = add_months(last_complete_month, -horizon)
    return [add_months(last_cutoff, -k) for k in range(n_cutoffs - 1, -1, -1)]


# ── Painel ──────────────────────────────────────────────────────────


def build_cutoff_panel(
    complete_monthly: DataFrame,
    cutoffs: Sequence[dt.date],
    date_col: str = DEFAULT_DATE_COL,
    id_cols: Sequence[str] = DEFAULT_ID_COLS,
    target_col: str = DEFAULT_TARGET_COL,
    horizon: int = HORIZON,
) -> DataFrame:
    """Uma linha por série × mês de corte, com o passado e o alvo.

    As janelas contam linhas da série mensal, que é densa (um registro por
    mês desde a primeira venda). `window_ok` confirma que as janelas cobrem
    exatamente os meses esperados, sem buracos.

    Args:
        complete_monthly: Série mensal só com meses completos.
        cutoffs: Meses de corte.
        date_col: Coluna com o primeiro dia do mês.
        id_cols: Colunas que identificam a série.
        target_col: Coluna de demanda.
        horizon: Meses somados no alvo.

    Returns:
        DataFrame com cutoff, id_cols, sum_12m, sum_3m, months_with_sale_12m,
        months_since_last_sale, target_3m e window_ok.
    """
    id_cols = list(id_cols)
    by_series = Window.partitionBy(*id_cols).orderBy(date_col)
    past_12 = by_series.rowsBetween(-11, 0)
    past_3 = by_series.rowsBetween(-2, 0)
    future = by_series.rowsBetween(1, horizon)
    history = by_series.rowsBetween(Window.unboundedPreceding, 0)

    q = F.col("_q")
    last_sale = F.max(F.when(q > 0, F.col(date_col))).over(history)
    panel = (
        complete_monthly.withColumn("_q", F.col(target_col).cast("double"))
        .withColumn("sum_12m", F.sum(q).over(past_12))
        .withColumn("sum_3m", F.sum(q).over(past_3))
        .withColumn("months_with_sale_12m", F.sum((q > 0).cast("int")).over(past_12))
        .withColumn("months_since_last_sale", F.months_between(F.col(date_col), last_sale).cast("int"))
        .withColumn("target_3m", F.sum(q).over(future))
        .withColumn(
            "window_ok",
            (F.count(q).over(past_12) == 12)
            & (F.min(date_col).over(past_12) == F.add_months(F.col(date_col), -11))
            & (F.count(q).over(future) == horizon)
            & (F.max(date_col).over(future) == F.add_months(F.col(date_col), horizon)),
        )
    )
    cutoff_values = [F.lit(c).cast("date") for c in cutoffs]
    return panel.filter(F.col(date_col).isin(*cutoff_values)).select(
        F.col(date_col).alias("cutoff"),
        *id_cols,
        "sum_12m",
        "sum_3m",
        "months_with_sale_12m",
        "months_since_last_sale",
        "target_3m",
        "window_ok",
    )


def monthly_totals(
    complete_monthly: DataFrame,
    date_col: str = DEFAULT_DATE_COL,
    target_col: str = DEFAULT_TARGET_COL,
) -> pd.DataFrame:
    """Demanda total de todas as séries por mês (pandas, ordenado por mês)."""
    return (
        complete_monthly.groupBy(date_col)
        .agg(F.sum(F.col(target_col).cast("double")).alias("demand"))
        .orderBy(date_col)
        .toPandas()
        .rename(columns={date_col: "month"})
    )


# ── Índice sazonal e tendência no corte ─────────────────────────────


def seasonal_index_at(totals: pd.DataFrame, cutoff: dt.date) -> dict[int, float]:
    """Índice sazonal por mês do ano usando só meses até o corte.

    Mesma regra de int_high_season_months: média de cada mês do ano ao longo
    dos anos ÷ média das 12 médias mensais.

    Args:
        totals: Saída de monthly_totals.
        cutoff: Mês de corte.

    Returns:
        Dicionário mês do ano (1–12) → índice.
    """
    past = totals[pd.to_datetime(totals["month"]) <= pd.Timestamp(cutoff)]
    by_month = past.groupby(pd.to_datetime(past["month"]).dt.month)["demand"].mean()
    if len(by_month) < 12:
        raise ValueError(f"corte {cutoff}: faltam meses do ano para o índice sazonal")
    return (by_month / by_month.mean()).to_dict()


def trend_factor_at(totals: pd.DataFrame, cutoff: dt.date, lag_months: float = MM12_LAG_MONTHS) -> tuple[float, float]:
    """Crescimento anual no corte e o fator que leva a MM12 até o horizonte.

    Crescimento = total dos 12 meses até o corte ÷ total dos 12 anteriores.
    Fator = crescimento ^ (lag_months / 12): quanto a demanda deve ter
    crescido entre o centro da janela da MM12 e o centro dos meses previstos.

    Returns:
        (crescimento anual, fator de correção).
    """
    months = pd.to_datetime(totals["month"])
    cut, minus_12, minus_24 = (pd.Timestamp(add_months(cutoff, -n)) for n in (0, 12, 24))
    last = totals[(months > minus_12) & (months <= cut)]["demand"].sum()
    prev = totals[(months > minus_24) & (months <= minus_12)]["demand"].sum()
    growth = last / prev
    return float(growth), float(growth ** (lag_months / 12))


# ── Réguas ──────────────────────────────────────────────────────────


def add_forecasts(
    panel: pd.DataFrame,
    totals: pd.DataFrame,
    group_cols: Mapping[str, Sequence[str]],
    horizon: int = HORIZON,
) -> pd.DataFrame:
    """Calcula as réguas de previsão do total dos próximos `horizon` meses.

    Colunas criadas:

    - pred_mm12: MM12 × horizon
    - pred_mm3: MM3 × horizon
    - pred_mm12_idx: MM12 × soma dos índices sazonais dos meses previstos
    - pred_mm12_idx_trend: pred_mm12_idx × fator de tendência do corte
    - pred_<grupo>_idx: média por série do grupo (MM12 do grupo ÷ séries do
      grupo) × soma dos índices — a mesma previsão para toda série do grupo
    - pred_<grupo>_idx_trend: pred_<grupo>_idx × fator de tendência do corte

    Args:
        panel: Painel em pandas (saída de build_cutoff_panel), com as colunas
            de grupo já juntadas.
        totals: Saída de monthly_totals.
        group_cols: Nome do grupo → colunas (ex.: {"produto": ["sk_product"]}).
        horizon: Meses previstos.

    Returns:
        Cópia do painel com as previsões, season_sum, growth_12m e trend_factor.
    """
    df = panel.copy()
    per_cutoff = []
    for cutoff in sorted(df["cutoff"].unique()):
        index = seasonal_index_at(totals, cutoff)
        target_months = [add_months(cutoff, k).month for k in range(1, horizon + 1)]
        growth, factor = trend_factor_at(totals, cutoff)
        per_cutoff.append(
            {
                "cutoff": cutoff,
                "season_sum": sum(index[m] for m in target_months),
                "growth_12m": growth,
                "trend_factor": factor,
            }
        )
    df = df.merge(pd.DataFrame(per_cutoff), on="cutoff")

    df["pred_mm12"] = df["sum_12m"] / 12 * horizon
    df["pred_mm3"] = df["sum_3m"] / 3 * horizon
    df["pred_mm12_idx"] = df["sum_12m"] / 12 * df["season_sum"]
    df["pred_mm12_idx_trend"] = df["pred_mm12_idx"] * df["trend_factor"]
    for name, cols in group_cols.items():
        keys = ["cutoff", *cols]
        group_mean = df.groupby(keys)["sum_12m"].transform("sum") / df.groupby(keys)["sum_12m"].transform("size")
        df[f"pred_{name}_idx"] = group_mean / 12 * df["season_sum"]
        df[f"pred_{name}_idx_trend"] = df[f"pred_{name}_idx"] * df["trend_factor"]
    return df


# ── Erro ────────────────────────────────────────────────────────────


def error_table(
    df: pd.DataFrame,
    forecasts: Mapping[str, str],
    by: Sequence[str] = (),
    actual_col: str = "target_3m",
    reference: str | None = "MM12",
) -> pd.DataFrame:
    """WAPE, viés e erro relativo de cada régua, no total ou por grupo.

    - WAPE = soma |previsto − real| ÷ soma real
    - viés = (soma previsto − soma real) ÷ soma real
    - erro relativo = WAPE da régua ÷ WAPE da régua de referência

    Args:
        df: Painel com as previsões.
        forecasts: Rótulo → coluna de previsão.
        by: Colunas de agrupamento; vazio = total.
        actual_col: Coluna do valor real.
        reference: Rótulo da régua de referência (None, ou ausente em
            `forecasts`, para não calcular).

    Returns:
        Uma linha por grupo × régua com n, wape, vies e erro_relativo.
    """
    groups = df.groupby(list(by)) if by else [((), df)]
    rows = []
    for key, part in groups:
        key = key if isinstance(key, tuple) else (key,)
        actual = part[actual_col].sum()
        for label, col in forecasts.items():
            rows.append(
                {
                    **dict(zip(by, key, strict=True)),
                    "regua": label,
                    "n": len(part),
                    "wape": (part[col] - part[actual_col]).abs().sum() / actual,
                    "vies": (part[col].sum() - actual) / actual,
                }
            )
    table = pd.DataFrame(rows)
    if reference is not None and reference in forecasts:
        ref = table[table["regua"] == reference].set_index(list(by))["wape"] if by else None
        if by:
            table["erro_relativo"] = table["wape"] / table.set_index(list(by)).index.map(ref)
        else:
            table["erro_relativo"] = table["wape"] / table.loc[table["regua"] == reference, "wape"].iloc[0]
    for col in ("wape", "vies", "erro_relativo"):
        if col in table:
            table[col] = table[col].round(4)
    return table


def aggregated_error_table(
    df: pd.DataFrame,
    forecasts: Mapping[str, str],
    level: Sequence[str],
    actual_col: str = "target_3m",
) -> pd.DataFrame:
    """Erro depois de somar séries num nível (ex.: loja × categoria × corte).

    Mede a previsão onde ela é usada na prática: o erro de cada série se
    compensa em parte quando as séries são somadas.
    """
    summed = df.groupby(["cutoff", *level], as_index=False)[[actual_col, *forecasts.values()]].sum()
    return error_table(summed, forecasts, actual_col=actual_col)


# ── Persistência ────────────────────────────────────────────────────


def year_over_year_persistence(
    complete_monthly: DataFrame,
    last_month: dt.date,
    unit_cols: Sequence[str],
    date_col: str = DEFAULT_DATE_COL,
    target_col: str = DEFAULT_TARGET_COL,
    top_share: float = 0.2,
) -> dict:
    """O volume de uma unidade (série ou produto) se repete de um ano para o outro?

    Compara o volume de cada unidade nos 12 meses até `last_month` com os 12
    meses anteriores.

    Returns:
        Dicionário com n_unidades, correlação de Pearson, correlação de
        Spearman (por posição no ranking) e permanência no topo: fração das
        unidades no top `top_share` do primeiro ano que continuam no top do
        segundo (ao acaso seria igual a `top_share`).
    """
    ref = F.lit(last_month).cast("date")
    in_last = (F.col(date_col) > F.add_months(ref, -12)) & (F.col(date_col) <= ref)
    in_prev = (F.col(date_col) > F.add_months(ref, -24)) & (F.col(date_col) <= F.add_months(ref, -12))
    q = F.col(target_col).cast("double")
    volumes = (
        complete_monthly.groupBy(*unit_cols)
        .agg(
            F.sum(F.when(in_prev, q)).alias("ano_anterior"),
            F.sum(F.when(in_last, q)).alias("ultimo_ano"),
        )
        .dropna()
        .toPandas()
    )
    n_top = int(round(len(volumes) * top_share))
    top_prev = set(volumes.nlargest(n_top, "ano_anterior").index)
    top_last = set(volumes.nlargest(n_top, "ultimo_ano").index)
    return {
        "n_unidades": len(volumes),
        "correlacao_pearson": round(float(np.corrcoef(volumes["ano_anterior"], volumes["ultimo_ano"])[0, 1]), 3),
        # Spearman = Pearson sobre as posições no ranking (sem depender do scipy).
        "correlacao_spearman": round(float(volumes["ano_anterior"].rank().corr(volumes["ultimo_ano"].rank())), 3),
        "permanencia_no_topo": round(len(top_prev & top_last) / n_top, 3),
        "permanencia_ao_acaso": top_share,
    }


# ── Faixa de previsão por produto ───────────────────────────────────

INTERVAL_QUANTILES = (0.25, 0.5, 0.75, 0.9)


def fit_interval_buckets(
    calibration: pd.DataFrame,
    pred_col: str,
    actual_col: str = "target_3m",
    n_buckets: int = 10,
    quantiles: Sequence[float] = INTERVAL_QUANTILES,
) -> pd.DataFrame:
    """Aprende, em cortes antigos, como a venda real se espalha em torno da previsão.

    As previsões da calibração são divididas em `n_buckets` faixas de
    tamanho (decis). Em cada faixa, guarda os quantis da venda real: é a
    distribuição observada de "quanto se vendeu quando a previsão era deste
    tamanho". Como usa só cortes cujo alvo já terminou antes do período de
    teste, não carrega informação do futuro.

    Args:
        calibration: Painel com previsões e alvo, só com cortes de calibração.
        pred_col: Coluna da quantidade esperada.
        actual_col: Coluna da venda real.
        n_buckets: Quantidade de faixas de previsão.
        quantiles: Quantis da venda real a guardar.

    Returns:
        Uma linha por faixa com lower, upper (limites da previsão), n e q_<p>
        para cada quantil (ex.: q_90).
    """
    edges = np.unique(np.quantile(calibration[pred_col], np.linspace(0, 1, n_buckets + 1)))
    buckets = np.clip(np.searchsorted(edges, calibration[pred_col], side="right") - 1, 0, len(edges) - 2)
    rows = []
    for b in range(len(edges) - 1):
        actual = calibration.loc[buckets == b, actual_col]
        if actual.empty:
            continue
        row = {"bucket": b, "lower": edges[b], "upper": edges[b + 1], "n": len(actual)}
        row.update({f"q_{round(q * 100)}": float(actual.quantile(q)) for q in quantiles})
        rows.append(row)
    return pd.DataFrame(rows)


def apply_interval_buckets(df: pd.DataFrame, buckets: pd.DataFrame, pred_col: str) -> pd.DataFrame:
    """Aplica a faixa aprendida: cada previsão recebe os quantis da sua faixa.

    Previsões fora do intervalo visto na calibração ficam na faixa mais
    próxima (a primeira ou a última).

    Returns:
        Cópia de `df` com as colunas q_<p> de `buckets`.
    """
    out = df.copy()
    position = np.clip(
        np.searchsorted(buckets["lower"].to_numpy(), out[pred_col].to_numpy(), side="right") - 1,
        0,
        len(buckets) - 1,
    )
    for col in [c for c in buckets.columns if c.startswith("q_")]:
        out[col] = buckets[col].to_numpy()[position]
    return out


def interval_coverage(
    df: pd.DataFrame,
    by: Sequence[str] = (),
    actual_col: str = "target_3m",
) -> pd.DataFrame:
    """Confere se os limites de venda acertam na proporção prometida.

    - ate_q50: venda real até q_50 (prometido: ~50%)
    - ate_q75: venda real até q_75, o "limite de 3 em cada 4 vezes" (~75%)
    - ate_q90: venda real até q_90, o "limite de 9 em cada 10 vezes" (~90%)

    Com vendas inteiras e muitos zeros, a proporção fica um pouco acima do
    prometido quando vários valores empatam no limite.
    """
    groups = df.groupby(list(by)) if by else [((), df)]
    rows = []
    for key, part in groups:
        key = key if isinstance(key, tuple) else (key,)
        actual = part[actual_col]
        rows.append(
            {
                **dict(zip(by, key, strict=True)),
                "n": len(part),
                "ate_q50": round(float((actual <= part["q_50"]).mean()), 3),
                "ate_q75": round(float((actual <= part["q_75"]).mean()), 3),
                "ate_q90": round(float((actual <= part["q_90"]).mean()), 3),
            }
        )
    return pd.DataFrame(rows)


# ── Base de comparação ──────────────────────────────────────────────


def poisson_deviance(actual: pd.Series, pred: pd.Series) -> float:
    """Desvio de Poisson médio: erro por produto que não premia prever abaixo.

    É minimizado pela média verdadeira (ao contrário do WAPE por produto,
    minimizado pela mediana, que com muitos zeros fica abaixo da média).
    Menor é melhor; só serve para comparar previsões do mesmo alvo.
    """
    y = actual.to_numpy(dtype=float)
    mu = np.clip(pred.to_numpy(dtype=float), 1e-6, None)
    with np.errstate(divide="ignore", invalid="ignore"):
        term = np.where(y > 0, y * np.log(y / mu), 0.0)
    return float(np.mean(2 * (term - (y - mu))))


def comparison_scorecard(
    df: pd.DataFrame,
    forecasts: Mapping[str, str],
    group_level: Sequence[str] = ("category_name", "sk_location"),
    location_level: Sequence[str] = ("sk_location",),
    actual_col: str = "target_3m",
) -> pd.DataFrame:
    """Quadro padrão para comparar qualquer previsão com a régua.

    Todas as previsões precisam estar no mesmo painel (mesmas linhas de
    série × corte). Métricas:

    - erro_produto: WAPE por produto × local
    - erro_categoria_local e erro_local: WAPE depois de somar
    - vies: (total previsto − total vendido) ÷ total vendido
    - erro_medio_unidades: erro médio absoluto por produto, em unidades
    - desvio_poisson: erro por produto que não premia prever abaixo

    Returns:
        Uma linha por previsão.
    """
    rows = []
    for label, col in forecasts.items():
        actual = df[actual_col]
        rows.append(
            {
                "previsao": label,
                "erro_produto": (df[col] - actual).abs().sum() / actual.sum(),
                "erro_categoria_local": aggregated_error_table(df, {label: col}, list(group_level), actual_col)["wape"].iloc[0],
                "erro_local": aggregated_error_table(df, {label: col}, list(location_level), actual_col)["wape"].iloc[0],
                "vies": (df[col].sum() - actual.sum()) / actual.sum(),
                "erro_medio_unidades": (df[col] - actual).abs().mean(),
                "desvio_poisson": poisson_deviance(actual, df[col]),
            }
        )
    table = pd.DataFrame(rows).set_index("previsao")
    return table.round({"erro_produto": 4, "erro_categoria_local": 4, "erro_local": 4, "vies": 4, "erro_medio_unidades": 2, "desvio_poisson": 3})


def past_volume_quintiles(df: pd.DataFrame, actual_col: str = "target_3m") -> pd.DataFrame:
    """Quem vendeu mais no último ano vende mais nos 3 meses seguintes?

    Em cada corte, divide as séries em 5 grupos iguais pela venda dos 12
    meses anteriores (1 = as 20% que menos venderam, 5 = as 20% que mais
    venderam) e compara com a venda média dos 3 meses seguintes.

    Returns:
        Uma linha por quintil com venda_media_12m_antes e
        venda_media_3m_depois.
    """
    ranked = df.copy()
    ranked["quintil"] = ranked.groupby("cutoff")["sum_12m"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
    )
    return (
        ranked.groupby("quintil", observed=True)
        .agg(
            series=("sum_12m", "size"),
            venda_media_12m_antes=("sum_12m", "mean"),
            venda_media_3m_depois=(actual_col, "mean"),
        )
        .round(2)
    )
