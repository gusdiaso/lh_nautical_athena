"""Testes das peças compartilhadas de previsão: calendário de cortes e métricas de erro.

Os valores esperados foram calculados à mão (veja os comentários), não lidos da
saída do código.
"""

import datetime as dt
import math
import warnings

import numpy as np
import pandas as pd
import pytest

from src.analytics_ai.demand_common import (
    HORIZON,
    add_months,
    aggregated_error_table,
    as_bool,
    comparison_scorecard,
    cutoff_months,
    cutoff_wape,
    error_table,
    poisson_deviance,
    root_mean_squared_error,
    scorecard_vs_ruler,
)

SCORECARD_COLUMNS = [
    "wape_produto",
    "mae_produto",
    "rmse_produto",
    "wape_categoria_local",
    "wape_local",
    "vies",
    "desvio_poisson",
]


# ── as_bool ─────────────────────────────────────────────────────────


def test_as_bool_turns_nulls_into_false_without_warnings():
    series = pd.Series([True, None, False, np.nan, True], dtype=object)  # como o Delta entrega
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = as_bool(series)
    assert out.tolist() == [True, False, False, False, True]
    assert out.dtype == bool
    assert series.isna().sum() == 2  # entrada intacta


def test_as_bool_keeps_plain_boolean_columns_and_index():
    series = pd.Series([False, True], index=[10, 20])
    out = as_bool(series)
    assert out.tolist() == [False, True]
    assert out.index.tolist() == [10, 20]


def test_as_bool_can_be_used_as_a_row_mask_even_with_nulls():
    frame = pd.DataFrame({"x": [1, 2, 3], "flag": [True, None, True]})
    assert frame.loc[as_bool(frame["flag"]), "x"].tolist() == [1, 3]


# ── Calendário ──────────────────────────────────────────────────────


def test_horizon_is_three_months():
    assert HORIZON == 3


@pytest.mark.parametrize(
    ("start", "n", "expected"),
    [
        (dt.date(2024, 1, 1), 0, dt.date(2024, 1, 1)),
        (dt.date(2024, 1, 1), 1, dt.date(2024, 2, 1)),
        (dt.date(2024, 12, 1), 1, dt.date(2025, 1, 1)),  # virada de ano
        (dt.date(2024, 1, 1), -1, dt.date(2023, 12, 1)),  # virada de ano para trás
        (dt.date(2024, 11, 1), 3, dt.date(2025, 2, 1)),
        (dt.date(2024, 3, 1), -14, dt.date(2023, 1, 1)),  # 14 = 1 ano + 2 meses
        (dt.date(2024, 1, 1), 24, dt.date(2026, 1, 1)),
        (dt.date(2024, 12, 1), -12, dt.date(2023, 12, 1)),
        (dt.date(2024, 5, 1), 7, dt.date(2024, 12, 1)),
        (dt.date(2024, 5, 1), 8, dt.date(2025, 1, 1)),
    ],
)
def test_add_months(start, n, expected):
    assert add_months(start, n) == expected


def test_add_months_accepts_timestamp_and_returns_date():
    result = add_months(pd.Timestamp("2024-12-01"), 1)
    assert result == dt.date(2025, 1, 1)
    assert type(result) is dt.date


def test_cutoff_months_are_the_last_twelve_with_known_target():
    # Último mês completo = maio/2026: o último corte com alvo fechado é fev/2026
    # (alvo = mar, abr, mai). Os 12 cortes vão de mar/2025 a fev/2026.
    cutoffs = cutoff_months(dt.date(2026, 5, 1))
    assert len(cutoffs) == 12
    assert cutoffs[0] == dt.date(2025, 3, 1)
    assert cutoffs[-1] == dt.date(2026, 2, 1)
    assert cutoffs == sorted(cutoffs)
    assert all(add_months(a, 1) == b for a, b in zip(cutoffs, cutoffs[1:], strict=False))


