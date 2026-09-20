"""Testes do executável do GLM (`run_demand_glm`): argumentos, fluxo e gravação.

O fluxo roda inteiro: leitura das features, split, ajuste, previsão, decomposição e
gravação. Só as bordas são falsas: a sessão Spark do Databricks (`build_spark_session`)
vira um `RecordingSpark` (guarda o quadro e o schema enviados e a cadeia de escrita, sem
Spark) e a tabela de features é um pandas sintético. Nada toca o Databricks.
"""

import datetime as dt
import importlib
import sys
import types
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.analytics_ai.demand_common import add_months

FEATURES_TABLE = "dev_lh_nautical.ml.ml_features_produto_loja_mes"
N_SERIES = 6


def _features_panel(first=dt.date(2022, 1, 1), last=dt.date(2026, 8, 1), last_complete=dt.date(2026, 5, 1), seed=0):
    """Tabela `ml_features_produto_loja_mes` sintética: 6 séries por mês de corte."""
    rng = np.random.default_rng(seed)
    rows = []
    cutoff = first
    while cutoff <= last:
        for s in range(N_SERIES):
            level = 2.0 + s
            base = level / 12 * 3.6
            rows.append(
                {
                    "cutoff": cutoff,
                    "sk_product": f"p{s}",
                    "sku": f"SKU{s}",
                    "sk_location": f"l{s % 2}",
                    "location_name": f"Loja {s % 2}",
                    "category_name": f"Cat{s % 3}",
                    "categoria_local_avg_12m": level + 1,
                    "season_sum_next_3m": 3.6,
                    "trend_factor": 1.05,
                    "sum_12m": float(rng.poisson(level)),
                    "sum_3m": float(rng.poisson(level / 4)),
                    "produto_locais_avg_12m": level,
                    "categoria_local_n_series": float(rng.integers(3, 9)),
                    "produto_locais_n_locations": float(rng.integers(1, 5)),
                    "months_with_sale_12m": float(rng.integers(0, 13)),
                    "months_since_last_sale": np.nan if rng.random() < 0.05 else float(rng.integers(0, 6)),
                    "is_stopped_12m": bool(rng.random() < 0.1),
                    "seasonal_index_month_plus1": 1.0,
                    "seasonal_index_month_plus2": 1.2,
                    "seasonal_index_month_plus3": 0.8,
                    "trend_ready": True,
                    "is_target_complete": cutoff <= last_complete,
                    "baseline_pred_categoria_local_idx_trend": base,
                    "target_3m": float(rng.poisson(base)) if cutoff <= last_complete else np.nan,
                }
            )
        cutoff = add_months(cutoff, 1)
    return pd.DataFrame(rows)


@pytest.fixture()
def glm_env(monkeypatch, make_recording_spark, fake_table):
    """Carrega `run_demand_glm` com uma `build_spark_session` falsa que devolve o Spark registrador."""
    features = _features_panel()
    spark = make_recording_spark({FEATURES_TABLE: fake_table(features)})
    fake_utils = types.ModuleType("src.ingestion.utils")
    fake_utils.build_spark_session = lambda: spark
    monkeypatch.setitem(sys.modules, "src.ingestion.utils", fake_utils)
    monkeypatch.delitem(sys.modules, "src.analytics_ai.run_demand_glm", raising=False)
    for variable in ("ML_CATALOG", "ML_SCHEMA", "ML_FEATURES_TABLE", "ML_FORECAST_TABLE", "ML_FORECAST_MONTHLY_TABLE"):
        monkeypatch.delenv(variable, raising=False)
    module = importlib.import_module("src.analytics_ai.run_demand_glm")
    yield SimpleNamespace(module=module, spark=spark, features=features)
    sys.modules.pop("src.analytics_ai.run_demand_glm", None)


# ── parse_args ──────────────────────────────────────────────────────


def test_parse_args_defaults(glm_env):
    args = glm_env.module.parse_args([])
    assert args.model_name == "glm_poisson"
    assert args.step == "passo3_historico"
    assert args.family == "poisson"
    assert args.power == 1.3
    assert args.alpha == 0.0
    assert args.fit_on == "treino"
    assert args.dry_run is False


def test_parse_args_overrides(glm_env):
    args = glm_env.module.parse_args(
        ["--model-name", "m", "--step", "passo2_offset", "--family", "tweedie", "--power", "1.5", "--alpha", "0.01", "--fit-on", "completo", "--dry-run"]
    )
    assert (args.model_name, args.step, args.family, args.power, args.alpha, args.fit_on, args.dry_run) == (
        "m", "passo2_offset", "tweedie", 1.5, 0.01, "completo", True
    )


@pytest.mark.parametrize(
    "argv", [["--step", "passo9"], ["--family", "gamma"], ["--fit-on", "tudo"], ["--power", "abc"]]
)
def test_parse_args_rejects_invalid_values(glm_env, argv):
    with pytest.raises(SystemExit) as saida:
        glm_env.module.parse_args(argv)
    assert saida.value.code == 2


def test_step_choices_are_the_feature_steps(glm_env):
    from src.analytics_ai.demand_glm import FEATURE_STEPS

    for passo in FEATURE_STEPS:
        assert glm_env.module.parse_args(["--step", passo]).step == passo


# ── main: dry-run ───────────────────────────────────────────────────


