"""Testes do XGBoost de demanda: contrato temporal, métricas, seleção na validação e o `run` completo."""

import datetime as dt
import sys
import warnings
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.analytics_ai.demand_common import add_months
from src.analytics_ai.demand_xgboost import (
    BASELINE,
    COLUMNS,
    FEATURE_SETS,
    FEATURES,
    MOVING_BASELINES,
    PARAMETER_CANDIDATES,
    TARGET,
    WINNING_PARAMETERS,
    Calibration,
    XgbParameters,
    _calibration_metrics,
    _fit,
    _fit_base_margin,
    _fit_residual,
    _fit_two_stage,
    _margin,
    add_moving_average_baselines,
    apply_calibration,
    evaluate,
    feature_table_name,
    load_panel,
    metric_table,
    predict_base_margin,
    predict_nonnegative,
    predict_residual,
    predict_two_stage,
    reconcile_to_baseline_total,
    reconstruct_residual,
    run,
    search_hyperparameters,
    select_calibration,
    select_residual_shift,
    select_two_stage_threshold,
    temporal_split,
)
from src.analytics_ai.ml_config import MlFeatureConfig


def synthetic_panel() -> pd.DataFrame:
    rows = []
    for month in range(80):
        cutoff = add_months(dt.date(2020, 1, 1), month)
        rows.append({
            "cutoff": cutoff,
            "sk_product": "p1",
            "sk_location": "l1",
            "is_target_complete": month <= 76,
            "trend_ready": month >= 23,
            "target_3m": 2.0 if month <= 76 else np.nan,
        })
    return pd.DataFrame(rows)


