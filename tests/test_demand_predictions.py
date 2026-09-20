"""Testes da camada de previsões do GLM no Unity Catalog (`demand_predictions`).

A montagem dos quadros é lógica pura de pandas. Para a escrita, o `RecordingSpark`
do conftest guarda o quadro e o schema recebidos por `createDataFrame` e a cadeia
`.write.format("delta")...saveAsTable` numa lista, sem sessão Spark nem JVM. O código
de `_write`, `write_forecast_*` e `read_features` que está sob teste roda inteiro.
"""

import datetime as dt

import numpy as np
import pandas as pd
import pytest
from pyspark.sql.types import BooleanType, DateType, DoubleType, IntegerType, StringType, TimestampType

from src.analytics_ai.demand_glm import BASELINE_COL, decompose_months
from src.analytics_ai.demand_predictions import (
    FORECAST_3M_SCHEMA,
    FORECAST_MENSAL_SCHEMA,
    build_forecast_3m_frame,
    build_forecast_mensal_frame,
    read_features,
    write_forecast_3m,
    write_forecast_mensal,
)
from src.analytics_ai.ml_config import MlModelConfig

TRAINED_AT = dt.datetime(2026, 5, 20, 12, 30, 45)
CONFIG = MlModelConfig(
    catalog="cat",
    schema="sch",
    features_table="feats",
    forecast_table="f3m",
    forecast_monthly_table="fmes",
)


# ── Dados ───────────────────────────────────────────────────────────


def _panel(n=3, cutoff=dt.date(2026, 2, 1)):
    return pd.DataFrame(
        {
            "cutoff": [cutoff] * n,
            "sk_product": [100 + i for i in range(n)],
            "sku": [f"SKU{i}" for i in range(n)],
            "sk_location": [7] * n,
            "location_name": ["Loja Sul"] * n,
            "category_name": [f"Cat{i % 2}" for i in range(n)],
            BASELINE_COL: [2.0 + i for i in range(n)],
            "target_3m": [1.0, np.nan, 5.0][:n],
            "is_target_complete": [True, False, True][:n],
            "pred_glm": [1.5, 2.5, 3.5][:n],
            "seasonal_index_month_plus1": [1.0] * n,
            "seasonal_index_month_plus2": [1.2] * n,
            "seasonal_index_month_plus3": [0.8] * n,
        }
    )


# ── Schemas ─────────────────────────────────────────────────────────


def test_forecast_3m_schema_contract():
    fields = [(f.name, type(f.dataType), f.nullable) for f in FORECAST_3M_SCHEMA.fields]
    assert fields == [
        ("model_name", StringType, False),
        ("model_family", StringType, False),
        ("model_power", DoubleType, True),
        ("model_alpha", DoubleType, True),
        ("split_name", StringType, False),
        ("cutoff", DateType, False),
        ("sk_product", StringType, False),
        ("sku", StringType, True),
        ("sk_location", StringType, False),
        ("location_name", StringType, True),
        ("category_name", StringType, True),
        ("pred_total_3m", DoubleType, False),
        ("baseline_pred_3m", DoubleType, True),
        ("target_3m", DoubleType, True),
        ("is_target_complete", BooleanType, False),
        ("trained_at", TimestampType, False),
    ]


def test_forecast_mensal_schema_contract():
    fields = [(f.name, type(f.dataType), f.nullable) for f in FORECAST_MENSAL_SCHEMA.fields]
    assert fields == [
        ("model_name", StringType, False),
        ("sk_product", StringType, False),
        ("sku", StringType, True),
        ("sk_location", StringType, False),
        ("location_name", StringType, True),
        ("cutoff", DateType, False),
        ("mes_previsto", DateType, False),
        ("horizonte_mes", IntegerType, False),
        ("demanda_prevista", DoubleType, False),
        ("demanda_prevista_3m", DoubleType, False),
        ("share_sazonal", DoubleType, False),
        ("generated_at", TimestampType, False),
    ]


