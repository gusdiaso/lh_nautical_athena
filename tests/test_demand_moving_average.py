"""Testes das réguas de média móvel (notebook 04).

Contas feitas à mão em cada teste. Só a lógica em pandas/Python: as funções PySpark
do módulo (`build_cutoff_panel`, `monthly_totals`, `year_over_year_persistence`) não são
testadas aqui.
"""

import datetime as dt
import warnings

import numpy as np
import pandas as pd
import pytest

from src.analytics_ai.demand_common import add_months
from src.analytics_ai.demand_moving_average import (
    INTERVAL_QUANTILES,
    MM12_LAG_MONTHS,
    add_forecasts,
    apply_interval_buckets,
    fit_interval_buckets,
    interval_coverage,
    past_volume_quintiles,
    seasonal_index_at,
    trend_factor_at,
)

BASE = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0, 120.0]  # média 65


def _months(start: dt.date, n: int) -> list[dt.date]:
    return [add_months(start, k) for k in range(n)]


def _totals(values_by_month: dict[dt.date, float]) -> pd.DataFrame:
    months = sorted(values_by_month)
    return pd.DataFrame({"month": months, "demand": [values_by_month[m] for m in months]})


def _seasonal_totals(years: tuple[int, ...], factors: dict[int, float] | None = None) -> pd.DataFrame:
    """Demanda total = BASE[mês] × fator do ano (1 se não informado)."""
    factors = factors or {}
    values = {}
    for year in years:
        for month in range(1, 13):
            values[dt.date(year, month, 1)] = BASE[month - 1] * factors.get(year, 1.0)
    return _totals(values)


# ── Constantes ──────────────────────────────────────────────────────


def test_mm12_lag_is_distance_between_window_centers():
    # Centro da MM12 = 5,5 meses antes do corte; centro dos 3 meses previstos = 2 depois.
    assert MM12_LAG_MONTHS == 5.5 + 2.0


def test_interval_quantiles_default():
    assert INTERVAL_QUANTILES == (0.25, 0.5, 0.75, 0.9)


# ── seasonal_index_at ───────────────────────────────────────────────


def test_seasonal_index_is_month_mean_over_grand_mean():
    totals = _seasonal_totals((2022, 2023))
    index = seasonal_index_at(totals, dt.date(2023, 12, 1))
    # Cada mês do ano vale BASE[m] nos dois anos; média das médias = 65.
    assert sorted(index) == list(range(1, 13))
    for month in range(1, 13):
        assert index[month] == pytest.approx(BASE[month - 1] / 65.0, rel=1e-12)
    assert sum(index.values()) / 12 == pytest.approx(1.0)


def test_seasonal_index_uses_only_months_up_to_cutoff():
    # 2022 inteiro + 2023 até junho, com 2023 valendo o dobro.
    totals = _seasonal_totals((2022, 2023), {2023: 2.0})
    totals = totals[pd.to_datetime(totals["month"]) <= pd.Timestamp("2023-06-01")]
    index = seasonal_index_at(totals, dt.date(2023, 6, 1))
    # jan-jun: média de BASE e 2*BASE = 1,5*BASE; jul-dez: só 2022 = BASE.
    by_month = [1.5 * BASE[m] for m in range(6)] + [BASE[m] for m in range(6, 12)]
    grand_mean = sum(by_month) / 12  # (315 + 570) / 12 = 73,75
    assert grand_mean == 73.75
    assert index[1] == pytest.approx(15.0 / 73.75)
    assert index[12] == pytest.approx(120.0 / 73.75)


def test_seasonal_index_has_no_lookahead():
    honest = _seasonal_totals((2022, 2023), {2023: 2.0})
    honest = honest[pd.to_datetime(honest["month"]) <= pd.Timestamp("2023-06-01")]
    # Mesma série até o corte, mas com um futuro absurdo depois dele.
    future = _totals({dt.date(2023, m, 1): 1e9 for m in range(7, 13)})
    with_future = pd.concat([honest, future], ignore_index=True)
    assert seasonal_index_at(with_future, dt.date(2023, 6, 1)) == seasonal_index_at(honest, dt.date(2023, 6, 1))


def test_seasonal_index_needs_the_twelve_calendar_months():
    totals = _seasonal_totals((2023,))
    totals = totals[pd.to_datetime(totals["month"]) <= pd.Timestamp("2023-11-01")]  # 11 meses
    with pytest.raises(ValueError, match="faltam meses"):
        seasonal_index_at(totals, dt.date(2023, 11, 1))


