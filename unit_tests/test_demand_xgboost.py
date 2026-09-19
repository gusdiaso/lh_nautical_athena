"""Checagens unitárias do contrato temporal e das métricas do primeiro modelo."""

import datetime as dt
import os
import sys
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch, sentinel

import numpy as np
import pandas as pd

from src.analytics_ai.demand_baselines import add_months
from src.analytics_ai.demand_xgboost import (
    BASELINE,
    TARGET,
    Calibration,
    FEATURE_SETS,
    add_moving_average_baselines,
    _margin,
    PARAMETER_CANDIDATES,
    apply_calibration,
    metric_table,
    predict_nonnegative,
    predict_two_stage,
    reconstruct_residual,
    select_two_stage_threshold,
    reconcile_to_baseline_total,
    search_hyperparameters,
    select_calibration,
    temporal_split,
)
from src.analytics_ai.run_demand_xgboost import create_spark_session


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
    def test_default_connect_profile_matches_project_profile(self) -> None:
        from src.ingestion.utils import build_spark_session

        env = os.environ.copy()
        for key in ("DATABRICKS_PROFILE", "DATABRICKS_CLUSTER_ID", "DATABRICKS_RUNTIME_VERSION"):
            env.pop(key, None)
        with patch.dict(os.environ, env, clear=True):
            with patch("src.ingestion.utils.DatabricksSession") as session:
                self.assertIsNotNone(build_spark_session())
                session.builder.profile.assert_called_once_with("lh-nautical-developers")
                session.builder.profile.return_value.serverless.assert_called_once_with()

    def test_local_session_uses_databricks_connect_helper(self) -> None:
        with patch.dict(os.environ, {"DATABRICKS_RUNTIME_VERSION": ""}):
            with patch("src.ingestion.utils.build_spark_session", return_value=sentinel.spark) as builder:
                self.assertIs(create_spark_session(), sentinel.spark)
                builder.assert_called_once_with()

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


if __name__ == "__main__":
    unittest.main()