# ── build_forecast_3m_frame ─────────────────────────────────────────


def _build_3m(frame=None, **overrides):
    args = dict(
        pred_col="pred_glm",
        model_name="glm_poisson",
        family="poisson",
        power=None,
        alpha=0.0,
        split_name="teste",
        trained_at=TRAINED_AT,
    )
    args.update(overrides)
    return build_forecast_3m_frame(_panel() if frame is None else frame, **args)


def test_3m_frame_has_exactly_the_schema_columns_in_order():
    out = _build_3m()
    assert list(out.columns) == [f.name for f in FORECAST_3M_SCHEMA.fields]


def test_3m_frame_values_and_types():
    out = _build_3m()
    assert out["model_name"].tolist() == ["glm_poisson"] * 3
    assert out["model_family"].tolist() == ["poisson"] * 3
    assert out["model_power"].isna().all()  # Poisson não tem power
    assert out["model_alpha"].tolist() == [0.0] * 3
    assert out["split_name"].tolist() == ["teste"] * 3
    assert out["cutoff"].tolist() == [dt.date(2026, 2, 1)] * 3
    assert out["sk_product"].tolist() == ["100", "101", "102"]  # chaves viram texto
    assert out["sk_location"].tolist() == ["7"] * 3
    assert out["sku"].tolist() == ["SKU0", "SKU1", "SKU2"]
    assert out["pred_total_3m"].tolist() == [1.5, 2.5, 3.5]
    assert out["baseline_pred_3m"].tolist() == [2.0, 3.0, 4.0]
    assert out["target_3m"].tolist()[0] == 1.0 and np.isnan(out["target_3m"].iloc[1])
    assert out["is_target_complete"].tolist() == [True, False, True]
    assert out["is_target_complete"].dtype == bool
    assert out["pred_total_3m"].dtype == np.float64
    assert out["trained_at"].tolist() == [TRAINED_AT] * 3


def test_3m_frame_tweedie_metadata_and_custom_prediction_column():
    frame = _panel().rename(columns={"pred_glm": "minha_previsao"})
    out = _build_3m(frame, pred_col="minha_previsao", family="tweedie", power=1.3, alpha=0.01)
    assert out["model_family"].unique().tolist() == ["tweedie"]
    assert out["model_power"].tolist() == [1.3] * 3
    assert out["model_alpha"].tolist() == [0.01] * 3
    assert out["pred_total_3m"].tolist() == [1.5, 2.5, 3.5]


def test_3m_frame_resets_the_index_and_keeps_row_order():
    frame = _panel(3).iloc[[2, 0]]  # índice 2, 0
    out = _build_3m(frame)
    assert list(out.index) == [0, 1]
    assert out["sk_product"].tolist() == ["102", "100"]
    assert out["pred_total_3m"].tolist() == [3.5, 1.5]


def test_3m_frame_does_not_modify_the_source_panel():
    frame = _panel()
    antes = frame.copy()
    _build_3m(frame)
    pd.testing.assert_frame_equal(frame, antes)


def test_3m_frame_missing_source_column_is_a_key_error():
    with pytest.raises(KeyError):
        _build_3m(_panel().drop(columns=["category_name"]))


def test_3m_frame_of_empty_panel_is_empty_with_all_columns():
    out = _build_3m(_panel().iloc[0:0])
    assert out.empty
    assert list(out.columns) == [f.name for f in FORECAST_3M_SCHEMA.fields]


# ── build_forecast_mensal_frame ─────────────────────────────────────


def _monthly(frame=None):
    frame = _panel() if frame is None else frame
    return decompose_months(frame, "pred_glm")


def test_monthly_frame_has_exactly_the_schema_columns_in_order():
    out = build_forecast_mensal_frame(_monthly(), "pred_glm", "glm_poisson", TRAINED_AT)
    assert list(out.columns) == [f.name for f in FORECAST_MENSAL_SCHEMA.fields]