def test_seasonal_index_accepts_timestamp_months():
    totals = _seasonal_totals((2022, 2023)).assign(month=lambda d: pd.to_datetime(d["month"]))
    index = seasonal_index_at(totals, dt.date(2023, 12, 1))
    assert index[6] == pytest.approx(60.0 / 65.0)


# ── trend_factor_at ─────────────────────────────────────────────────


def test_trend_factor_growth_and_lag_exponent():
    totals = _totals({m: 100.0 for m in _months(dt.date(2022, 1, 1), 12)} | {m: 150.0 for m in _months(dt.date(2023, 1, 1), 12)})
    growth, factor = trend_factor_at(totals, dt.date(2023, 12, 1))
    assert growth == pytest.approx(1800.0 / 1200.0)  # 12 meses recentes / 12 anteriores
    assert factor == pytest.approx(1.5 ** (7.5 / 12))


def test_trend_factor_custom_lag_and_flat_series():
    totals = _totals({m: 100.0 for m in _months(dt.date(2022, 1, 1), 24)})
    growth, factor = trend_factor_at(totals, dt.date(2023, 12, 1), lag_months=12.0)
    assert (growth, factor) == (1.0, 1.0)
    totals = _totals({m: 100.0 for m in _months(dt.date(2022, 1, 1), 12)} | {m: 200.0 for m in _months(dt.date(2023, 1, 1), 12)})
    _, factor12 = trend_factor_at(totals, dt.date(2023, 12, 1), lag_months=12.0)
    assert factor12 == pytest.approx(2.0)  # lag de 12 meses = o crescimento inteiro


def test_trend_factor_ignores_months_after_cutoff():
    base = {m: 100.0 for m in _months(dt.date(2022, 1, 1), 12)} | {m: 150.0 for m in _months(dt.date(2023, 1, 1), 12)}
    with_future = base | {dt.date(2024, 1, 1): 1e9}
    assert trend_factor_at(_totals(with_future), dt.date(2023, 12, 1)) == trend_factor_at(_totals(base), dt.date(2023, 12, 1))


def test_trend_factor_without_previous_year_fails_instead_of_returning_infinity():
    totals = _totals({m: 100.0 for m in _months(dt.date(2023, 1, 1), 12)})  # só um ano de histórico
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(ValueError, match="12 meses anteriores"):
            trend_factor_at(totals, dt.date(2023, 12, 1))


# ── add_forecasts ───────────────────────────────────────────────────


def _panel(cutoff: dt.date) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cutoff": [cutoff] * 3,
            "sk_product": ["p1", "p1", "p2"],
            "sk_location": ["l1", "l2", "l1"],
            "sum_12m": [120.0, 60.0, 24.0],
            "sum_3m": [12.0, 3.0, 0.0],
        }
    )


def test_add_forecasts_formulas_without_growth():
    # Mesma demanda em todos os anos: crescimento 1, fator 1; índice = BASE/65.
    totals = _seasonal_totals((2021, 2022, 2023))
    cutoff = dt.date(2023, 9, 1)  # meses previstos: out, nov, dez
    out = add_forecasts(_panel(cutoff), totals, {"produto": ["sk_product"]})
    season_sum = (100.0 + 110.0 + 120.0) / 65.0
    assert out["season_sum"].tolist() == pytest.approx([season_sum] * 3)
    assert out["growth_12m"].tolist() == pytest.approx([1.0] * 3)
    assert out["trend_factor"].tolist() == pytest.approx([1.0] * 3)
    # MM12 x 3 e MM3 x 3
    assert out["pred_mm12"].tolist() == pytest.approx([30.0, 15.0, 6.0])
    assert out["pred_mm3"].tolist() == pytest.approx([12.0, 3.0, 0.0])
    # MM12 x soma dos índices: sum_12m/12 * season_sum
    assert out["pred_mm12_idx"].tolist() == pytest.approx([10.0 * season_sum, 5.0 * season_sum, 2.0 * season_sum])
    assert out["pred_mm12_idx_trend"].tolist() == pytest.approx(out["pred_mm12_idx"].tolist())
    # Produto p1: média por série = (120+60)/2 = 90; p2: 24.
    assert out["pred_produto_idx"].tolist() == pytest.approx([90.0 / 12 * season_sum] * 2 + [2.0 * season_sum])
    assert out["pred_produto_idx_trend"].tolist() == pytest.approx(out["pred_produto_idx"].tolist())


