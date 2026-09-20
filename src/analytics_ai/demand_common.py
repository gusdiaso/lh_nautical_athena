"""Peças compartilhadas pelos notebooks de previsão (04 a 07).

Calendário de meses de corte e as métricas de erro que comparam qualquer
previsão com a régua: WAPE, viés, desvio de Poisson, RMSE e o quadro
`comparison_scorecard`. Não depende de Spark — só de pandas e numpy.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

HORIZON = 3


def as_bool(series: pd.Series) -> pd.Series:
    """Coluna booleana sem nulos: nulo vira False.

    Passa por `boolean` (que aceita None) porque `fillna(False)` direto numa
    coluna de objetos, como o Delta entrega, emite FutureWarning do pandas, e
    filtrar com uma máscara que tenha nulos falha.
    """
    return series.astype("boolean").fillna(False).astype(bool)


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


# ── Erro ────────────────────────────────────────────────────────────


def _ratio(numerator: float, denominator: float) -> float:
    """Divisão que devolve NaN (indefinido) quando o denominador é zero.

    Um grupo sem venda real não tem WAPE nem viés: dividir por zero daria
    infinito e um aviso do numpy, e o infinito contaminaria qualquer média
    calculada depois sobre os grupos.
    """
    return numerator / denominator if denominator != 0 else float("nan")


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
                    "wape": _ratio((part[col] - part[actual_col]).abs().sum(), actual),
                    "vies": _ratio(part[col].sum() - actual, actual),
                }
            )
    # Colunas explícitas: sem linhas (painel vazio) a tabela ainda tem o formato certo.
    table = pd.DataFrame(rows, columns=[*by, "regua", "n", "wape", "vies"])
    if reference is not None and reference in forecasts:
        if by:
            ref = table[table["regua"] == reference].set_index(list(by))["wape"]
            table["erro_relativo"] = table["wape"] / table.set_index(list(by)).index.map(ref)
        elif table.empty:
            table["erro_relativo"] = pd.Series(dtype=float)
        else:
            table["erro_relativo"] = table["wape"] / table.loc[table["regua"] == reference, "wape"].iloc[0]
    for col in ("wape", "vies", "erro_relativo"):
        if col in table:
            table[col] = table[col].astype(float).round(4)
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
    summed = df.groupby(
        ["cutoff", *level], as_index=False)[[actual_col, *forecasts.values()]].sum()
    return error_table(summed, forecasts, actual_col=actual_col)


# ── Base de comparação ──────────────────────────────────────────────


def poisson_deviance(actual: pd.Series, pred: pd.Series) -> float:
    """Desvio de Poisson médio: erro por produto que não premia prever abaixo.

    É minimizado pela média verdadeira (ao contrário do WAPE por produto,
    minimizado pela mediana, que com muitos zeros fica abaixo da média).
    Menor é melhor; só serve para comparar previsões do mesmo alvo.
    """
    y = actual.to_numpy(dtype=float)
    if y.size == 0:
        return float("nan")
    mu = np.clip(pred.to_numpy(dtype=float), 1e-6, None)
    with np.errstate(divide="ignore", invalid="ignore"):
        term = np.where(y > 0, y * np.log(y / mu), 0.0)
    return float(np.mean(2 * (term - (y - mu))))


def root_mean_squared_error(actual: pd.Series, pred: pd.Series) -> float:
    """Raiz do erro quadrático médio (RMSE), em unidades do alvo.

    Penaliza erros grandes mais que o erro médio absoluto, por elevar cada
    desvio ao quadrado. Com demanda muito assimétrica (metade das linhas em
    zero e cauda longa), fica bem acima do erro médio em unidades — a
    diferença entre os dois mede o peso da cauda.

    Args:
        actual: Venda real.
        pred: Previsão, na mesma ordem de `actual`.

    Returns:
        RMSE em unidades vendidas.
    """
    erro = pred.to_numpy(dtype=float) - actual.to_numpy(dtype=float)
    if erro.size == 0:
        return float("nan")
    return float(np.sqrt(np.mean(erro**2)))


def comparison_scorecard(
    df: pd.DataFrame,
    forecasts: Mapping[str, str],
    group_level: Sequence[str] = ("category_name", "sk_location"),
    location_level: Sequence[str] = ("sk_location",),
    actual_col: str = "target_3m",
) -> pd.DataFrame:
    """Quadro padrão para comparar qualquer previsão com a régua.

    Todas as previsões precisam estar no mesmo painel (mesmas linhas de
    série × corte, com a coluna `cutoff`). Colunas do quadro:

    - wape_produto: WAPE por produto × local
    - mae_produto: erro médio absoluto por produto × local, em unidades (MAE)
    - rmse_produto: raiz do erro quadrático médio por produto × local, em
      unidades (RMSE; pesa mais os erros grandes que o MAE)
    - wape_categoria_local e wape_local: WAPE depois de somar as séries
      (`group_level` e `location_level`), corte a corte
    - vies: (total previsto − total vendido) ÷ total vendido
    - desvio_poisson: erro por produto que não premia prever abaixo

    Sem venda real no painel, os WAPEs e o viés ficam indefinidos (NaN).

    Returns:
        Uma linha por previsão, indexada por `previsao`.
    """
    rows = []
    for label, col in forecasts.items():
        actual = df[actual_col]
        erro = df[col] - actual
        rows.append(
            {
                "previsao": label,
                "wape_produto": _ratio(erro.abs().sum(), actual.sum()),
                "mae_produto": erro.abs().mean(),
                "rmse_produto": root_mean_squared_error(actual, df[col]),
                "wape_categoria_local": aggregated_error_table(df, {label: col}, list(group_level), actual_col)["wape"].iloc[0],
                "wape_local": aggregated_error_table(df, {label: col}, list(location_level), actual_col)["wape"].iloc[0],
                "vies": _ratio(df[col].sum() - actual.sum(), actual.sum()),
                "desvio_poisson": poisson_deviance(actual, df[col]),
            }
        )
    table = pd.DataFrame(rows).set_index("previsao")
    return table.round(
        {
            "wape_produto": 4,
            "mae_produto": 2,
            "rmse_produto": 2,
            "wape_categoria_local": 4,
            "wape_local": 4,
            "vies": 4,
            "desvio_poisson": 3,
        }
    )


# ── Quadro de notebook: previsões contra a régua ───────────────────


def cutoff_wape(
    df: pd.DataFrame,
    column: str,
    actual_col: str = "target_3m",
    group_level: Sequence[str] = ("category_name", "sk_location"),
) -> pd.Series:
    """WAPE de cada mês de corte, depois de somar as séries em `group_level`.

    Diferente de `comparison_scorecard`, que junta todos os cortes num número
    só, devolve um valor por corte: é o que diz em quantos meses um método
    ganha de outro.

    Args:
        df: Painel com a previsão e o valor real, com a coluna `cutoff`.
        column: Coluna de previsão.
        actual_col: Coluna do valor real.
        group_level: Nível em que as séries são somadas (padrão: categoria × local).

    Returns:
        WAPE indexado por `cutoff`.
    """
    summed = df.groupby(["cutoff", *group_level])[[actual_col, column]].sum()
    error = (summed[column] - summed[actual_col]).abs().groupby(level="cutoff").sum()
    return error / summed[actual_col].groupby(level="cutoff").sum()


def scorecard_vs_ruler(
    df: pd.DataFrame,
    forecasts: Mapping[str, str],
    ruler_col: str,
    ruler_label: str = "Régua final",
    actual_col: str = "target_3m",
) -> pd.DataFrame:
    """Quadro do notebook 04 (em %), mais os cortes em que cada método ganha da régua.

    Args:
        df: Painel com todas as previsões (mesmas linhas de série × corte).
        forecasts: Rótulo → coluna de previsão.
        ruler_col: Coluna de previsão da régua, contra a qual se conta os ganhos.
        ruler_label: Rótulo da régua em `forecasts`; sua linha mostra "–" nos ganhos.
        actual_col: Coluna do valor real.

    Returns:
        Uma linha por previsão, com erros e viés em %, MAE e RMSE em unidades
        e a contagem de cortes ganhos da régua (texto).
    """
    card = comparison_scorecard(df, forecasts, actual_col=actual_col)
    table = pd.DataFrame(
        {
            "Erro por produto × loja (%)": card["wape_produto"] * 100,
            "Erro por categoria no local (%)": card["wape_categoria_local"] * 100,
            "Erro por local (%)": card["wape_local"] * 100,
            "Viés (%)": card["vies"] * 100,
            "MAE (unidades)": card["mae_produto"],
            "RMSE (unidades)": card["rmse_produto"],
        }
    ).round(2)
    ruler_by_cutoff = cutoff_wape(df, ruler_col, actual_col)
    table["Cortes ganhos da régua (de 12)"] = [
        str((cutoff_wape(df, col, actual_col) < ruler_by_cutoff).sum()) for col in forecasts.values()
    ]
    if ruler_label in table.index:
        table.loc[ruler_label, "Cortes ganhos da régua (de 12)"] = "–"
    return table