class DemandXgboostTests(unittest.TestCase):
    def test_last_twelve_labeled_cutoffs_are_test(self) -> None:
        split = temporal_split(synthetic_panel())
        self.assertEqual(len(split.test_cutoffs), 12)
        self.assertEqual(split.test_cutoffs[0], dt.date(2025, 6, 1))
        self.assertEqual(split.test_cutoffs[-1], dt.date(2026, 5, 1))
        self.assertEqual(set(split.test["cutoff"]), set(split.test_cutoffs))

    def test_training_labels_are_available_before_validation_and_test(self) -> None:
        split = temporal_split(synthetic_panel())
        self.assertTrue(split.train["is_target_complete"].all())
        self.assertTrue(split.final_train["is_target_complete"].all())
        self.assertLessEqual(add_months(split.train["cutoff"].max(), 3), split.validation_cutoffs[0])
        self.assertLessEqual(add_months(split.final_train["cutoff"].max(), 3), split.test_cutoffs[0])
        self.assertEqual(split.train["cutoff"].max(), dt.date(2024, 9, 1))
        self.assertEqual(split.final_train["cutoff"].max(), dt.date(2025, 3, 1))

    def test_negative_predictions_are_clipped_without_training(self) -> None:
        class FakeModel:
            def predict(self, matrix):
                return np.array([-2.0, 3.0])

        fake_xgboost = SimpleNamespace(DMatrix=lambda matrix: matrix)
        features = pd.DataFrame({
            "categoria_local_avg_12m": [1.0, 1.0],
            "season_sum_next_3m": [3.0, 3.0],
            "growth_12m": [1.1, 1.1],
            "trend_factor": [1.1, 1.1],
            BASELINE: [1.0, 1.0],
        })
        with patch.dict(sys.modules, {"xgboost": fake_xgboost}):
            self.assertEqual(predict_nonnegative(FakeModel(), features).tolist(), [0.0, 3.0])

    def test_metrics_compare_model_and_baseline(self) -> None:
        frame = pd.DataFrame({
            "cutoff": [dt.date(2026, 5, 1)] * 2,
            "sk_product": ["p1", "p2"],
            "category_name": ["cat"] * 2,
            "sk_location": ["l1"] * 2,
            "target_3m": [Decimal("2.00"), Decimal("4.00")],
            "pred_xgboost": [1.0, 5.0],
            BASELINE: [Decimal("2.00"), Decimal("2.00")],
        })
        result = metric_table(frame)
        self.assertEqual(set(result.index), {"XGBoost puro", "Régua"})
        self.assertAlmostEqual(result.loc["XGBoost puro", "mae"], 1.0)
        self.assertAlmostEqual(result.loc["XGBoost puro", "rmse"], 1.0)
        self.assertAlmostEqual(result.loc["XGBoost puro", "wape"], 2 / 6, delta=0.0001)
        self.assertAlmostEqual(result.loc["XGBoost puro", "vies"], 0.0)
        self.assertAlmostEqual(result.loc["Régua", "mae"], 1.0)
        self.assertAlmostEqual(result.loc["Régua", "rmse"], np.sqrt(2))
        self.assertAlmostEqual(result.loc["Régua", "wape"], 2 / 6, delta=0.0001)
        self.assertAlmostEqual(result.loc["Régua", "vies"], -2 / 6, delta=0.0001)

    def test_global_multiplier_is_fitted_only_from_validation_totals(self) -> None:
        validation = pd.DataFrame({
            "cutoff": [dt.date(2025, 1, 1)] * 2,
            "category_name": ["a", "b"],
            "sk_location": ["l1", "l1"],
            "target_3m": [4.0, 4.0],
            "pred_xgboost": [2.0, 2.0],
            BASELINE: [1.0, 1.0],
        })
        chosen, candidates = select_calibration(validation)
        self.assertEqual(len(candidates), 23)
        self.assertEqual(chosen.name, "XGBoost × fator global")
        self.assertAlmostEqual(chosen.multiplier, 2.0)
        self.assertEqual(apply_calibration(validation, chosen).tolist(), [4.0, 4.0])
        self.assertEqual(sorted(candidates.loc[candidates.alternativa.str.startswith("Mistura"), "peso_xgboost"].round(2)),
                         [weight / 100 for weight in range(0, 101, 5)])

    def test_convex_mix_can_win_validation_score(self) -> None:
        validation = pd.DataFrame({
            "cutoff": [dt.date(2025, 1, 1)] * 2,
            "category_name": ["a", "b"],
            "sk_location": ["l1", "l1"],
            "target_3m": [10.0, 10.0],
            "pred_xgboost": [0.0, 20.0],
            BASELINE: [20.0, 0.0],
        })
        chosen, candidates = select_calibration(validation)
        self.assertEqual(chosen, Calibration("Mistura 50% XGBoost", 0.5))
        self.assertAlmostEqual(candidates.iloc[0].pontuacao, 0.0)

    def test_reconciliation_preserves_xgboost_proportions_and_baseline_total(self) -> None:
        frame = pd.DataFrame({
            "cutoff": [dt.date(2025, 1, 1)] * 3,
            "category_name": ["cat"] * 3,
            "sk_location": ["l1"] * 3,
            "sk_product": ["p1", "p2", "p3"],
            "pred_xgboost": [8.0, 2.0, 1.0],
            BASELINE: [6.0, 3.0, 3.0],
        })
        result = reconcile_to_baseline_total(frame)
        self.assertAlmostEqual(result.sum(), 12.0)
        self.assertAlmostEqual(result[0] / result[1], 4.0)

    def test_reconciliation_uses_baseline_when_xgboost_group_is_zero(self) -> None:
        frame = pd.DataFrame({
            "cutoff": [dt.date(2025, 1, 1)] * 2,
            "category_name": ["cat"] * 2,
            "sk_location": ["l1"] * 2,
            "sk_product": ["p1", "p2"],
            "pred_xgboost": [0.0, 0.0],
            BASELINE: [4.0, 6.0],
        })
        np.testing.assert_allclose(reconcile_to_baseline_total(frame), [4.0, 6.0])

    def test_historical_feature_sets_are_incremental(self) -> None:
        current = set(FEATURE_SETS["modelo_atual"])
        own_series = set(FEATURE_SETS["modelo_atual_historico_serie"])
        other_stores = set(FEATURE_SETS["modelo_atual_historico_outras_lojas"])
        self.assertTrue(current < own_series < other_stores)
        self.assertIn("sum_3m", own_series)
        self.assertIn("sum_12m", own_series)
        self.assertIn("months_with_sale_12m", own_series)
        self.assertIn("months_since_last_sale", own_series)
        self.assertIn("produto_locais_avg_12m", other_stores)
        self.assertIn("produto_locais_n_locations", other_stores)

    def test_moving_average_baselines_match_notebook_formulas(self) -> None:
        frame = pd.DataFrame({
            "sum_3m": [6.0], "sum_12m": [24.0], "season_sum_next_3m": [3.6],
            "produto_locais_avg_12m": [12.0], "categoria_local_avg_12m": [18.0],
        })
        result = add_moving_average_baselines(frame)
        self.assertAlmostEqual(result.loc[0, "pred_mm3"], 6.0)
        self.assertAlmostEqual(result.loc[0, "pred_mm12"], 6.0)
        self.assertAlmostEqual(result.loc[0, "pred_mm12_idx"], 7.2)
        self.assertAlmostEqual(result.loc[0, "pred_produto_idx"], 3.6)
        self.assertAlmostEqual(result.loc[0, "pred_categoria_loja_idx"], 5.4)

    def test_residual_log1p_reconstruction_handles_zero_baseline_and_target(self) -> None:
        frame = pd.DataFrame({BASELINE: [0.0, 4.0]})
        result = reconstruct_residual(frame, np.array([0.0, 0.0]))
        np.testing.assert_allclose(result, [0.0, 4.0])
        shifted = reconstruct_residual(frame, np.array([np.log1p(3.0), -np.log1p(4.0)]))
        np.testing.assert_allclose(shifted, [3.0, 0.0])

    def test_base_margin_zero_is_finite(self) -> None:
        frame = pd.DataFrame({BASELINE: [0.0, 2.0]})
        self.assertTrue(np.isfinite(_margin(frame, 1e-6)).all())

    def test_two_stage_threshold_reports_f1_metrics(self) -> None:
        frame = pd.DataFrame({TARGET: [0.0, 2.0, 3.0, 0.0]})
        threshold, metrics = select_two_stage_threshold(frame, np.array([0.1, 0.8, 0.7, 0.2]))
        self.assertGreaterEqual(threshold, 0.2)
        self.assertIn("precision", metrics.columns)
        self.assertIn("recall", metrics.columns)
        self.assertIn("f1", metrics.columns)

    def test_hyperparameter_search_uses_only_validation(self) -> None:
        split = temporal_split(synthetic_panel())
        self.assertEqual(len(PARAMETER_CANDIDATES), 12)
        for field in ("max_depth", "min_child_weight", "learning_rate", "n_estimators", "subsample", "reg_lambda"):
            self.assertGreater(len({getattr(item, field) for item in PARAMETER_CANDIDATES}), 1)

        trained_on = []
        evaluated_on = []
        def fake_fit(frame, parameters):
            trained_on.append(frame)
            return parameters

        def fake_evaluate(model, frame):
            evaluated_on.append(frame)
            return None, pd.DataFrame({
                "model": [PARAMETER_CANDIDATES.index(model)],
                "target_3m": [2.0],
                "pred_xgboost": [1.0],
                BASELINE: [2.0],
            })

        def fake_select(predictions):
            index = int(predictions.loc[0, "model"])
            score = 0.1 if index == 4 else 1.0 + index
            return Calibration("XGBoost puro", 1.0), pd.DataFrame([{
                "wape_categoria_local": score / 3,
                "wape_local": score / 3,
                "vies": score / 3,
                "pontuacao": score,
            }])

        with patch("src.analytics_ai.demand_xgboost._fit", side_effect=fake_fit), \
             patch("src.analytics_ai.demand_xgboost.evaluate", side_effect=fake_evaluate), \
             patch("src.analytics_ai.demand_xgboost.select_calibration", side_effect=fake_select):
            best, calibration, ranking, predictions = search_hyperparameters(split)

        self.assertEqual(best, PARAMETER_CANDIDATES[4])
        self.assertEqual(calibration.name, "XGBoost puro")
        self.assertEqual(len(ranking), len(PARAMETER_CANDIDATES))
        self.assertEqual(int(predictions.loc[0, "model"]), 4)
        self.assertTrue(all(frame is split.train for frame in trained_on))
        self.assertTrue(all(frame is split.validation for frame in evaluated_on))