def test_monthly_frame_values_types_and_sums():
    out = build_forecast_mensal_frame(_monthly(), "pred_glm", "glm_poisson", TRAINED_AT)
    assert len(out) == 9  # 3 séries x 3 meses
    first = out[(out["sk_product"] == "100") & (out["horizonte_mes"] == 1)].iloc[0]
    # Índices 1,0 / 1,2 / 0,8 somam 3: o mês +1 recebe 1/3 do total de 1,5.
    assert first["share_sazonal"] == pytest.approx(1 / 3)
    assert first["demanda_prevista"] == pytest.approx(0.5)
    assert first["demanda_prevista_3m"] == 1.5
    assert first["mes_previsto"] == dt.date(2026, 3, 1)
    assert first["cutoff"] == dt.date(2026, 2, 1)
    assert first["generated_at"] == TRAINED_AT
    assert out["horizonte_mes"].dtype == np.int32
    assert out["sk_product"].map(type).eq(str).all()
    # Os três meses de cada série somam o total previsto.
    soma = out.groupby("sk_product")["demanda_prevista"].sum()
    esperado = out.groupby("sk_product")["demanda_prevista_3m"].first()
    np.testing.assert_allclose(soma.to_numpy(), esperado.to_numpy())
    assert (out["model_name"] == "glm_poisson").all()


def test_monthly_frame_uses_the_named_prediction_column():
    frame = _panel().rename(columns={"pred_glm": "outra"})
    mensal = decompose_months(frame, "outra")
    out = build_forecast_mensal_frame(mensal, "outra", "m", TRAINED_AT)
    assert out["demanda_prevista_3m"].isin([1.5, 2.5, 3.5]).all()


# ── read_features ───────────────────────────────────────────────────


def test_read_features_reads_the_configured_table_and_clears_connect_attrs(make_recording_spark, fake_table):
    tabela = pd.DataFrame({"a": [1, 2]})
    spark = make_recording_spark({"cat.sch.feats": fake_table(tabela)})
    frame = read_features(spark, CONFIG)
    assert spark.table_requests == ["cat.sch.feats"]
    pd.testing.assert_frame_equal(frame, tabela)
    assert frame.attrs == {}  # sem metadados não serializáveis pendurados


def test_read_features_defaults_to_the_environment_configuration(monkeypatch, make_recording_spark, fake_table):
    monkeypatch.setenv("ML_CATALOG", "prod_lh_nautical")
    monkeypatch.setenv("ML_SCHEMA", "ml")
    monkeypatch.setenv("ML_FEATURES_TABLE", "ml_features_produto_loja_mes")
    spark = make_recording_spark({"prod_lh_nautical.ml.ml_features_produto_loja_mes": fake_table(pd.DataFrame({"a": [1]}))})
    read_features(spark)
    assert spark.table_requests == ["prod_lh_nautical.ml.ml_features_produto_loja_mes"]


# ── Escrita ─────────────────────────────────────────────────────────


def test_write_forecast_3m_replaces_only_the_model_partition(recorder):
    frame = _build_3m()
    written = write_forecast_3m(recorder, frame, "glm_poisson", CONFIG)
    assert written == 3
    assert len(recorder.created) == 1
    assert recorder.created[0].write.calls == [
        ("format", "delta"),
        ("mode", "overwrite"),
        ("option", "replaceWhere", "model_name = 'glm_poisson'"),
        ("option", "overwriteSchema", "true"),
        ("partitionBy", "model_name"),
        ("saveAsTable", "cat.sch.f3m"),
    ]