def test_cutoff_months_single_cutoff_and_none():
    assert cutoff_months(dt.date(2026, 5, 1), n_cutoffs=1) == [dt.date(2026, 2, 1)]
    assert cutoff_months(dt.date(2026, 5, 1), n_cutoffs=0) == []


def test_cutoff_months_respects_horizon():
    assert cutoff_months(dt.date(2026, 5, 1), n_cutoffs=2, horizon=1) == [
        dt.date(2026, 3, 1),
        dt.date(2026, 4, 1),
    ]


def test_cutoff_target_window_never_passes_last_complete_month():
    last = dt.date(2025, 1, 1)
    for cutoff in cutoff_months(last, n_cutoffs=24):
        assert add_months(cutoff, HORIZON) <= last  # sem alvo no futuro


# ── error_table ─────────────────────────────────────────────────────


def _panel():
    return pd.DataFrame(
        {
            "grupo": ["g1", "g1", "g2", "g2"],
            "target_3m": [10.0, 0.0, 20.0, 10.0],
            "MM12": [12.0, 3.0, 15.0, 10.0],
            "modelo": [10.0, 0.0, 20.0, 10.0],
        }
    )


def test_error_table_total_wape_bias_and_relative_error():
    # MM12: |erros| = 2+3+5+0 = 10 sobre 40 reais -> 0,25; soma prevista 40 -> viés 0.
    # modelo: acerta tudo -> wape 0, viés 0, erro relativo 0/0,25 = 0.
    table = error_table(_panel(), {"MM12": "MM12", "modelo": "modelo"})
    assert list(table.columns) == ["regua", "n", "wape", "vies", "erro_relativo"]
    by_label = table.set_index("regua")
    assert by_label.loc["MM12", "n"] == 4
    assert by_label.loc["MM12", "wape"] == 0.25
    assert by_label.loc["MM12", "vies"] == 0.0
    assert by_label.loc["MM12", "erro_relativo"] == 1.0
    assert by_label.loc["modelo", "wape"] == 0.0
    assert by_label.loc["modelo", "erro_relativo"] == 0.0


def test_error_table_bias_sign_and_rounding():
    frame = pd.DataFrame({"target_3m": [3.0, 0.0], "p": [1.0, 0.0]})
    # WAPE = 2/3, viés = (1-3)/3 = -2/3 (previu abaixo) -> arredondados a 4 casas.
    row = error_table(frame, {"p": "p"}, reference=None).iloc[0]
    assert row["wape"] == 0.6667
    assert row["vies"] == -0.6667
    assert "erro_relativo" not in error_table(frame, {"p": "p"}, reference=None).columns


def test_error_table_reference_missing_from_forecasts_is_ignored():
    table = error_table(_panel(), {"modelo": "modelo"})  # 'MM12' não está no dicionário
    assert "erro_relativo" not in table.columns


def test_error_table_by_single_column():
    # g1: |2|+|3| = 5 sobre 10 reais -> 0,5; soma prevista 15 -> viés +0,5.
    # g2: 5+0 = 5 sobre 30 -> 0,1667; previsto 25 -> viés -5/30 = -0,1667.
    table = error_table(_panel(), {"MM12": "MM12", "modelo": "modelo"}, by=["grupo"])
    mm12 = table[table["regua"] == "MM12"].set_index("grupo")
    assert mm12.loc["g1", "wape"] == 0.5
    assert mm12.loc["g1", "vies"] == 0.5
    assert mm12.loc["g2", "wape"] == 0.1667
    assert mm12.loc["g2", "vies"] == -0.1667
    assert mm12["n"].tolist() == [2, 2]
    modelo = table[table["regua"] == "modelo"].set_index("grupo")
    assert modelo["erro_relativo"].tolist() == [0.0, 0.0]
    assert mm12["erro_relativo"].tolist() == [1.0, 1.0]
    assert len(table) == 4  # 2 grupos x 2 réguas