# ── Testes adicionais (pytest) ──────────────────────────────────────


def _xgb_frame(**columns):
    """Quadro mínimo com as colunas de `evaluate`/`metric_table`."""
    base = {
        "cutoff": [dt.date(2025, 1, 1)] * 3,
        "sk_product": ["p1", "p2", "p3"],
        "sk_location": ["l1"] * 3,
        "category_name": ["a"] * 3,
        TARGET: [2.0, 4.0, 0.0],
        BASELINE: [1.0, 2.0, 3.0],
        "pred_xgboost": [2.0, 3.0, 1.0],
    }
    base.update(columns)
    return pd.DataFrame(base)


def test_feature_definitions_are_consistent():
    assert FEATURES[-1] == BASELINE
    for name, features in FEATURE_SETS.items():
        assert len(set(features)) == len(features), f"{name} repete feature"
    assert len(COLUMNS) == len(set(COLUMNS))  # sem colunas duplicadas na consulta
    for features in FEATURE_SETS.values():
        assert set(features) <= set(COLUMNS)
    for obrigatoria in ("cutoff", "sk_product", "sk_location", "category_name", "is_target_complete", "trend_ready", TARGET):
        assert obrigatoria in COLUMNS
    assert WINNING_PARAMETERS == PARAMETER_CANDIDATES[6]
    assert len({(p.max_depth, p.min_child_weight, p.learning_rate, p.n_estimators, p.subsample, p.reg_lambda) for p in PARAMETER_CANDIDATES}) == 12


def test_feature_table_name_uses_catalog_and_schema_from_config():
    config = MlFeatureConfig.from_environment_monthly()
    assert feature_table_name(config) == f"{config.catalog}.{config.schema}.ml_features_produto_loja_mes"


# ── load_panel ──────────────────────────────────────────────────────


class _FakeTable:
    def __init__(self, frame):
        self.frame = frame
        self.selected = None

    def select(self, *columns):
        self.selected = columns
        return self

    def toPandas(self):  # noqa: N802 - nome da API do Spark
        return self.frame[list(self.selected)].copy()


class _FakeSpark:
    def __init__(self, table):
        self._table = table
        self.requested = None

    def table(self, name):
        self.requested = name
        return self._table


def test_load_panel_selects_only_needed_columns_and_converts_decimals_to_float(demand_panel):
    source = demand_panel.copy()
    source["extra_que_nao_entra"] = 1
    for column in (TARGET, "sum_3m", "growth_12m"):
        source[column] = source[column].map(lambda v: None if pd.isna(v) else Decimal(str(round(v, 4))))
    table = _FakeTable(source)
    config = MlFeatureConfig.from_environment_monthly()
    spark = _FakeSpark(table)
    panel = load_panel(spark, config)
    assert spark.requested == feature_table_name(config)
    assert table.selected == COLUMNS
    assert list(panel.columns) == list(COLUMNS)
    for column in (TARGET, "sum_3m", "growth_12m", "is_stopped_12m", "sum_12m"):
        assert panel[column].dtype == np.float64, column
    assert panel[TARGET].isna().sum() == source[TARGET].isna().sum()  # os alvos nulos da inferência continuam nulos
    assert panel["sk_product"].tolist() == demand_panel["sk_product"].tolist()  # chaves intactas