def test_add_forecasts_applies_trend_factor():
    totals = _totals(
        {m: 100.0 for m in _months(dt.date(2022, 1, 1), 12)} | {m: 150.0 for m in _months(dt.date(2023, 1, 1), 12)}
    )
    out = add_forecasts(_panel(dt.date(2023, 12, 1)), totals, {"produto": ["sk_product"]})
    factor = 1.5 ** (7.5 / 12)
    # Índice sazonal 1 em todo mês -> season_sum = 3.
    assert out["season_sum"].tolist() == pytest.approx([3.0] * 3)
    assert out["growth_12m"].tolist() == pytest.approx([1.5] * 3)
    assert out["pred_mm12_idx"].tolist() == pytest.approx([30.0, 15.0, 6.0])
    assert out["pred_mm12_idx_trend"].tolist() == pytest.approx([30.0 * factor, 15.0 * factor, 6.0 * factor])
    assert out["pred_produto_idx_trend"].tolist() == pytest.approx(
        [90.0 / 12 * 3 * factor] * 2 + [24.0 / 12 * 3 * factor]
    )


def test_add_forecasts_computes_each_cutoff_with_its_own_history():
    totals = _seasonal_totals((2021, 2022, 2023), {2023: 2.0})
    panel = pd.concat([_panel(dt.date(2022, 12, 1)), _panel(dt.date(2023, 6, 1))], ignore_index=True)
    out = add_forecasts(panel, totals, {})
    early = out[out["cutoff"] == dt.date(2022, 12, 1)]
    late = out[out["cutoff"] == dt.date(2023, 6, 1)]
    # Corte de dez/2022 (crescimento 1 até então; previsão jan-fev-mar, BASE/65 cada).
    assert early["season_sum"].iloc[0] == pytest.approx((10 + 20 + 30) / 65.0)
    assert early["growth_12m"].iloc[0] == pytest.approx(1.0)
    # Corte de jun/2023: 12 meses até jun = 6 meses de 2022 (jul-dez) + 6 de 2023.
    last12 = sum(BASE[6:]) + 2 * sum(BASE[:6])
    prev12 = sum(BASE[6:]) + sum(BASE[:6])  # jul-dez/2021 + jan-jun/2022, sem crescimento
    assert late["growth_12m"].iloc[0] == pytest.approx(last12 / prev12)
    assert late["season_sum"].iloc[0] != early["season_sum"].iloc[0]


def test_add_forecasts_has_no_lookahead():
    honest = _seasonal_totals((2021, 2022, 2023))
    honest = honest[pd.to_datetime(honest["month"]) <= pd.Timestamp("2023-09-01")]
    future = _totals({dt.date(2023, m, 1): 1e9 for m in (10, 11, 12)})
    panel = _panel(dt.date(2023, 9, 1))
    pd.testing.assert_frame_equal(
        add_forecasts(panel, honest, {"produto": ["sk_product"]}),
        add_forecasts(panel, pd.concat([honest, future], ignore_index=True), {"produto": ["sk_product"]}),
    )


def test_add_forecasts_does_not_mutate_the_panel_and_keeps_its_rows():
    totals = _seasonal_totals((2021, 2022, 2023))
    panel = _panel(dt.date(2023, 9, 1))
    before = panel.copy()
    out = add_forecasts(panel, totals, {"produto": ["sk_product"]})
    pd.testing.assert_frame_equal(panel, before)
    assert len(out) == len(panel)
    assert set(panel.columns) <= set(out.columns)


def test_add_forecasts_horizon_argument_changes_multiplier_and_index_span():
    totals = _seasonal_totals((2021, 2022, 2023))
    out = add_forecasts(_panel(dt.date(2023, 9, 1)), totals, {}, horizon=2)
    assert out["pred_mm12"].tolist() == pytest.approx([120 / 12 * 2, 60 / 12 * 2, 24 / 12 * 2])
    assert out["season_sum"].iloc[0] == pytest.approx((100.0 + 110.0) / 65.0)


def test_add_forecasts_on_empty_panel_returns_empty_with_forecast_columns():
    totals = _seasonal_totals((2021, 2022, 2023))
    out = add_forecasts(_panel(dt.date(2023, 9, 1)).iloc[0:0], totals, {"produto": ["sk_product"]})
    assert out.empty
    for column in ("pred_mm12", "pred_mm3", "pred_mm12_idx", "pred_mm12_idx_trend", "pred_produto_idx", "season_sum"):
        assert column in out.columns


# ── Faixa de previsão ───────────────────────────────────────────────


