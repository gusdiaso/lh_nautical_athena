"""Testes da sazonalidade por produto (notebook 03): índice, força, acaso e séries de um produto.

Reúne os testes do antigo `eda_product_seasonality` (funções de um produto, no fim do módulo)
e os das medidas de sazonalidade por produto. Tudo pandas/numpy, sem Spark.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

from src.analytics_ai.eda_seasonality import (
    HIGH_SEASON_MONTHS,
    MIN_HISTORY_MONTHS,
    MONTH_LABELS,
    N_PERMUTATIONS,
    SIGNIFICANCE,
    month_summary,
    null_distribution,
    peak_profile,
    product_month_matrix,
    season_vs_offseason,
    seasonal_index,
    seasonal_ratios,
    seasonality_metrics,
    seasonality_table,
    strength_label,
    year_consistency,
    year_month_grid,
    year_month_matrix,
)

MONTHS = pd.date_range("2021-01-01", periods=60, freq="MS")
SEASON = np.array([0.5, 0.6, 0.8, 1.0, 1.3, 1.6, 1.7, 1.5, 1.1, 0.9, 0.6, 0.4])


def _series(kind: str, seed: int = 1) -> pd.Series:
    rng = np.random.default_rng(seed)
    growth = np.linspace(1.0, 1.4, len(MONTHS))
    if kind == "seasonal":
        mean = 100 * growth * SEASON[MONTHS.month - 1]
    else:
        mean = 100 * growth
    return pd.Series(rng.poisson(mean).astype(float), index=MONTHS)


def test_seasonal_series_is_detected_and_flat_series_is_not():
    seasonal = seasonality_metrics(_series("seasonal"))
    flat = seasonality_metrics(_series("flat"))
    assert seasonal["p_value"] < 0.01
    assert seasonal["strength"] > 0.7
    assert seasonal["consistency"] > 0.7
    assert seasonal["peak_month"] in (6, 7, 8)
    assert flat["p_value"] > 0.05
    assert flat["strength"] < seasonal["strength"]


def test_seasonal_index_averages_one():
    index = seasonal_index(seasonal_ratios(_series("seasonal")))
    assert list(index.index) == list(range(1, 13))
    assert index.mean() == pytest.approx(1.0)


def test_product_matrix_fills_zeros_only_after_first_month():
    monthly = pd.DataFrame(
        {
            "sk_product": ["a", "a", "b"],
            "month": pd.to_datetime(["2024-01-01", "2024-04-01", "2024-03-01"]),
            "demand": [5.0, 2.0, 7.0],
        }
    )
    wide = product_month_matrix(monthly)
    assert wide["a"].tolist() == [5.0, 0.0, 0.0, 2.0]
    assert wide["b"].isna().tolist() == [True, True, False, False]
    assert wide.loc["2024-04-01", "b"] == 0.0


def test_table_corrects_for_many_tests_and_skips_short_history():
    wide = pd.DataFrame({"seasonal": _series("seasonal"), "flat": _series("flat", 2)})
    wide["short"] = np.where(np.arange(len(MONTHS)) >= 40, 3.0, np.nan)
    table = seasonality_table(wide, n_permutations=200)
    assert set(table.index) == {"seasonal", "flat"}
    assert table.loc["seasonal", "is_seasonal"]
    assert table.loc["seasonal", "q_value"] >= table.loc["seasonal", "p_value"]


def test_year_month_grid_shape():
    grid = year_month_grid(_series("seasonal"))
    assert list(grid.columns) == list(range(1, 13))
    assert grid.notna().sum().sum() == 48


# ── Um produto (antigo test_eda_product_seasonality) ─────────────────


PRODUCT_MONTHS = pd.date_range("2021-01-01", "2023-12-01", freq="MS")


def _spiky_series() -> pd.Series:
    """Três anos completos: 3 unidades por mês e um pico de 30 em março."""
    return pd.Series(np.where(PRODUCT_MONTHS.month == 3, 30.0, 3.0), index=PRODUCT_MONTHS)


def test_year_month_matrix_layout_and_missing_months():
    y = _spiky_series().iloc[:-2]  # falta nov e dez de 2023
    matrix = year_month_matrix(y)
    assert list(matrix.columns) == list(range(1, 13))
    assert list(matrix.index) == [2021, 2022, 2023]
    assert matrix.loc[2021, 3] == 30.0
    assert np.isnan(matrix.loc[2023, 12])


def test_month_summary_counts_years_above_their_own_average():
    summary = month_summary(year_month_matrix(_spiky_series()))
    assert summary.loc[3, "anos_acima"] == 3 and summary.loc[3, "anos"] == 3
    assert summary.loc[7, "anos_acima"] == 0
    assert summary.loc[3, "media"] == 30.0


def test_season_vs_offseason_assigns_nov_dec_to_next_season():
    y = pd.Series(1.0, index=pd.date_range("2021-05-01", "2022-10-01", freq="MS"))
    y.loc[[pd.Timestamp("2021-11-01"), pd.Timestamp("2021-12-01")]] = 10.0
    table = season_vs_offseason(y)
    assert table.loc[2022, "meses_alta"] == 6  # nov/21 a abr/22
    assert table.loc[2022, "media_alta"] > table.loc[2022, "media_baixa"]
    assert table.loc[2021, "meses_baixa"] == 6  # mai a out/21


def test_peak_profile_shows_spike_then_back_to_normal():
    profile = peak_profile(_spiky_series())
    assert (profile["mes_pico"] == 3).all()
    assert (profile[0] > 2.5).all()
    assert (profile[1] < profile[0]).all()
    assert np.allclose(profile[1], profile[2])


def test_peak_profile_ignores_incomplete_years():
    y = _spiky_series().iloc[:-2]
    assert list(peak_profile(y).index) == [2021, 2022]


# ── Constantes ──────────────────────────────────────────────────────

BASE = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0, 120.0])  # média 65
FIVE_YEARS = pd.date_range("2019-01-01", periods=60, freq="MS")


def _periodic(years: int = 5) -> pd.Series:
    """Padrão sazonal exato (BASE por mês do ano), sem tendência nem ruído."""
    index = pd.date_range("2019-01-01", periods=12 * years, freq="MS")
    return pd.Series(np.tile(BASE, years), index=index)


def test_module_constants():
    assert MIN_HISTORY_MONTHS == 36
    assert N_PERMUTATIONS == 500
    assert SIGNIFICANCE == 0.05
    assert HIGH_SEASON_MONTHS == (11, 12, 1, 2, 3, 4)
    assert MONTH_LABELS[0] == "Jan" and MONTH_LABELS[-1] == "Dez" and len(MONTH_LABELS) == 12


# ── Razões e índice sazonal ─────────────────────────────────────────


def test_seasonal_ratios_of_a_linear_trend_are_all_one_and_lose_six_months_per_end():
    y = pd.Series(np.arange(1.0, 37.0), index=pd.date_range("2021-01-01", periods=36, freq="MS"))
    ratios = seasonal_ratios(y)
    # A média móvel centrada 2x12 reproduz exatamente uma reta.
    assert len(ratios) == 24
    assert ratios.index[0] == pd.Timestamp("2021-07-01") and ratios.index[-1] == pd.Timestamp("2023-06-01")
    np.testing.assert_allclose(ratios.to_numpy(), 1.0, rtol=1e-12)


def test_seasonal_ratios_of_a_pure_seasonal_pattern_are_value_over_mean():
    ratios = seasonal_ratios(_periodic(3))
    expected = BASE[ratios.index.month - 1] / 65.0
    np.testing.assert_allclose(ratios.to_numpy(), expected, rtol=1e-12)


def test_seasonal_ratios_drop_months_where_the_trend_is_not_positive():
    ratios = seasonal_ratios(pd.Series(0.0, index=pd.date_range("2021-01-01", periods=36, freq="MS")))
    assert ratios.empty  # 0 / 0 não vira índice


def test_seasonal_index_of_a_pure_pattern_is_base_over_its_mean():
    index = seasonal_index(seasonal_ratios(_periodic(4)))
    np.testing.assert_allclose(index.to_numpy(), BASE / 65.0, rtol=1e-12)
    assert index.idxmax() == 12 and index.idxmin() == 1


def test_seasonal_index_has_nan_for_calendar_months_without_data():
    ratios = pd.Series([1.0, 2.0], index=pd.to_datetime(["2022-03-01", "2022-04-01"]))
    index = seasonal_index(ratios)
    assert index.isna().sum() == 10
    assert list(index.index) == list(range(1, 13))


# ── Força, acaso e consistência ─────────────────────────────────────


def test_metrics_of_an_exact_seasonal_pattern():
    y = _periodic(5)
    global_index = pd.Series(BASE / 65.0, index=range(1, 13))
    m = seasonality_metrics(y, global_index, n_permutations=99)
    assert m["n_months"] == 60
    assert m["total_demand"] == 5 * BASE.sum() == 3900.0
    assert m["mean_demand"] == 65.0
    assert m["strength"] == pytest.approx(1.0)  # o mês do ano explica toda a variação
    assert m["p_value"] == pytest.approx(1 / 100)  # nenhum embaralhamento chega a 1,0: (1 + 0) / (1 + 99)
    assert m["consistency"] == pytest.approx(1.0)
    assert (m["peak_month"], m["trough_month"]) == (12, 1)
    assert m["peak_index"] == pytest.approx(120 / 65)
    assert m["trough_index"] == pytest.approx(10 / 65)
    assert m["amplitude"] == pytest.approx(12.0)
    assert m["corr_global"] == pytest.approx(1.0)
    assert 0 < m["null_mean"] < 0.5


def test_metrics_without_global_index_have_nan_correlation():
    assert np.isnan(seasonality_metrics(_periodic(5), None, n_permutations=20)["corr_global"])


def test_metrics_are_reproducible_for_a_given_seed_and_change_with_another():
    y = _series("flat", seed=3)
    a = seasonality_metrics(y, n_permutations=50, seed=1)
    b = seasonality_metrics(y, n_permutations=50, seed=1)
    c = seasonality_metrics(y, n_permutations=50, seed=2)
    assert pd.Series(a).equals(pd.Series(b))  # mesma semente, mesmo resultado (NaN incluído)
    assert a["strength"] == c["strength"]  # a força observada não depende da semente
    assert a["null_mean"] != c["null_mean"]  # já o sorteio dos embaralhamentos, sim


def test_metrics_return_none_for_constant_or_incomplete_series():
    constant = pd.Series(5.0, index=pd.date_range("2020-01-01", periods=48, freq="MS"))
    assert seasonality_metrics(constant, n_permutations=10) is None  # razões todas iguais a 1
    short = pd.Series(np.arange(1.0, 21.0), index=pd.date_range("2020-01-01", periods=20, freq="MS"))
    assert seasonality_metrics(short, n_permutations=10) is None  # sobram 8 razões: falta mês do ano


def test_amplitude_is_nan_when_the_trough_index_is_not_positive():
    y = _periodic(4).copy()
    y[y.index.month == 1] = 0.0  # janeiro sempre zero -> índice 0 no vale
    m = seasonality_metrics(y, n_permutations=10)
    assert m["trough_month"] == 1
    assert m["trough_index"] == 0.0
    assert np.isnan(m["amplitude"])


def test_null_distribution_hand_computed_properties():
    y = _periodic(5)
    null = null_distribution(y, n_permutations=500, seed=0)
    assert null.shape == (500,)
    assert ((null >= 0) & (null <= 1)).all()
    # Sob permutação, a fração explicada esperada é (k-1)/(N-1) = 11/47 para 12 meses e 48 razões.
    assert null.mean() == pytest.approx(11 / 47, abs=0.02)
    np.testing.assert_array_equal(null, null_distribution(y, n_permutations=500, seed=0))
    assert not np.array_equal(null, null_distribution(y, n_permutations=500, seed=1))


def test_null_distribution_of_a_series_without_variation_is_empty():
    constant = pd.Series(7.0, index=pd.date_range("2020-01-01", periods=48, freq="MS"))
    assert null_distribution(constant).size == 0


def _ratio_series(year_values: dict[int, list[float]]) -> pd.Series:
    """Razões mensais; cada ano recebe uma lista com os valores de jan em diante."""
    values, index = [], []
    for year, series in year_values.items():
        for month, value in enumerate(series, start=1):
            index.append(pd.Timestamp(year, month, 1))
            values.append(value)
    return pd.Series(values, index=pd.DatetimeIndex(index))


def test_year_consistency_is_the_correlation_between_years():
    pattern = list(BASE)
    same_shape = _ratio_series({2020: pattern, 2021: [2 * v + 3 for v in pattern]})
    reversed_shape = _ratio_series({2020: pattern, 2021: pattern[::-1]})
    assert year_consistency(same_shape) == pytest.approx(1.0)
    assert year_consistency(reversed_shape) == pytest.approx(-1.0)


def test_year_consistency_is_nan_without_comparable_years():
    assert np.isnan(year_consistency(_ratio_series({2020: list(BASE)})))  # um ano só: sem "outros anos"
    flat = _ratio_series({2020: [1.0] * 12, 2021: list(BASE)})
    # 2020 constante (desvio 0) é pulado; 2021 contra 2020 também (perfil constante).
    assert np.isnan(year_consistency(flat))
    short = _ratio_series({2020: list(BASE)[:5], 2021: list(BASE)[:5]})
    assert np.isnan(year_consistency(short))  # menos de 6 meses em cada ano
    assert year_consistency(short, min_months=5) == pytest.approx(1.0)


# ── Tabela por produto ──────────────────────────────────────────────


def _wide(**series: pd.Series) -> pd.DataFrame:
    wide = pd.DataFrame(series)
    wide.columns.name = "sk_product"
    return wide


def test_seasonality_table_hand_computed_row_and_metadata():
    exact = _periodic(5)
    wide = _wide(exact=exact, flat=pd.Series(4.0, index=exact.index))
    table = seasonality_table(wide, n_permutations=99)
    assert list(table.index) == ["exact"]  # a série constante não gera métricas
    assert table.index.name == "sk_product"
    row = table.loc["exact"]
    assert row["strength"] == pytest.approx(1.0)
    assert row["p_value"] == pytest.approx(0.01)
    assert row["q_value"] == pytest.approx(0.01)  # um só teste: sem correção
    assert bool(row["is_seasonal"]) is True


def test_seasonality_table_benjamini_hochberg_and_sorting():
    exact = _periodic(5)
    noisy = _series("flat", seed=5)
    noisy = pd.Series(noisy.to_numpy(), index=exact.index)
    wide = _wide(exact=exact, exact2=exact * 2, noisy=noisy)
    table = seasonality_table(wide, n_permutations=99)
    assert list(table["strength"]) == sorted(table["strength"], reverse=True)
    assert (table["q_value"] >= table["p_value"] - 1e-12).all()  # a correção nunca baixa o p-valor
    assert table["q_value"].between(0, 1).all()
    assert bool(table.loc["exact", "is_seasonal"]) and bool(table.loc["exact2", "is_seasonal"])


def test_seasonality_table_min_history_boundary():
    thirty_six = _periodic(3)
    wide = _wide(enough=thirty_six, short=thirty_six.iloc[:35].reindex(thirty_six.index))
    table = seasonality_table(wide, n_permutations=10)
    assert list(table.index) == ["enough"]  # 36 meses entram; 35 não
    assert set(seasonality_table(wide, min_history=35, n_permutations=10).index) == {"enough", "short"}


def test_seasonality_table_without_any_eligible_product_is_empty_with_columns():
    wide = _wide(flat=pd.Series(3.0, index=pd.date_range("2020-01-01", periods=48, freq="MS")))
    table = seasonality_table(wide, n_permutations=10)
    assert table.empty
    for column in ("strength", "p_value", "q_value", "is_seasonal"):
        assert column in table.columns


def test_seasonality_table_ignores_leading_nan_months_of_a_product():
    exact = _periodic(5)
    late = exact.copy()
    late.iloc[:12] = np.nan  # o produto só passa a existir no 2º ano
    table = seasonality_table(_wide(late=late), n_permutations=10)
    assert table.loc["late", "n_months"] == 48


def test_seasonality_table_passes_the_global_index_to_each_product():
    exact = _periodic(5)
    reversed_index = pd.Series((BASE / 65.0)[::-1], index=range(1, 13))
    table = seasonality_table(_wide(exact=exact), global_index=reversed_index, n_permutations=10)
    assert table.loc["exact", "corr_global"] == pytest.approx(-1.0)


# ── Rótulos, grade e matriz de produtos ─────────────────────────────


@pytest.mark.parametrize(
    ("strength", "label"),
    [(0.0, "fraca"), (0.19, "fraca"), (0.2, "moderada"), (0.49, "moderada"), (0.5, "forte"), (1.0, "forte")],
)
def test_strength_label_thresholds(strength, label):
    assert strength_label(strength) == label


def test_strength_label_of_nan_is_undefined_not_strong():
    assert strength_label(float("nan")) == "indefinida"


def test_year_month_grid_holds_the_ratios_by_year_and_month():
    grid = year_month_grid(_periodic(5))
    expected = BASE / 65.0
    # 2019 só tem jul-dez (perde 6 meses no início) e 2023 só jan-jun.
    assert grid.loc[2019, [1, 2, 3, 4, 5, 6]].isna().all()
    np.testing.assert_allclose(grid.loc[2019, [7, 8, 9, 10, 11, 12]].to_numpy(), expected[6:], rtol=1e-12)
    np.testing.assert_allclose(grid.loc[2021].to_numpy(), expected, rtol=1e-12)
    assert grid.loc[2023, [7, 8, 9, 10, 11, 12]].isna().all()


def test_product_month_matrix_sums_duplicates_and_fills_gaps_after_first_month():
    monthly = pd.DataFrame(
        {
            "sk_product": ["a", "a", "a", "b"],
            "month": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-04-01", "2024-03-01"]),
            "demand": [5.0, 2.0, 1.0, 9.0],
        }
    )
    wide = product_month_matrix(monthly)
    assert wide.columns.name == "sk_product"
    assert list(wide.index) == list(pd.date_range("2024-01-01", "2024-04-01", freq="MS"))
    assert wide["a"].tolist() == [7.0, 0.0, 0.0, 1.0]  # duplicata somada; meses sem registro = 0
    assert wide["b"].isna().tolist() == [True, True, False, False]
    assert wide["b"].tolist()[2:] == [9.0, 0.0]


def test_product_month_matrix_custom_column_names():
    monthly = pd.DataFrame({"p": ["x"], "m": pd.to_datetime(["2024-05-01"]), "q": [3.0]})
    wide = product_month_matrix(monthly, id_col="p", date_col="m", value_col="q")
    assert wide.columns.name == "p"
    assert wide["x"].tolist() == [3.0]


def test_product_month_matrix_of_empty_input_is_rejected():
    empty = pd.DataFrame({"sk_product": [], "month": pd.to_datetime([]), "demand": []})
    with pytest.raises(ValueError):
        product_month_matrix(empty)


# ── Um produto: matriz, resumo, temporada e pico ────────────────────


def test_year_month_matrix_hand_computed_cells():
    y = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2021-12-01", "2022-01-01", "2022-02-01"]))
    matrix = year_month_matrix(y)
    assert matrix.loc[2021, 12] == 1.0
    assert matrix.loc[2022, 1] == 2.0 and matrix.loc[2022, 2] == 3.0
    assert np.isnan(matrix.loc[2021, 1]) and np.isnan(matrix.loc[2022, 12])


def test_month_summary_hand_computed():
    matrix = year_month_matrix(
        pd.Series([1.0, 3.0, 5.0, 3.0], index=pd.to_datetime(["2021-01-01", "2021-02-01", "2022-01-01", "2022-02-01"]))
    )
    summary = month_summary(matrix)
    # 2021: média 2 (fev acima); 2022: média 4 (jan acima).
    assert summary.loc[1, ["media", "mediana", "anos", "anos_acima"]].tolist() == [3.0, 3.0, 2, 1]
    assert summary.loc[2, ["media", "mediana", "anos", "anos_acima"]].tolist() == [3.0, 3.0, 2, 1]
    assert summary.loc[7, "anos"] == 0 and summary.loc[7, "anos_acima"] == 0  # mês sem dado
    assert np.isnan(summary.loc[7, "media"])
    assert list(summary.index) == list(range(1, 13))


def test_month_summary_a_month_equal_to_the_year_average_is_not_above():
    matrix = year_month_matrix(pd.Series([2.0, 2.0], index=pd.to_datetime(["2021-01-01", "2021-02-01"])))
    assert month_summary(matrix).loc[1, "anos_acima"] == 0


def test_season_vs_offseason_hand_computed_means():
    y = pd.Series(1.0, index=pd.date_range("2021-05-01", "2022-10-01", freq="MS"))
    y.loc[[pd.Timestamp("2021-11-01"), pd.Timestamp("2021-12-01")]] = 10.0
    table = season_vs_offseason(y)
    # Temporada 2022, alta: nov e dez/21 (10 cada) + jan a abr/22 (1 cada) = 24 / 6 = 4; baixa: mai a out/22 = 1.
    assert table.loc[2022, ["meses_alta", "media_alta", "meses_baixa", "media_baixa"]].tolist() == [6, 4.0, 6, 1.0]
    # Temporada 2021 só tem baixa (mai a out/21): os meses de alta ficam indefinidos.
    assert table.loc[2021, "meses_baixa"] == 6 and table.loc[2021, "media_baixa"] == 1.0
    assert np.isnan(table.loc[2021, "meses_alta"])


def test_season_vs_offseason_series_with_only_high_season_months():
    y = pd.Series([4.0, 6.0, 8.0, 10.0], index=pd.date_range("2022-11-01", periods=4, freq="MS"))  # nov a fev
    table = season_vs_offseason(y)
    assert table.loc[2023, "meses_alta"] == 4
    assert table.loc[2023, "media_alta"] == 7.0
    assert np.isnan(table.loc[2023, "meses_baixa"]) and np.isnan(table.loc[2023, "media_baixa"])


def test_peak_profile_hand_computed_values():
    profile = peak_profile(_spiky_series())
    mean_of_year = (30.0 + 11 * 3.0) / 12  # 5,25
    assert list(profile.columns) == ["mes_pico", -2, -1, 0, 1, 2, 3]
    assert profile.loc[2022, 0] == pytest.approx(30.0 / mean_of_year)
    assert profile.loc[2022, -2] == pytest.approx(3.0 / mean_of_year)  # janeiro
    assert profile.loc[2022, 3] == pytest.approx(3.0 / mean_of_year)  # junho
    assert list(profile.index) == [2021, 2022, 2023]


def test_peak_profile_offsets_outside_the_series_are_nan_and_offsets_are_configurable():
    y = _spiky_series().copy()
    y[y.index.month == 3] = 3.0
    y[y.index.month == 1] = 30.0  # pico em janeiro
    profile = peak_profile(y, offsets=range(-1, 1))
    assert list(profile.columns) == ["mes_pico", -1, 0]
    assert np.isnan(profile.loc[2021, -1])  # dez/2020 não existe
    assert profile.loc[2022, -1] == pytest.approx(3.0 / ((30.0 + 11 * 3.0) / 12))  # dez/2021 existe


def test_peak_profile_without_complete_years_is_empty():
    y = _spiky_series().iloc[:11]
    assert peak_profile(y).empty


def test_peak_profile_a_year_without_demand_is_nan_not_a_warning():
    y = pd.Series(0.0, index=pd.date_range("2022-01-01", periods=12, freq="MS"))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        profile = peak_profile(y)
    assert profile.drop(columns="mes_pico").isna().all().all()