def test_load_panel_defaults_to_the_monthly_environment_config(demand_panel, monkeypatch):
    monkeypatch.setenv("ML_CATALOG", "prod_lh_nautical")
    monkeypatch.setenv("ML_SCHEMA", "ml")
    spark = _FakeSpark(_FakeTable(demand_panel))
    load_panel(spark)
    assert spark.requested == "prod_lh_nautical.ml.ml_features_produto_loja_mes"


# ── temporal_split ──────────────────────────────────────────────────


def test_temporal_split_contiguous_windows_and_no_overlap():
    split = temporal_split(synthetic_panel())
    assert len(split.validation_cutoffs) == 6
    assert split.validation_cutoffs[-1] == add_months(split.test_cutoffs[0], -1)  # a validação termina no mês anterior ao teste
    assert set(split.validation["cutoff"]).isdisjoint(set(split.test["cutoff"]))
    assert split.train["cutoff"].max() < split.validation["cutoff"].min()
    assert split.final_train["cutoff"].max() < split.test["cutoff"].min()
    # O treino final inclui a validação até o embargo de 3 meses antes do teste.
    assert split.final_train["cutoff"].max() == add_months(split.test_cutoffs[0], -3)
    assert split.train["cutoff"].max() == add_months(split.validation_cutoffs[0], -3)


def test_temporal_split_uses_only_labeled_rows_with_trend():
    panel = synthetic_panel()
    split = temporal_split(panel)
    for part in (split.train, split.validation, split.final_train, split.test):
        assert part["is_target_complete"].all() and part["trend_ready"].all()
    assert split.train["cutoff"].min() == add_months(dt.date(2020, 1, 1), 23)  # antes disso trend_ready é falso


def test_temporal_split_custom_window_sizes():
    split = temporal_split(synthetic_panel(), validation_months=3, test_months=4)
    assert len(split.validation_cutoffs) == 3 and len(split.test_cutoffs) == 4
    assert split.test_cutoffs[-1] == dt.date(2026, 5, 1)
    assert split.validation_cutoffs[-1] == add_months(split.test_cutoffs[0], -1)


def test_temporal_split_does_not_modify_the_input():
    panel = synthetic_panel()
    antes = panel.copy()
    temporal_split(panel)
    pd.testing.assert_frame_equal(panel, antes)


@pytest.mark.parametrize("kwargs", [{"validation_months": 0}, {"test_months": 0}, {"validation_months": -2}])
def test_temporal_split_rejects_non_positive_windows(kwargs):
    with pytest.raises(ValueError, match="positivos"):
        temporal_split(synthetic_panel(), **kwargs)


def test_temporal_split_without_labeled_cutoffs_is_an_error():
    panel = synthetic_panel().assign(is_target_complete=False)
    with pytest.raises(ValueError, match="rotulados"):
        temporal_split(panel)


def test_temporal_split_missing_validation_or_test_cutoffs_is_an_error():
    panel = synthetic_panel()
    buraco = panel[panel["cutoff"] != dt.date(2025, 9, 1)]  # cai no meio dos 12 cortes de teste
    with pytest.raises(ValueError, match="Faltam cortes"):
        temporal_split(buraco)


def test_temporal_split_insufficient_history_is_an_error():
    panel = synthetic_panel()
    # Só a partir do 1º corte da validação: validação e teste existem, mas o treino (que termina 3 meses antes) fica vazio.
    curto = panel[panel["cutoff"] >= add_months(dt.date(2020, 1, 1), 59)].copy()
    with pytest.raises(ValueError, match="Histórico insuficiente"):
        temporal_split(curto)


def test_temporal_split_treats_null_flags_as_false_without_warnings():
    panel = synthetic_panel()
    panel["is_target_complete"] = panel["is_target_complete"].astype(object)
    panel["trend_ready"] = panel["trend_ready"].astype(object)
    panel.loc[panel.index[:3], "is_target_complete"] = None
    panel.loc[panel.index[5:8], "trend_ready"] = None
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        split = temporal_split(panel)
    assert len(split.test_cutoffs) == 12


def test_temporal_split_accepts_timestamp_cutoffs():
    panel = synthetic_panel()
    panel["cutoff"] = pd.to_datetime(panel["cutoff"])
    split = temporal_split(panel)
    assert split.test_cutoffs[0] == dt.date(2025, 6, 1)


# ── Modelos e previsões com xgboost de verdade (dados minúsculos) ──


def _training_frame(n=200, seed=0):
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({name: rng.uniform(0.5, 3.0, n) for name in FEATURES})
    frame[TARGET] = rng.poisson(frame[BASELINE]).astype(float)
    return frame