def test_fit_interval_buckets_hand_computed_quartiles():
    calibration = pd.DataFrame({"pred": np.arange(1.0, 21.0), "target_3m": np.arange(1.0, 21.0) * 2})
    buckets = fit_interval_buckets(calibration, "pred", n_buckets=4)
    # Quantis 0, .25, .5, .75, 1 de 1..20: 1; 5,75; 10,5; 15,25; 20 (interpolação linear).
    assert buckets["lower"].tolist() == pytest.approx([1.0, 5.75, 10.5, 15.25])
    assert buckets["upper"].tolist() == pytest.approx([5.75, 10.5, 15.25, 20.0])
    assert buckets["n"].tolist() == [5, 5, 5, 5]
    assert list(buckets.columns) == ["bucket", "lower", "upper", "n", "q_25", "q_50", "q_75", "q_90"]
    # Faixa 0: previsões 1..5, vendas 2,4,6,8,10 -> q25 = 4, mediana 6, q75 = 8, q90 = 8 + 0,6*2 = 9,2.
    first = buckets.iloc[0]
    assert (first["q_25"], first["q_50"], first["q_75"]) == (4.0, 6.0, 8.0)
    assert first["q_90"] == pytest.approx(9.2)


def test_fit_interval_buckets_with_ties_merges_equal_edges_and_loses_no_rows():
    # Seis previsões zero e quatro positivas: os decis repetem o valor 0.
    calibration = pd.DataFrame({"pred": [0.0] * 6 + [1.0, 2.0, 3.0, 4.0], "target_3m": [0.0] * 6 + [1.0, 1.0, 5.0, 9.0]})
    buckets = fit_interval_buckets(calibration, "pred", n_buckets=10)
    # Bordas únicas: 0; 0,4; 1,3; 2,2; 3,1; 4 -> 5 faixas com 6, 1, 1, 1 e 1 linhas.
    assert buckets["lower"].tolist() == pytest.approx([0.0, 0.4, 1.3, 2.2, 3.1])
    assert buckets["n"].tolist() == [6, 1, 1, 1, 1]
    assert buckets["n"].sum() == len(calibration)
    assert buckets["q_90"].iloc[0] == 0.0  # faixa dos zeros: só vendeu zero
    assert buckets["q_50"].iloc[-1] == 9.0  # última faixa tem uma linha só


def test_fit_interval_buckets_constant_predictions_yield_one_bucket():
    calibration = pd.DataFrame({"pred": [0.0] * 4, "target_3m": [0.0, 1.0, 2.0, 3.0]})
    buckets = fit_interval_buckets(calibration, "pred")
    assert len(buckets) == 1
    assert buckets.iloc[0]["n"] == 4
    assert buckets.iloc[0]["lower"] == 0.0 == buckets.iloc[0]["upper"]
    assert buckets.iloc[0]["q_50"] == 1.5


def test_fit_interval_buckets_single_row_is_one_bucket():
    buckets = fit_interval_buckets(pd.DataFrame({"pred": [2.0], "target_3m": [7.0]}), "pred")
    assert buckets["n"].tolist() == [1]
    assert buckets.iloc[0]["q_50"] == 7.0


def test_fit_interval_buckets_rejects_empty_calibration():
    with pytest.raises(ValueError, match="calibra"):
        fit_interval_buckets(pd.DataFrame({"pred": [], "target_3m": []}), "pred")


def test_fit_interval_buckets_custom_quantiles_and_actual_column():
    calibration = pd.DataFrame({"pred": [1.0, 2.0, 3.0], "real": [10.0, 20.0, 30.0]})
    buckets = fit_interval_buckets(calibration, "pred", actual_col="real", n_buckets=1, quantiles=(0.5, 0.95))
    assert list(buckets.columns) == ["bucket", "lower", "upper", "n", "q_50", "q_95"]
    assert buckets.iloc[0]["q_50"] == 20.0


def test_apply_interval_buckets_assigns_quantiles_of_the_matching_bucket():
    calibration = pd.DataFrame({"pred": np.arange(1.0, 21.0), "target_3m": np.arange(1.0, 21.0) * 2})
    buckets = fit_interval_buckets(calibration, "pred", n_buckets=4)
    new = pd.DataFrame({"pred": [-5.0, 3.0, 5.75, 12.0, 100.0]})
    out = apply_interval_buckets(new, buckets, "pred")
    # -5 fica na primeira faixa; 5,75 é o limite inferior da segunda (fechado à esquerda);
    # 100 fica na última.
    assert out["q_50"].tolist() == [6.0, 6.0, 16.0, 26.0, 36.0]
    assert "q_50" not in new.columns  # cópia