def test_error_table_by_two_columns_keeps_both_keys():
    frame = _panel().assign(loja=["a", "b", "a", "a"])
    table = error_table(frame, {"MM12": "MM12"}, by=["grupo", "loja"])
    got = table.set_index(["grupo", "loja"])
    assert set(got.index) == {("g1", "a"), ("g1", "b"), ("g2", "a")}
    # (g1,a): real 10, previsto 12 -> 0,2. (g2,a): erros 5+0 sobre 30 reais -> 0,1667.
    assert got.loc[("g1", "a"), "wape"] == 0.2
    assert got.loc[("g2", "a"), "wape"] == 0.1667
    assert got.loc[("g2", "a"), "n"] == 2
    # (g1,b) só tem venda real 0: WAPE indefinido, e o erro relativo também.
    assert np.isnan(got.loc[("g1", "b"), "wape"])
    assert np.isnan(got.loc[("g1", "b"), "erro_relativo"])
    # A régua de referência é ela mesma: erro relativo 1 onde está definido.
    assert got.loc[("g1", "a"), "erro_relativo"] == 1.0
    assert got.loc[("g2", "a"), "erro_relativo"] == 1.0


def test_error_table_zero_actual_is_undefined_not_infinite_and_does_not_warn():
    frame = pd.DataFrame({"target_3m": [0.0, 0.0], "p": [0.0, 2.0]})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        table = error_table(frame, {"p": "p"}, reference=None)
    assert np.isnan(table.loc[0, "wape"])
    assert np.isnan(table.loc[0, "vies"])