def test_fit_and_predict_nonnegative_shape_and_reproducibility():
    frame = _training_frame()
    parametros = XgbParameters(2, 5, 0.1, 20, 0.9, 5.0)
    a = predict_nonnegative(_fit(frame, parametros), frame)
    b = predict_nonnegative(_fit(frame, parametros), frame)
    assert a.shape == (len(frame),)
    assert (a >= 0).all() and np.isfinite(a).all()
    np.testing.assert_array_equal(a, b)  # semente fixa


def test_fit_uses_the_requested_feature_subset():
    frame = _training_frame()
    parametros = XgbParameters(2, 5, 0.1, 10, 0.9, 5.0)
    so_baseline = ("categoria_local_avg_12m", BASELINE)
    modelo = _fit(frame, parametros, so_baseline)
    assert modelo.feature_names == list(so_baseline)
    with pytest.raises(KeyError):
        predict_nonnegative(modelo, frame.drop(columns=[BASELINE]), so_baseline)


def test_base_margin_model_trained_on_the_baseline_itself_reproduces_it():
    rng = np.random.default_rng(3)
    frame = _training_frame(n=150)
    frame[BASELINE] = rng.uniform(1.0, 6.0, len(frame))
    frame[TARGET] = frame[BASELINE]  # o alvo é exatamente a régua: nada a corrigir
    epsilon = 1e-6
    modelo = _fit_base_margin(frame, XgbParameters(2, 5, 0.1, 20, 0.9, 5.0), epsilon)
    previsto = predict_base_margin(modelo, frame, epsilon)
    # exp(log(régua + eps)) = régua + eps, e o gradiente inicial é só eps: a previsão fica em cima da régua.
    np.testing.assert_allclose(previsto, frame[BASELINE].to_numpy(), rtol=1e-3)


def test_two_stage_models_return_probability_and_expected_quantity():
    rng = np.random.default_rng(5)
    frame = _training_frame(n=300)
    frame[TARGET] = np.where(frame[BASELINE] > 1.75, rng.poisson(4, len(frame)) + 1.0, 0.0)  # zero determinístico
    modelos = _fit_two_stage(frame, XgbParameters(2, 5, 0.3, 40, 1.0, 1.0))
    esperado, probabilidade = predict_two_stage(modelos, frame)
    assert ((probabilidade >= 0) & (probabilidade <= 1)).all()
    assert (esperado >= 0).all()
    # A classe é separável pela régua: onde o alvo é zero a probabilidade cai perto de 0, e onde vende, perto de 1.
    assert probabilidade[frame[TARGET] == 0].mean() < 0.2
    assert probabilidade[frame[TARGET] > 0].mean() > 0.8


def test_predict_two_stage_arithmetic_with_stub_models():
    class Stub:
        def __init__(self, values):
            self.values = np.array(values)

        def predict(self, matrix):
            return self.values

    frame = pd.DataFrame({name: [1.0, 1.0, 1.0] for name in FEATURES})
    esperado, probabilidade = predict_two_stage((Stub([0.5, 1.2, -0.1]), Stub([4.0, -2.0, 6.0])), frame)
    np.testing.assert_allclose(probabilidade, [0.5, 1.0, 0.0])  # cortada em [0, 1]
    np.testing.assert_allclose(esperado, [2.0, 0.0, 0.0])  # 0,5 x 4; 1 x max(-2, 0); 0 x 6


def test_residual_model_learns_a_constant_log_shift():
    frame = _training_frame(n=200)
    frame[TARGET] = np.expm1(np.log1p(frame[BASELINE]) + 0.5)  # alvo = régua em log1p + 0,5
    modelo = _fit_residual(frame, XgbParameters(2, 5, 0.3, 60, 1.0, 1.0))
    residuo = predict_residual(modelo, frame)
    np.testing.assert_allclose(residuo, 0.5, atol=0.02)  # o resíduo aprendido é o deslocamento constante
    np.testing.assert_allclose(reconstruct_residual(frame, residuo), frame[TARGET].to_numpy(), rtol=0.03)


# ── Aritmética de previsão e reconstrução ───────────────────────────


def test_reconstruct_residual_with_shift_hand_computed():
    frame = pd.DataFrame({BASELINE: [4.0, 0.0, -3.0]})
    # expm1(log1p(4) + ln 2 + ... ): log1p(4) = ln 5; somando ln 2 -> 10; menos 1 -> 9.
    result = reconstruct_residual(frame, np.array([0.0, 0.0, 0.0]), shift=np.log(2.0))
    np.testing.assert_allclose(result, [9.0, 1.0, 1.0])  # régua 0: expm1(ln 2) = 1; régua negativa vira 0 antes
    assert (reconstruct_residual(frame, np.array([-50.0] * 3)) >= 0).all()  # nunca negativa


def test_margin_hand_computed():
    frame = pd.DataFrame({BASELINE: [0.0, 1.0, -5.0]})
    np.testing.assert_allclose(_margin(frame, 1e-3), np.log([1e-3, 1.001, 1e-3]))  # negativa é cortada em 0


