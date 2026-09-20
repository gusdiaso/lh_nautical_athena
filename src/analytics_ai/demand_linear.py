"""Regressão linear da demanda dos próximos 3 meses (notebooks 05 e 05b).

Os grupos de features, a leitura da tabela de features e o ajuste (regressão
simples ou Ridge, com janela de treino opcional). A justificativa de cada
feature está em `docs/dicionario_features_ml_produto_loja_mes.md`.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from pyspark.sql import functions as F
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

TARGET = "target_3m"
ESSENTIAL_FEATURES = ["categoria_local_avg_12m", "season_sum_next_3m", "trend_factor"]
RULER_FEATURE = "baseline_pred_categoria_local_idx_trend"
HISTORY_FEATURES = ["sum_12m", "sum_3m", "months_with_sale_12m", "months_since_last_sale"]
GROUP_FEATURES = ["produto_locais_avg_12m", "produto_locais_n_locations", "categoria_local_n_series"]
NUMERIC_FEATURES = [*ESSENTIAL_FEATURES, RULER_FEATURE, *HISTORY_FEATURES, *GROUP_FEATURES]


def load_linear_panel(spark, table: str) -> tuple[pd.DataFrame, int]:
    """Lê a tabela de features numa única consulta e descarta linhas com valor ausente.

    Só entram linhas com alvo conhecido e tendência pronta (os primeiros
    cortes não têm 24 meses de histórico).

    Args:
        spark: Sessão Spark.
        table: Nome completo da tabela de features.

    Returns:
        O painel em pandas e quantas linhas foram descartadas por valor ausente.
    """
    panel = (
        spark.table(table)
        .filter("is_target_complete AND trend_ready")
        .select(
            "cutoff",
            "sk_product",
            "sk_location",
            "category_name",
            *[F.col(c).cast("double") for c in [*NUMERIC_FEATURES, TARGET]],
        )
        .toPandas()
    )
    clean = panel.dropna(subset=[*NUMERIC_FEATURES, TARGET])
    return clean, len(panel) - len(clean)


def fit_linear(
    train: pd.DataFrame,
    columns: Sequence[str],
    n_cutoffs: int | None = None,
    alpha: float | None = None,
) -> LinearRegression | Pipeline:
    """Treina nos `n_cutoffs` cortes mais recentes de `train` (None = todos).

    Args:
        train: Painel de treino, com `cutoff` e o alvo.
        columns: Features.
        n_cutoffs: Janela de treino, em cortes.
        alpha: Força do Ridge; None = regressão linear simples. O Ridge padroniza
            as features antes, senão a penalidade cairia só sobre as de escala menor.
    """
    if n_cutoffs is not None:
        recent = sorted(train["cutoff"].unique())[-n_cutoffs:]
        train = train[train["cutoff"].isin(recent)]
    model = LinearRegression() if alpha is None else make_pipeline(StandardScaler(), Ridge(alpha=alpha))
    return model.fit(train[list(columns)], train[TARGET])


def predict_nonnegative(model, frame: pd.DataFrame, columns: Sequence[str]) -> np.ndarray:
    """Previsão sem negativos: uma venda nunca é negativa, mas uma soma de pesos pode ser."""
    return np.clip(model.predict(frame[list(columns)]), 0, None)