def test_error_table_group_with_zero_actual_does_not_hide_other_groups():
    frame = pd.DataFrame(
        {
            "g": ["a", "a", "b"],
            "target_3m": [0.0, 0.0, 4.0],
            "p": [1.0, 0.0, 2.0],
        }
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        table = error_table(frame, {"p": "p"}, by=["g"], reference=None).set_index("g")
    assert np.isnan(table.loc["a", "wape"])
    assert table.loc["b", "wape"] == 0.5  # |2-4| / 4


def test_error_table_empty_panel_returns_empty_table_with_columns():
    empty = _panel().iloc[0:0]
    grouped = error_table(empty, {"MM12": "MM12"}, by=["grupo"])
    assert grouped.empty
    assert list(grouped.columns) == ["grupo", "regua", "n", "wape", "vies", "erro_relativo"]


def test_error_table_without_group_on_empty_panel_is_undefined():
    empty = _panel().iloc[0:0]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        table = error_table(empty, {"MM12": "MM12"})
    assert table.loc[0, "n"] == 0
    assert np.isnan(table.loc[0, "wape"])


def test_error_table_does_not_mutate_input():
    frame = _panel()
    before = frame.copy()
    error_table(frame, {"MM12": "MM12"}, by=["grupo"])
    pd.testing.assert_frame_equal(frame, before)


def test_error_table_unknown_column_raises_keyerror():
    with pytest.raises(KeyError):
        error_table(_panel(), {"x": "nao_existe"})


# ── aggregated_error_table ──────────────────────────────────────────


def test_aggregated_error_table_sums_series_before_measuring():
    frame = pd.DataFrame(
        {
            "cutoff": [dt.date(2025, 1, 1)] * 4,
            "sk_location": [1, 1, 2, 2],
            "target_3m": [0.0, 4.0, 6.0, 2.0],
            "p": [4.0, 0.0, 2.0, 6.0],
        }
    )
    # Por série o erro seria 4+4+4+4 = 16 sobre 12 reais. Somando por loja:
    # loja 1: real 4, previsto 4 -> 0; loja 2: real 8, previsto 8 -> 0.
    table = aggregated_error_table(frame, {"p": "p"}, ["sk_location"])
    assert table.loc[0, "wape"] == 0.0
    assert table.loc[0, "n"] == 2  # duas séries agregadas (loja 1 e loja 2)


def test_aggregated_error_table_groups_by_cutoff_too():
    frame = pd.DataFrame(
        {
            "cutoff": [dt.date(2025, 1, 1), dt.date(2025, 2, 1)],
            "sk_location": [1, 1],
            "target_3m": [10.0, 10.0],
            "p": [5.0, 10.0],
        }
    )
    # Um mesmo local em dois cortes NÃO se soma: erros 5 e 0 sobre 20 reais = 0,25.
    table = aggregated_error_table(frame, {"p": "p"}, ["sk_location"])
    assert table.loc[0, "n"] == 2
    assert table.loc[0, "wape"] == 0.25


def test_aggregated_error_table_requires_cutoff_column():
    frame = pd.DataFrame({"sk_location": [1], "target_3m": [1.0], "p": [1.0]})
    with pytest.raises(KeyError):
        aggregated_error_table(frame, {"p": "p"}, ["sk_location"])


# ── Desvio de Poisson e RMSE ────────────────────────────────────────


def test_poisson_deviance_hand_computed():
    actual = pd.Series([0.0, 2.0, 4.0, 6.0])
    pred = pd.Series([1.0, 1.0, 5.0, 5.0])
    # termo = 2 * (y ln(y/mu) - (y - mu)); y = 0 contribui 2*mu.
    expected = np.mean(
        [
            2 * 1.0,
            2 * (2 * math.log(2 / 1) - (2 - 1)),
            2 * (4 * math.log(4 / 5) - (4 - 5)),
            2 * (6 * math.log(6 / 5) - (6 - 5)),
        ]
    )
    assert poisson_deviance(actual, pred) == pytest.approx(expected, rel=1e-12)


def test_poisson_deviance_is_zero_for_perfect_forecast_with_zeros():
    actual = pd.Series([0.0, 3.0, 7.0])
    assert poisson_deviance(actual, actual) == pytest.approx(0.0, abs=1e-5)


def test_poisson_deviance_zero_prediction_is_floored_not_infinite():
    value = poisson_deviance(pd.Series([3.0]), pd.Series([0.0]))
    assert math.isfinite(value)
    assert value > 20  # prever 0 quando vendeu 3 é muito penalizado


def test_poisson_deviance_is_minimised_by_the_mean_not_the_median():
    actual = pd.Series([0.0, 0.0, 0.0, 4.0])  # média 1, mediana 0
    at_mean = poisson_deviance(actual, pd.Series([1.0] * 4))
    at_median = poisson_deviance(actual, pd.Series([0.001] * 4))
    assert at_mean < at_median


def test_poisson_deviance_empty_series_is_undefined():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert math.isnan(poisson_deviance(pd.Series([], dtype=float), pd.Series([], dtype=float)))


def test_rmse_hand_computed():
    # erros: 1, -1, 1, -1 -> média dos quadrados 1 -> raiz 1.
    assert root_mean_squared_error(pd.Series([0.0, 2.0, 4.0, 6.0]), pd.Series([1.0, 1.0, 5.0, 5.0])) == 1.0
    # erros 3 e 4 -> (9+16)/2 = 12,5 -> raiz de 12,5.
    value = root_mean_squared_error(pd.Series([0.0, 0.0]), pd.Series([3.0, 4.0]))
    assert value == pytest.approx(math.sqrt(12.5), rel=1e-12)


def test_rmse_is_never_below_mae():
    actual = pd.Series([0.0, 0.0, 0.0, 10.0])
    pred = pd.Series([1.0, 1.0, 1.0, 1.0])
    mae = float((pred - actual).abs().mean())
    assert root_mean_squared_error(actual, pred) >= mae


def test_rmse_empty_series_is_undefined():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert math.isnan(root_mean_squared_error(pd.Series([], dtype=float), pd.Series([], dtype=float)))


# ── comparison_scorecard ────────────────────────────────────────────


def _scorecard_panel():
    return pd.DataFrame(
        {
            "cutoff": [dt.date(2025, 1, 1)] * 4,
            "category_name": ["A", "A", "B", "B"],
            "sk_location": [1, 1, 2, 2],
            "target_3m": [0.0, 2.0, 4.0, 6.0],
            "pred": [1.0, 1.0, 5.0, 5.0],
        }
    )


def test_scorecard_contract_columns_and_index():
    card = comparison_scorecard(_scorecard_panel(), {"teste": "pred"})
    assert list(card.columns) == SCORECARD_COLUMNS
    assert card.index.name == "previsao"
    assert list(card.index) == ["teste"]


def test_scorecard_has_no_legacy_duplicate_columns():
    card = comparison_scorecard(_scorecard_panel(), {"teste": "pred"})
    for legacy in ("erro_medio_unidades", "raiz_erro_quadratico", "erro_produto", "erro_categoria_local", "erro_local"):
        assert legacy not in card.columns


def test_scorecard_hand_computed_values():
    card = comparison_scorecard(_scorecard_panel(), {"teste": "pred"}).loc["teste"]
    assert card["wape_produto"] == round(4 / 12, 4)  # 4 erros de 1 sobre 12 vendidos
    assert card["mae_produto"] == 1.0
    assert card["rmse_produto"] == 1.0
    # Somando por categoria x loja os erros se cancelam: A (real 2, prev 2), B (real 10, prev 10).
    assert card["wape_categoria_local"] == 0.0
    assert card["wape_local"] == 0.0
    assert card["vies"] == 0.0
    expected_deviance = np.mean(
        [
            2 * 1.0,
            2 * (2 * math.log(2) - 1),
            2 * (4 * math.log(4 / 5) + 1),
            2 * (6 * math.log(6 / 5) - 1),
        ]
    )
    assert card["desvio_poisson"] == round(expected_deviance, 3)


def test_scorecard_compares_several_forecasts_on_the_same_panel():
    frame = _scorecard_panel().assign(perfeita=[0.0, 2.0, 4.0, 6.0], dobro=[0.0, 4.0, 8.0, 12.0])
    card = comparison_scorecard(frame, {"perfeita": "perfeita", "dobro": "dobro"})
    assert list(card.index) == ["perfeita", "dobro"]
    assert card.loc["perfeita", "wape_produto"] == 0.0
    assert card.loc["perfeita", "rmse_produto"] == 0.0
    # dobro: erros 0, 2, 4, 6 -> 12 sobre 12 -> wape 1; viés (24-12)/12 = 1; MAE 3.
    assert card.loc["dobro", "wape_produto"] == 1.0
    assert card.loc["dobro", "vies"] == 1.0
    assert card.loc["dobro", "mae_produto"] == 3.0
    assert card.loc["dobro", "rmse_produto"] == round(math.sqrt((0 + 4 + 16 + 36) / 4), 2)


def test_scorecard_aggregated_levels_are_configurable():
    frame = pd.DataFrame(
        {
            "cutoff": [dt.date(2025, 1, 1)] * 4,
            "category_name": ["A", "A", "B", "B"],
            "sk_location": [1, 2, 1, 2],
            "target_3m": [2.0, 2.0, 4.0, 4.0],
            "pred": [4.0, 0.0, 4.0, 4.0],
        }
    )
    # categoria x loja (padrão): (A,1) erra 2, (A,2) erra 2, B acerta -> 4/12.
    default = comparison_scorecard(frame, {"p": "pred"}).loc["p"]
    assert default["wape_categoria_local"] == round(4 / 12, 4)
    # loja: loja 1 real 6 prev 8; loja 2 real 6 prev 4 -> erros 2 + 2 -> 4/12.
    assert default["wape_local"] == round(4 / 12, 4)
    # só categoria: A real 4 prev 4, B real 8 prev 8 -> 0.
    by_category = comparison_scorecard(
        frame, {"p": "pred"}, group_level=("category_name",), location_level=("category_name",)
    ).loc["p"]
    assert by_category["wape_categoria_local"] == 0.0
    assert by_category["wape_local"] == 0.0
    assert by_category["wape_produto"] == round(4 / 12, 4)  # o nível por produto não muda


def test_scorecard_zero_actual_is_undefined_without_warnings():
    frame = _scorecard_panel().assign(target_3m=0.0)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        card = comparison_scorecard(frame, {"p": "pred"}).loc["p"]
    for column in ("wape_produto", "wape_categoria_local", "wape_local", "vies"):
        assert np.isnan(card[column])
    assert card["mae_produto"] == 3.0  # (1+1+5+5)/4: não depende de o real ser zero


def test_scorecard_uses_the_actual_column_argument():
    frame = _scorecard_panel().rename(columns={"target_3m": "real"})
    card = comparison_scorecard(frame, {"p": "pred"}, actual_col="real")
    assert card.loc["p", "mae_produto"] == 1.0


# ── cutoff_wape e scorecard_vs_ruler ────────────────────────────────


def _two_cutoff_panel() -> pd.DataFrame:
    """Dois cortes, uma categoria × local. Corte 1: real 10, régua acerta, método erra 2.
    Corte 2: real 10, régua erra 4, método acerta."""
    return pd.DataFrame(
        {
            "cutoff": [dt.date(2025, 1, 1)] * 2 + [dt.date(2025, 2, 1)] * 2,
            "category_name": ["A"] * 4,
            "sk_location": [1] * 4,
            "target_3m": [4.0, 6.0, 4.0, 6.0],
            "ruler": [4.0, 6.0, 6.0, 8.0],
            "method": [3.0, 5.0, 4.0, 6.0],
        }
    )


def test_cutoff_wape_is_one_value_per_cutoff():
    frame = _two_cutoff_panel()
    # Corte 1: |10-10|/10 = 0 (régua) e |8-10|/10 = 0,2 (método); corte 2: 0,4 e 0.
    ruler = cutoff_wape(frame, "ruler")
    method = cutoff_wape(frame, "method")
    assert ruler.round(4).tolist() == [0.0, 0.4]
    assert method.round(4).tolist() == [0.2, 0.0]
    assert ruler.index.tolist() == [dt.date(2025, 1, 1), dt.date(2025, 2, 1)]


def test_cutoff_wape_sums_series_before_taking_the_error():
    frame = _two_cutoff_panel().iloc[:2].assign(method=[10.0, 0.0])
    # Por série o método erra 6 + 6; somadas (real 10, previsto 10) o erro se compensa.
    assert cutoff_wape(frame, "method").tolist() == [0.0]


def test_scorecard_vs_ruler_counts_cutoffs_won_and_marks_the_ruler():
    frame = _two_cutoff_panel()
    table = scorecard_vs_ruler(frame, {"Régua final": "ruler", "Outro": "method"}, ruler_col="ruler")
    # O método ganha só no corte 2 (0 < 0,4); no corte 1 perde (0,2 > 0).
    assert table.loc["Outro", "Cortes ganhos da régua (de 12)"] == "1"
    assert table.loc["Régua final", "Cortes ganhos da régua (de 12)"] == "–"
    # Régua: erro por categoria no local = (0 + 4) / 20 = 20%; viés = (24 - 20) / 20 = 20%.
    assert table.loc["Régua final", "Erro por categoria no local (%)"] == 20.0
    assert table.loc["Régua final", "Viés (%)"] == 20.0


def test_scorecard_vs_ruler_does_not_invent_a_ruler_row():
    frame = _two_cutoff_panel()
    table = scorecard_vs_ruler(frame, {"Outro": "method"}, ruler_col="ruler")
    assert table.index.tolist() == ["Outro"]