def test_apply_calibration_hand_computed_and_clipped():
    frame = pd.DataFrame({"pred_xgboost": [10.0, 0.0, -4.0], BASELINE: [2.0, 4.0, 1.0]})
    # peso 0,5 x multiplicador 2 x xgb + 0,5 x régua.
    np.testing.assert_allclose(apply_calibration(frame, Calibration("m", 0.5, 2.0)), [11.0, 2.0, 0.0])
    np.testing.assert_allclose(apply_calibration(frame, Calibration("puro", 1.0)), [10.0, 0.0, 0.0])
    np.testing.assert_allclose(apply_calibration(frame, Calibration("regua", 0.0)), frame[BASELINE])


def test_add_moving_average_baselines_does_not_mutate_and_accepts_decimals():
    frame = pd.DataFrame(
        {
            "sum_3m": [Decimal("6")], "sum_12m": [Decimal("24")], "season_sum_next_3m": [Decimal("3.6")],
            "produto_locais_avg_12m": [Decimal("12")], "categoria_local_avg_12m": [Decimal("18")],
        }
    )
    result = add_moving_average_baselines(frame)
    assert "pred_mm3" not in frame.columns
    assert result.loc[0, "pred_mm12_idx"] == pytest.approx(7.2)
    assert list(MOVING_BASELINES.values()) == ["pred_mm3", "pred_mm12", "pred_mm12_idx", "pred_produto_idx", "pred_categoria_loja_idx"]


def test_reconcile_multiple_groups_are_independent():
    frame = pd.DataFrame(
        {
            "cutoff": [dt.date(2025, 1, 1)] * 4 + [dt.date(2025, 2, 1)] * 2,
            "category_name": ["a", "a", "b", "b", "a", "a"],
            "sk_location": ["l1"] * 6,
            "pred_xgboost": [1.0, 3.0, 2.0, 2.0, 5.0, 5.0],
            BASELINE: [4.0, 4.0, 1.0, 1.0, 0.0, 0.0],
        }
    )
    result = reconcile_to_baseline_total(frame)
    # Grupo (jan, a): total da régua 8, proporções 1:3 -> 2 e 6. (jan, b): total 2, iguais -> 1 e 1.
    # (fev, a): total da régua 0 -> tudo zera, mesmo com xgboost positivo.
    np.testing.assert_allclose(result, [2.0, 6.0, 1.0, 1.0, 0.0, 0.0])


def test_reconcile_clips_negative_predictions_and_follows_input_order_for_any_index():
    frame = pd.DataFrame(
        {
            "cutoff": [dt.date(2025, 1, 1)] * 3,
            "category_name": ["a"] * 3,
            "sk_location": ["l1"] * 3,
            "pred_xgboost": [-2.0, 4.0, 4.0],
            BASELINE: [3.0, 3.0, 3.0],
        },
        index=[30, 10, 20],
    )
    result = reconcile_to_baseline_total(frame)
    np.testing.assert_allclose(result, [0.0, 4.5, 4.5])  # total da régua 9 repartido 4:4 entre as linhas positivas
    assert result.sum() == pytest.approx(9.0)


def test_reconcile_keeps_series_whose_category_is_missing():
    frame = pd.DataFrame(
        {
            "cutoff": [dt.date(2025, 1, 1)] * 2,
            "category_name": [None, None],
            "sk_location": ["l1", "l1"],
            "pred_xgboost": [1.0, 3.0],
            BASELINE: [4.0, 4.0],
        }
    )
    np.testing.assert_allclose(reconcile_to_baseline_total(frame), [2.0, 6.0])  # sem categoria não pode virar zero


# ── Métricas ────────────────────────────────────────────────────────


def test_metric_table_aggregation_levels_hand_computed():
    frame = _xgb_frame(**{TARGET: [2.0, 4.0, 6.0], "pred_xgboost": [1.0, 5.0, 6.0]})
    result = metric_table(frame, {"m": "pred_xgboost"}).loc["m"]
    # Erros por produto: 1, 1, 0 sobre 12 reais -> WAPE 2/12; MAE = 2/3; RMSE = raiz(2/3).
    assert result["wape"] == round(2 / 12, 4)
    assert result["mae"] == pytest.approx(2 / 3)
    assert result["rmse"] == pytest.approx(np.sqrt(2 / 3))
    assert result["vies"] == 0.0  # 12 previstos contra 12 reais
    assert result["wape_produto_local"] == round(2 / 12, 4)  # cada produto é uma série
    # Somando a categoria (mesma loja e corte): real 12, previsto 12 -> erro 0. Idem para a loja.
    assert result["wape_categoria_local"] == 0.0
    assert result["wape_local"] == 0.0


