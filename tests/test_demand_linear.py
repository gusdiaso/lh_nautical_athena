"""Testes do ajuste linear: janela de treino, Ridge e previsão sem negativos."""

import datetime as dt

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline

from src.analytics_ai.demand_linear import (
    NUMERIC_FEATURES,
    TARGET,
    fit_linear,
    predict_nonnegative,
)


def _panel() -> pd.DataFrame:
    """Três cortes. Nos dois primeiros o alvo é 2x; no mais recente é 10x."""
    months = [dt.date(2025, 1, 1), dt.date(2025, 2, 1), dt.date(2025, 3, 1)]
    frame = pd.DataFrame({"cutoff": np.repeat(months, 4), "x": np.tile([1.0, 2.0, 3.0, 4.0], 3)})
    frame[TARGET] = frame["x"] * np.repeat([2.0, 2.0, 10.0], 4)
    return frame


def test_numeric_features_have_no_duplicates():
    assert len(NUMERIC_FEATURES) == len(set(NUMERIC_FEATURES))
    assert TARGET not in NUMERIC_FEATURES


def test_fit_linear_uses_every_cutoff_by_default():
    model = fit_linear(_panel(), ["x"])
    assert isinstance(model, LinearRegression)
    # 8 linhas com inclinação 2 e 4 com inclinação 10: a reta fica entre as duas.
    assert 2.0 < model.coef_[0] < 10.0


def test_fit_linear_window_keeps_only_the_most_recent_cutoffs():
    model = fit_linear(_panel(), ["x"], n_cutoffs=1)
    assert model.coef_[0] == pytest.approx(10.0)
    assert model.intercept_ == pytest.approx(0.0, abs=1e-9)
    two = fit_linear(_panel(), ["x"], n_cutoffs=2)
    assert 2.0 < two.coef_[0] < 10.0  # os dois últimos cortes: 2x e 10x


def test_fit_linear_alpha_builds_a_standardized_ridge_pipeline():
    model = fit_linear(_panel(), ["x"], alpha=1.0)
    assert isinstance(model, Pipeline)
    assert [name for name, _ in model.steps] == ["standardscaler", "ridge"]
    # Alpha enorme zera os pesos: a previsão vira quase a média do alvo.
    flat = fit_linear(_panel(), ["x"], alpha=1e12)
    assert np.allclose(flat.predict(_panel()[["x"]]), _panel()[TARGET].mean(), rtol=1e-3)


def test_fit_linear_does_not_mutate_the_training_panel():
    panel = _panel()
    before = panel.copy()
    fit_linear(panel, ["x"], n_cutoffs=1)
    pd.testing.assert_frame_equal(panel, before)


def test_predict_nonnegative_clips_negative_forecasts_to_zero():
    train = pd.DataFrame({"cutoff": [dt.date(2025, 1, 1)] * 3, "x": [0.0, 1.0, 2.0], TARGET: [4.0, 2.0, 0.0]})
    model = fit_linear(train, ["x"])  # reta 4 - 2x
    frame = pd.DataFrame({"x": [0.0, 1.0, 5.0]})
    assert model.predict(frame).tolist() == pytest.approx([4.0, 2.0, -6.0])
    assert predict_nonnegative(model, frame, ["x"]).tolist() == pytest.approx([4.0, 2.0, 0.0])