def test_apply_interval_buckets_works_after_constant_calibration():
    buckets = fit_interval_buckets(pd.DataFrame({"pred": [0.0] * 4, "target_3m": [0.0, 1.0, 2.0, 3.0]}), "pred")
    out = apply_interval_buckets(pd.DataFrame({"pred": [0.0, 5.0]}), buckets, "pred")
    assert out["q_50"].tolist() == [1.5, 1.5]


# ── interval_coverage ───────────────────────────────────────────────


def _coverage_frame():
    return pd.DataFrame(
        {
            "grupo": ["a", "a", "b", "b"],
            "target_3m": [1.0, 2.0, 3.0, 4.0],
            "q_50": [2.0] * 4,
            "q_75": [3.0] * 4,
            "q_90": [4.0] * 4,
        }
    )


def test_interval_coverage_total():
    out = interval_coverage(_coverage_frame())
    # Reais 1,2,3,4: até q50=2 -> 2/4; até q75=3 -> 3/4; até q90=4 -> 4/4.
    assert out.loc[0, "n"] == 4
    assert (out.loc[0, "ate_q50"], out.loc[0, "ate_q75"], out.loc[0, "ate_q90"]) == (0.5, 0.75, 1.0)


def test_interval_coverage_by_group():
    out = interval_coverage(_coverage_frame(), by=["grupo"]).set_index("grupo")
    assert out.loc["a", "ate_q50"] == 1.0  # 1 e 2 <= 2
    assert out.loc["b", "ate_q50"] == 0.0  # 3 e 4 > 2
    assert out.loc["b", "ate_q75"] == 0.5
    assert out["n"].tolist() == [2, 2]


def test_interval_coverage_counts_exact_ties_as_covered():
    frame = _coverage_frame().assign(target_3m=[2.0, 2.0, 2.0, 2.0])
    assert interval_coverage(frame).loc[0, "ate_q50"] == 1.0  # empate no limite conta como coberto


# ── past_volume_quintiles ───────────────────────────────────────────


def test_past_volume_quintiles_hand_computed():
    frame = pd.DataFrame(
        {
            "cutoff": [dt.date(2025, 1, 1)] * 10,
            "sum_12m": [float(v) for v in range(10, 0, -1)],  # fora de ordem de propósito
            "target_3m": [2.0 * v for v in range(10, 0, -1)],
        }
    )
    out = past_volume_quintiles(frame)
    assert out.index.tolist() == [1, 2, 3, 4, 5]
    assert out["series"].tolist() == [2] * 5
    # Quintil 1 = vendas 1 e 2 (média 1,5; alvo 3,0); quintil 5 = vendas 9 e 10 (9,5; 19,0).
    assert out.loc[1, "venda_media_12m_antes"] == 1.5
    assert out.loc[1, "venda_media_3m_depois"] == 3.0
    assert out.loc[5, "venda_media_12m_antes"] == 9.5
    assert out.loc[5, "venda_media_3m_depois"] == 19.0


def test_past_volume_quintiles_ranks_inside_each_cutoff():
    frame = pd.DataFrame(
        {
            "cutoff": [dt.date(2025, 1, 1)] * 5 + [dt.date(2025, 2, 1)] * 5,
            "sum_12m": [1.0, 2.0, 3.0, 4.0, 5.0, 100.0, 200.0, 300.0, 400.0, 500.0],
            "target_3m": [0.0] * 10,
        }
    )
    out = past_volume_quintiles(frame)
    # Cada corte tem 5 séries: uma por quintil. O quintil 1 mistura a menor de cada corte.
    assert out["series"].tolist() == [2] * 5
    assert out.loc[1, "venda_media_12m_antes"] == 50.5  # (1 + 100) / 2


def test_past_volume_quintiles_with_fewer_than_five_series_leaves_a_bin_empty():
    frame = pd.DataFrame({"cutoff": [dt.date(2025, 1, 1)] * 4, "sum_12m": [1.0, 2.0, 3.0, 4.0], "target_3m": [0.0] * 4})
    out = past_volume_quintiles(frame)
    # Ranks 1..4 em 5 faixas de quantis (bordas 1; 1,6; 2,2; 2,8; 3,4; 4): a terceira faixa
    # (2,2 a 2,8] não contém nenhum rank, então o quintil 3 não aparece.
    assert out.index.tolist() == [1, 2, 4, 5]
    assert out["series"].tolist() == [1, 1, 1, 1]
    assert out["venda_media_12m_antes"].tolist() == [1.0, 2.0, 3.0, 4.0]