def test_metric_table_multiple_forecasts_and_columns():
    frame = _xgb_frame()
    tabela = metric_table(frame)  # rótulos padrão
    assert list(tabela.index) == ["XGBoost puro", "Régua"]
    assert list(tabela.columns) == ["mae", "rmse", "wape", "vies", "wape_produto_local", "wape_categoria_local", "wape_local"]
    # Régua: erros 1, 2, 3 = 6 sobre 6 reais -> WAPE 1; previsto 6 = real 6 -> viés 0.
    assert tabela.loc["Régua", "wape"] == 1.0
    assert tabela.loc["Régua", "vies"] == 0.0
    assert tabela.loc["Régua", "mae"] == 2.0


def test_metric_table_does_not_mutate_input():
    frame = _xgb_frame(**{TARGET: [Decimal("2"), Decimal("4"), Decimal("0")]})
    antes = frame.copy()
    metric_table(frame)
    pd.testing.assert_frame_equal(frame, antes)


def test_evaluate_scores_a_model_and_returns_the_prediction_frame(demand_panel):
    class Constant:
        def predict(self, matrix):
            return np.full(matrix.num_row(), 1.5)

    frame = demand_panel.dropna(subset=[TARGET]).head(40)
    metricas, previsoes = evaluate(Constant(), frame)
    assert (previsoes["pred_xgboost"] == 1.5).all()
    assert len(previsoes) == 40
    assert list(metricas.index) == ["XGBoost puro", "Régua"]
    for coluna in ("cutoff", "sk_product", "sk_location", "category_name", TARGET, BASELINE, "sum_3m", "sum_12m", "season_sum_next_3m"):
        assert coluna in previsoes.columns
    assert previsoes[TARGET].tolist() == frame[TARGET].tolist()  # mesma ordem de linhas


# ── Seleção na validação ────────────────────────────────────────────


def test_calibration_metrics_hand_computed():
    scored = pd.DataFrame(
        {
            "cutoff": [dt.date(2025, 1, 1)] * 3,
            "category_name": ["a", "a", "b"],
            "sk_location": ["l1"] * 3,
            TARGET: [3.0, 1.0, 2.0],
        }
    )
    resultado = _calibration_metrics(scored, np.array([2.0, 2.0, 5.0]))
    # Categoria a: real 4, previsto 4 -> 0; b: real 2, previsto 5 -> 3. WAPE = 3/6. Local l1: real 6, previsto 9 -> 3/6.
    assert resultado["wape_categoria_local"] == pytest.approx(0.5)
    assert resultado["wape_local"] == pytest.approx(0.5)
    assert resultado["vies"] == pytest.approx(0.5)
    assert resultado["pontuacao"] == pytest.approx(1.5)


def test_calibration_metrics_without_demand_is_an_error():
    scored = pd.DataFrame({"cutoff": [dt.date(2025, 1, 1)], "category_name": ["a"], "sk_location": ["l"], TARGET: [0.0]})
    with pytest.raises(ValueError, match="demanda positiva"):
        _calibration_metrics(scored, np.array([1.0]))


def test_select_calibration_rejects_zero_xgboost_total():
    validation = pd.DataFrame(
        {
            "cutoff": [dt.date(2025, 1, 1)], "category_name": ["a"], "sk_location": ["l"],
            TARGET: [4.0], "pred_xgboost": [0.0], BASELINE: [4.0],
        }
    )
    with pytest.raises(ValueError, match="positiva"):
        select_calibration(validation)


def test_select_calibration_candidates_are_sorted_by_score_and_tie_broken_stably():
    validation = pd.DataFrame(
        {
            "cutoff": [dt.date(2025, 1, 1)] * 2, "category_name": ["a", "b"], "sk_location": ["l1", "l1"],
            TARGET: [4.0, 4.0], "pred_xgboost": [4.0, 4.0], BASELINE: [4.0, 4.0],
        }
    )
    chosen, tabela = select_calibration(validation)
    assert tabela["pontuacao"].is_monotonic_increasing
    # Tudo empata em zero: vence o primeiro candidato (XGBoost puro) pela ordenação estável.
    assert chosen.name == "XGBoost puro"
    assert tabela.iloc[0]["pontuacao"] == pytest.approx(0.0)


def test_select_residual_shift_picks_the_mean_log_error_when_it_scores_better():
    baseline = np.array([1.0, 2.0, 3.0, 4.0])
    frame = pd.DataFrame(
        {
            "cutoff": [dt.date(2025, 1, 1)] * 4, "sk_product": list("abcd"), "sk_location": ["l1"] * 4,
            "category_name": ["a"] * 4, TARGET: np.expm1(np.log1p(baseline) + 0.4), BASELINE: baseline,
        }
    )
    residuo = np.zeros(4)  # o modelo não aprendeu o deslocamento de 0,4 em log1p
    shift, tabela = select_residual_shift(frame, residuo)
    assert shift == pytest.approx(0.4)  # média de log1p(alvo) - log1p(régua) - resíduo
    assert set(tabela["shift_log"].round(6)) == {0.0, 0.4}
    assert tabela.iloc[0]["shift_log"] == pytest.approx(0.4)
    assert tabela.iloc[0]["pontuacao"] == pytest.approx(0.0, abs=1e-9)  # com o deslocamento a reconstrução é exata