def test_dry_run_reads_fits_prints_and_writes_nothing(glm_env, capsys):
    glm_env.module.main(["--dry-run"])
    saida = capsys.readouterr().out
    assert f"lendo {FEATURES_TABLE}" in saida
    assert glm_env.spark.table_requests == [FEATURES_TABLE]
    # 29 cortes de treino, 12 de validação, 12 de teste e 3 de inferência, 6 séries cada.
    assert "treino=174 validacao=72 teste=72 inferencia=18 descartadas=0" in saida
    assert "modelo 'glm_poisson' (poisson) treinado em 174 linhas" in saida
    assert "desempenho no teste" in saida
    assert "regua" in saida and "glm_poisson" in saida  # linhas do quadro comparativo
    assert "6 series x 3 meses = 18 linhas" in saida
    assert "--dry-run: nada gravado" in saida
    assert glm_env.spark.created == []


# ── main: gravação ──────────────────────────────────────────────────


def test_full_run_writes_both_forecast_tables_for_the_model_partition(glm_env, capsys):
    glm_env.module.main(["--model-name", "meu_glm"])
    saida = capsys.readouterr().out
    assert len(glm_env.spark.created) == 2
    tres_meses, mensal = glm_env.spark.created
    assert tres_meses.write.calls[-1] == ("saveAsTable", "dev_lh_nautical.ml.ml_forecast_demanda_3m")
    assert ("option", "replaceWhere", "model_name = 'meu_glm'") in tres_meses.write.calls
    assert mensal.write.calls[-1] == ("saveAsTable", "dev_lh_nautical.ml.ml_forecast_demanda_mensal")
    assert "gravadas 90 linhas em dev_lh_nautical.ml.ml_forecast_demanda_3m" in saida
    assert "gravadas 18 linhas em dev_lh_nautical.ml.ml_forecast_demanda_mensal" in saida

    tabela_3m = tres_meses.data
    assert len(tabela_3m) == 72 + 18  # linhas de teste + linhas de inferência
    assert (tabela_3m["model_name"] == "meu_glm").all()
    contagem = tabela_3m["split_name"].value_counts().to_dict()
    assert contagem == {"teste": 72, "inferencia": 18}
    teste = tabela_3m[tabela_3m["split_name"] == "teste"]
    assert teste["is_target_complete"].all() and teste["target_3m"].notna().all()
    assert set(teste["cutoff"]) == {add_months(dt.date(2025, 6, 1), k) for k in range(12)}
    inferencia = tabela_3m[tabela_3m["split_name"] == "inferencia"]
    assert (~inferencia["is_target_complete"]).all() and inferencia["target_3m"].isna().all()
    assert (tabela_3m["pred_total_3m"] >= 0).all() and tabela_3m["pred_total_3m"].notna().all()
    assert tabela_3m["model_power"].isna().all()  # Poisson

    tabela_mensal = mensal.data
    assert set(tabela_mensal["cutoff"]) == {dt.date(2026, 8, 1)}  # só o último corte de inferência
    assert set(tabela_mensal["mes_previsto"]) == {dt.date(2026, 9, 1), dt.date(2026, 10, 1), dt.date(2026, 11, 1)}
    assert len(tabela_mensal) == N_SERIES * 3
    soma = tabela_mensal.groupby("sk_product")["demanda_prevista"].sum().sort_index()
    total = tabela_mensal.groupby("sk_product")["demanda_prevista_3m"].first().sort_index()
    np.testing.assert_allclose(soma.to_numpy(), total.to_numpy())  # os três meses somam o total previsto


def test_tweedie_metadata_reaches_the_written_table(glm_env):
    glm_env.module.main(["--family", "tweedie", "--power", "1.5", "--alpha", "0.01", "--step", "passo2_offset"])
    tabela = glm_env.spark.created[0].data
    assert set(tabela["model_family"]) == {"tweedie"}
    assert set(tabela["model_power"]) == {1.5}
    assert set(tabela["model_alpha"]) == {0.01}


def test_fit_on_full_history_trains_on_every_labeled_cutoff_and_labels_seen_rows_as_training(glm_env, capsys):
    glm_env.module.main(["--fit-on", "completo"])
    saida = capsys.readouterr().out
    assert "treinado em 318 linhas" in saida  # 174 + 72 + 72
    assert "desempenho no teste" not in saida  # com o teste dentro do treino, a métrica seria enganosa
    tabela = glm_env.spark.created[0].data
    # O modelo já viu as linhas de teste: gravá-las como "teste" contaminaria a avaliação fora da amostra.
    assert set(tabela["split_name"]) == {"treino", "inferencia"}


def test_uses_the_configured_catalog_and_tables(glm_env, monkeypatch, fake_table):
    monkeypatch.setenv("ML_CATALOG", "prod_lh_nautical")
    monkeypatch.setenv("ML_FORECAST_TABLE", "minha_previsao")
    glm_env.spark.tables["prod_lh_nautical.ml.ml_features_produto_loja_mes"] = fake_table(glm_env.features)
    glm_env.module.main([])
    assert glm_env.spark.created[0].write.calls[-1] == ("saveAsTable", "prod_lh_nautical.ml.minha_previsao")
    assert glm_env.spark.created[1].write.calls[-1] == ("saveAsTable", "prod_lh_nautical.ml.ml_forecast_demanda_mensal")


def test_without_inference_rows_it_fails_before_writing_anything(glm_env, fake_table):
    completo = _features_panel(last=dt.date(2026, 5, 1))  # todos os cortes têm alvo
    glm_env.spark.tables[FEATURES_TABLE] = fake_table(completo)
    with pytest.raises(ValueError, match="inferência"):
        glm_env.module.main([])
    assert glm_env.spark.created == []