def test_write_forecast_3m_sends_the_explicit_schema_and_only_its_columns_in_order(recorder):
    frame = _build_3m()
    write_forecast_3m(recorder, frame, "glm_poisson", CONFIG)
    enviado = recorder.created[0]
    assert enviado.schema is FORECAST_3M_SCHEMA  # sem inferência: date continua date, alvo nulo continua double
    assert list(enviado.data.columns) == [f.name for f in FORECAST_3M_SCHEMA.fields]
    assert enviado.data["sk_product"].tolist() == ["100", "101", "102"]
    assert enviado.data["cutoff"].tolist() == [dt.date(2026, 2, 1)] * 3
    assert enviado.data["pred_total_3m"].tolist() == [1.5, 2.5, 3.5]
    assert enviado.data["is_target_complete"].tolist() == [True, False, True]
    assert enviado.data["trained_at"].iloc[0] == TRAINED_AT


def test_write_forecast_3m_keeps_an_all_null_target_typed_as_double(recorder):
    frame = _build_3m(_panel().assign(target_3m=np.nan, is_target_complete=False))
    write_forecast_3m(recorder, frame, "glm_poisson", CONFIG)
    assert recorder.created[0].schema["target_3m"].dataType == DoubleType()
    assert recorder.created[0].data["target_3m"].isna().all()


def test_write_forecast_mensal_targets_the_monthly_table(recorder):
    frame = build_forecast_mensal_frame(_monthly(), "pred_glm", "glm_poisson", TRAINED_AT)
    written = write_forecast_mensal(recorder, frame, "glm_poisson", CONFIG)
    assert written == 9
    calls = recorder.created[0].write.calls
    assert calls[-1] == ("saveAsTable", "cat.sch.fmes")
    assert ("option", "replaceWhere", "model_name = 'glm_poisson'") in calls
    assert recorder.created[0].schema is FORECAST_MENSAL_SCHEMA
    out = recorder.created[0].data
    assert out["horizonte_mes"].tolist()[:3] == [1, 2, 3]
    assert out["mes_previsto"].iloc[0] == dt.date(2026, 3, 1)


def test_write_defaults_to_the_environment_configuration(recorder, monkeypatch):
    monkeypatch.setenv("ML_CATALOG", "prod_lh_nautical")
    monkeypatch.delenv("ML_SCHEMA", raising=False)
    monkeypatch.delenv("ML_FORECAST_TABLE", raising=False)
    write_forecast_3m(recorder, _build_3m(), "glm_poisson")
    assert recorder.created[0].write.calls[-1] == ("saveAsTable", "prod_lh_nautical.ml.ml_forecast_demanda_3m")


def test_write_ignores_extra_columns_and_column_order(recorder):
    frame = _build_3m()
    frame = frame[list(reversed(frame.columns))].assign(coluna_extra=1)
    write_forecast_3m(recorder, frame, "glm_poisson", CONFIG)
    assert list(recorder.created[0].data.columns) == [f.name for f in FORECAST_3M_SCHEMA.fields]


def test_write_rejects_frames_missing_schema_columns(recorder):
    frame = _build_3m().drop(columns=["pred_total_3m", "trained_at"])
    with pytest.raises(ValueError, match="pred_total_3m"):
        write_forecast_3m(recorder, frame, "glm_poisson", CONFIG)
    assert recorder.created == []  # nada foi enviado


def test_write_rejects_model_names_that_would_break_the_replace_where_predicate(recorder):
    frame = _build_3m(model_name="o'brien")
    with pytest.raises(ValueError, match="model_name"):
        write_forecast_3m(recorder, frame, "o'brien", CONFIG)
    assert recorder.created == []


def test_write_rejects_rows_from_a_different_model_than_the_partition(recorder):
    frame = _build_3m(model_name="outro_modelo")
    with pytest.raises(ValueError, match="model_name"):
        write_forecast_3m(recorder, frame, "glm_poisson", CONFIG)
    assert recorder.created == []


def test_write_refuses_an_empty_frame_instead_of_wiping_the_model_partition(recorder):
    frame = _build_3m(_panel().iloc[0:0])
    with pytest.raises(ValueError, match="vazio"):
        write_forecast_3m(recorder, frame, "glm_poisson", CONFIG)
    assert recorder.created == []
