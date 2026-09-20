"""Fixtures compartilhadas dos testes: painel sintético, resultado do XGBoost e gravadores falsos.

Os testes cobrem só a lógica em pandas/Python: nenhum abre sessão Spark, JVM ou
Databricks. As sessões Spark são substituídas por objetos falsos que registram o que
receberam (`RecordingSpark`).
"""

from __future__ import annotations

import pandas as pd
import pytest


# ── Spark falso que registra a escrita, sem sessão Spark ───────────────


class RecordingWriter:
    """Registra a cadeia de escrita do DataFrameWriter, sem gravar nada."""

    def __init__(self):
        self.calls = []

    def format(self, name):
        self.calls.append(("format", name))
        return self

    def mode(self, name):
        self.calls.append(("mode", name))
        return self

    def option(self, key, value):
        self.calls.append(("option", key, value))
        return self

    def partitionBy(self, *columns):  # noqa: N802 - nome da API do Spark
        self.calls.append(("partitionBy", *columns))
        return self

    def saveAsTable(self, name):  # noqa: N802 - nome da API do Spark
        self.calls.append(("saveAsTable", name))


class RecordingFrame:
    """O que `createDataFrame` recebeu (dados e schema) e o registro da cadeia de escrita."""

    def __init__(self, data, schema):
        self.data = data
        self.schema = schema
        self.write = RecordingWriter()


class RecordingSpark:
    """Guarda o que recebe em `createDataFrame` e serve tabelas fixas por nome.

    Nenhuma escrita chega ao Unity Catalog e não há sessão Spark.
    """

    def __init__(self, tables=None):
        self.tables = tables or {}
        self.created = []
        self.table_requests = []

    def createDataFrame(self, data, schema=None):  # noqa: N802 - nome da API do Spark
        frame = RecordingFrame(data, schema)
        self.created.append(frame)
        return frame

    def table(self, name):
        self.table_requests.append(name)
        return self.tables[name]


class FakeTable:
    """Tabela do Spark que devolve um pandas com metadados do Databricks Connect em `.attrs`."""

    def __init__(self, frame):
        self.frame = frame

    def toPandas(self):  # noqa: N802 - nome da API do Spark
        out = self.frame.copy()
        out.attrs["metricas_do_connect"] = object()  # o Databricks Connect pendura isto em .attrs
        return out


@pytest.fixture()
def recorder():
    """Spark falso com escrita registrada, sem tabelas."""
    return RecordingSpark()


@pytest.fixture()
def make_recording_spark():
    """Fábrica de `RecordingSpark` com tabelas servidas por nome: `make_recording_spark({"a.b.c": fake_table(df)})`."""
    return lambda tables=None: RecordingSpark(tables)


@pytest.fixture()
def fake_table():
    """Classe `FakeTable`: `fake_table(pandas_df)`."""
    return FakeTable


def build_demand_panel(n_months: int = 72, n_series: int = 10, seed: int = 0) -> pd.DataFrame:
    """Painel sintético de `ml_features_produto_loja_mes`, com todas as colunas do XGBoost.

    Um corte por mês desde jan/2019; os 3 últimos cortes não têm alvo (inferência) e a
    tendência só existe a partir do 24º mês, como na tabela dbt. Determinístico.
    """
    import datetime as dt

    import numpy as np

    from src.analytics_ai.demand_common import add_months

    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_months):
        cutoff = add_months(dt.date(2019, 1, 1), i)
        for s in range(n_series):
            level = 2.0 + s
            season = 1.0 + 0.3 * np.sin(2 * np.pi * cutoff.month / 12)
            base = level / 12 * 3 * season
            complete = i <= n_months - 4
            rows.append(
                {
                    "cutoff": cutoff,
                    "sk_product": f"p{s}",
                    "sk_location": f"l{s % 2}",
                    "category_name": f"c{s % 3}",
                    "is_target_complete": complete,
                    "trend_ready": i >= 23,
                    "target_3m": float(rng.poisson(base)) if complete else np.nan,
                    "sum_3m": float(rng.poisson(level / 4)),
                    "sum_12m": float(rng.poisson(level)),
                    "produto_locais_avg_12m": level,
                    "categoria_local_avg_12m": level + 1,
                    "season_sum_next_3m": 3 * season,
                    "growth_12m": 1.0 + 0.01 * s,
                    "trend_factor": 1.0,
                    "baseline_pred_categoria_local_idx_trend": base,
                    "avg_monthly_3m": level / 4,
                    "avg_monthly_12m": level / 12,
                    "months_with_sale_12m": float(rng.integers(0, 13)),
                    "months_since_last_sale": float(rng.integers(0, 6)),
                    "is_stopped_12m": False,
                    "produto_locais_n_locations": 2.0,
                    "categoria_local_n_series": 5.0,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture(scope="session")
def demand_panel() -> pd.DataFrame:
    """Painel sintético compartilhado (não modifique: use `.copy()`)."""
    return build_demand_panel()


@pytest.fixture(scope="session")
def xgboost_result(demand_panel) -> dict:
    """Resultado de `demand_xgboost.run` sobre o painel sintético (roda uma vez por sessão)."""
    from src.analytics_ai.demand_xgboost import run

    return run(demand_panel.copy())