def test_two_stage_threshold_hand_computed_f1():
    frame = pd.DataFrame({TARGET: [0.0, 2.0, 3.0, 0.0]})
    limiar, tabela = select_two_stage_threshold(frame, np.array([0.1, 0.8, 0.7, 0.2]))
    # Com limiar 0,20 o zero de probabilidade 0,2 também é previsto positivo: precisão 2/3, recall 1, F1 0,8.
    primeiro = tabela[np.isclose(tabela["threshold"], 0.2)].iloc[0]
    assert primeiro["precision"] == pytest.approx(2 / 3)
    assert primeiro["recall"] == 1.0
    assert primeiro["f1"] == pytest.approx(0.8)
    # De 0,25 em diante só os dois positivos passam: F1 = 1. Empate: vence o menor limiar.
    assert limiar == pytest.approx(0.25)
    assert tabela.iloc[0]["f1"] == 1.0
    assert tabela.iloc[0]["proportion_real"] == 0.5 and tabela.iloc[0]["proportion_predicted"] == 0.5
    assert len(tabela) == 13  # de 0,20 a 0,80 de 0,05 em 0,05


def test_two_stage_threshold_without_positives_does_not_divide_by_zero():
    frame = pd.DataFrame({TARGET: [0.0, 0.0]})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        limiar, tabela = select_two_stage_threshold(frame, np.array([0.9, 0.1]))
    assert (tabela["f1"] == 0.0).all()
    assert limiar == pytest.approx(0.2)


# ── run() completo, em painel sintético ─────────────────────────────


def test_run_returns_every_artifact_and_respects_the_temporal_contract(xgboost_result, demand_panel):
    result = xgboost_result
    split = result["split"]
    assert len(split.validation_cutoffs) == 6 and len(split.test_cutoffs) == 12
    assert result["selected_feature_set"] in FEATURE_SETS
    assert result["features"] == FEATURE_SETS[result["selected_feature_set"]]
    assert result["best_parameters"] == WINNING_PARAMETERS
    for chave in (
        "calibration", "feature_search", "validation_metrics", "baseline_ranking", "residual_shift", "residual_search",
        "base_margin_search", "two_stage_search", "two_stage_classification", "test_metrics", "test_metrics_by_cutoff",
        "test_predictions", "future_predictions", "test_model", "forecast_model",
    ):
        assert chave in result, chave
    # Treino, validação e teste nunca se misturam e respeitam o embargo de 3 meses.
    assert split.train["cutoff"].max() == add_months(split.validation_cutoffs[0], -3)
    assert split.final_train["cutoff"].max() == add_months(split.test_cutoffs[0], -3)
    assert set(split.validation["cutoff"]) == set(split.validation_cutoffs)
    assert set(split.test["cutoff"]) == set(split.test_cutoffs)


def test_run_test_predictions_cover_exactly_the_test_rows_and_are_valid(xgboost_result):
    result = xgboost_result
    previsoes = result["test_predictions"]
    assert len(previsoes) == len(result["split"].test)
    assert set(previsoes["cutoff"]) == set(result["split"].test_cutoffs)
    for coluna in ("pred_xgboost", "pred_calibrated", "pred_reconciled", "pred_residual", "pred_base_margin", "pred_two_stage"):
        valores = previsoes[coluna].to_numpy(dtype=float)
        assert np.isfinite(valores).all() and (valores >= 0).all(), coluna
    for coluna in MOVING_BASELINES.values():
        assert coluna in previsoes.columns
    metricas = result["test_metrics"]
    assert set(metricas.index) >= {"XGBoost puro", "Régua", *MOVING_BASELINES}
    por_corte = result["test_metrics_by_cutoff"]
    assert set(por_corte.index.get_level_values("cutoff")) == set(result["split"].test_cutoffs)


def test_run_forecast_is_for_the_latest_unlabeled_cutoff_only(xgboost_result, demand_panel):
    futuro = xgboost_result["future_predictions"]
    ultimo = demand_panel["cutoff"].max()
    assert set(futuro["cutoff"]) == {ultimo}
    assert len(futuro) == demand_panel["sk_product"].nunique()  # uma linha por série
    for coluna in ("pred_xgboost", "pred_calibrated", "pred_reconciled", "pred_residual", "pred_base_margin", "pred_two_stage"):
        assert np.isfinite(futuro[coluna]).all() and (futuro[coluna] >= 0).all()


def test_run_selected_calibration_comes_from_the_candidate_list(xgboost_result):
    calibracao = xgboost_result["calibration"]
    assert calibracao.name.startswith(("XGBoost", "Mistura"))
    assert 0.0 <= calibracao.xgb_weight <= 1.0


def test_run_does_not_mutate_the_panel(demand_panel):
    painel = demand_panel.copy()
    run(painel)
    pd.testing.assert_frame_equal(painel, demand_panel)


def test_run_without_an_unlabeled_cutoff_is_an_error(demand_panel):
    sem_inferencia = demand_panel[demand_panel["is_target_complete"]].copy()
    with pytest.raises(ValueError, match="inferência"):
        run(sem_inferencia)


if __name__ == "__main__":
    unittest.main()
