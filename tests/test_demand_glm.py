"""Testes do GLM de previsão de demanda.

Todos offline: nenhum teste aqui abre sessão Spark nem lê tabela do
Databricks. O que é exercitado é a matemática do offset, a integridade do
split temporal, a decomposição mensal e os contratos de métrica.
"""

import datetime as dt
import inspect
import unittest
import unittest.mock
import warnings
from dataclasses import replace
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from src.analytics_ai.demand_common import comparison_scorecard, root_mean_squared_error
from src.analytics_ai.demand_glm import (
    BASELINE_COL,
    CUTOFF_COL,
    EXCLUDED_FROM_TRAINING,
    FEATURE_STEPS,
    ID_COLS,
    NEVER_SOLD_MONTHS,
    SEASONAL_COLS,
    TARGET_COL,
    TEST_END,
    TRAIN_END,
    VALIDATION_END,
    DemandSplits,
    GlmConfig,
    add_predictions,
    build_pipeline,
    check_no_nulls,
    coefficient_table,
    decompose_months,
    fit_glm,
    normalize_panel,
    offset_values,
    offset_weights,
    predict_total,
    prepare_features,
    scorecard_by_cutoff,
    select_power,
    split_panel,
    wins_by_cutoff,
)
from src.analytics_ai.ml_config import MlModelConfig


def _painel(cutoffs, n_series=4, seed=0, trend_ready=True, target_complete=True):
    """Painel sintético mínimo com as colunas que o módulo exige."""
    rng = np.random.default_rng(seed)
    linhas = []
    for cutoff in cutoffs:
        for s in range(n_series):
            linhas.append(
                {
                    "cutoff": cutoff,
                    "sk_product": 100 + s,
                    "sk_location": 1 + (s % 2),
                    "sku": f"SKU{s}",
                    "product_name": f"Produto {s}",
                    "category_name": f"Cat{s % 2}",
                    "location_name": f"Loja{1 + (s % 2)}",
                    "categoria_local_avg_12m": float(12 + s),
                    "season_sum_next_3m": 3.0,
                    "trend_factor": 1.1,
                    "sum_12m": float(10 + s),
                    "sum_3m": float(2 + s),
                    "produto_locais_avg_12m": float(9 + s),
                    "categoria_local_n_series": float(20 + s),
                    "produto_locais_n_locations": 6.0,
                    "months_with_sale_12m": float(s % 12),
                    "months_since_last_sale": float(s % 4),
                    "is_stopped_12m": s % 5 == 0,
                    "frequency_class": ("alta", "media", "baixa", "sem_venda")[s % 4],
                    "brand_name": f"Marca{s % 3}",
                    "location_type": ("loja", "armazem")[s % 2],
                    "region": f"Regiao{s % 2}",
                    "sale_price": float(100 + s),
                    "seasonal_index_month_plus1": 1.0,
                    "seasonal_index_month_plus2": 1.2,
                    "seasonal_index_month_plus3": 0.8,
                    "trend_ready": trend_ready,
                    "is_target_complete": target_complete,
                    BASELINE_COL: float(1 + s),
                    "target_3m": float(rng.integers(0, 8)),
                }
            )
    # Passa pelo mesmo preparo que `split_panel` aplica em produção, para que
    # as colunas derivadas (nunca_vendeu) existam também nos testes.
    return prepare_features(pd.DataFrame(linhas))


class SplitPanelTest(unittest.TestCase):
    """O recorte é temporal e não deixa linha escapar para o lado errado."""

    def setUp(self):
        cutoffs = [dt.date(2024, m, 1) for m in (4, 5)]
        cutoffs += [dt.date(2024, 8, 1), dt.date(2025, 8, 1)]
        self.painel = _painel(cutoffs)

    def test_split_separa_por_corte_sem_sobreposicao(self):
        splits = split_panel(self.painel)
        chaves = []
        for parte in (splits.train, splits.validation, splits.test):
            chaves.append(
                set(zip(parte["sk_product"], parte["sk_location"], parte["cutoff"], strict=True))
            )
        self.assertEqual(set(), chaves[0] & chaves[1])
        self.assertEqual(set(), chaves[1] & chaves[2])
        self.assertEqual(set(), chaves[0] & chaves[2])
        self.assertEqual({dt.date(2024, 4, 1), dt.date(2024, 5, 1)}, set(splits.train["cutoff"]))
        self.assertEqual({dt.date(2024, 8, 1)}, set(splits.validation["cutoff"]))
        self.assertEqual({dt.date(2025, 8, 1)}, set(splits.test["cutoff"]))

    def test_treino_exclui_trend_ready_false(self):
        painel = self.painel.copy()
        painel.loc[painel["cutoff"] == dt.date(2024, 4, 1), "trend_ready"] = False
        splits = split_panel(painel)
        self.assertEqual({dt.date(2024, 5, 1)}, set(splits.train["cutoff"]))
        self.assertEqual(4, splits.n_discarded)

    def test_scoring_com_trend_ready_false_levanta_erro(self):
        painel = self.painel.copy()
        painel.loc[painel["cutoff"] == dt.date(2025, 8, 1), "trend_ready"] = False
        with self.assertRaises(ValueError) as ctx:
            split_panel(painel)
        self.assertIn("teste", str(ctx.exception))

    def test_inferencia_recebe_linhas_sem_alvo_completo(self):
        painel = self.painel.copy()
        recente = painel["cutoff"] == dt.date(2025, 8, 1)
        painel.loc[recente, "is_target_complete"] = False
        painel.loc[recente, "target_3m"] = np.nan
        splits = split_panel(painel)
        self.assertEqual(4, len(splits.inference))
        self.assertEqual(0, len(splits.test))
        self.assertTrue(splits.inference["target_3m"].isna().all())

    def test_embargo_encurta_o_treino(self):
        splits = split_panel(self.painel, embargo_cutoffs=1)
        self.assertEqual({dt.date(2024, 4, 1)}, set(splits.train["cutoff"]))


class OffsetTest(unittest.TestCase):
    """A régua entra como exposição: é aqui que o modelo pode silenciosamente errar."""

    def test_peso_do_offset_por_familia(self):
        e = np.array([1.0, 4.0, 9.0])
        np.testing.assert_allclose(offset_weights(e, "poisson", 1.0), e)
        np.testing.assert_allclose(offset_weights(e, "tweedie", 1.5), np.sqrt(e))
        np.testing.assert_allclose(offset_weights(e, "tweedie", 1.9), e**0.1)
        np.testing.assert_allclose(offset_weights(e, "tweedie", 1.0), e)

    def test_offset_recupera_coeficientes_verdadeiros(self):
        rng = np.random.default_rng(42)
        n = 40000
        x1, x2 = rng.normal(size=n), rng.normal(size=n)
        e = rng.gamma(2.0, 2.0, size=n) + 0.05
        mu = e * np.exp(0.15 + 0.30 * x1 - 0.20 * x2)
        frame = pd.DataFrame(
            {
                "x1": x1,
                "x2": x2,
                BASELINE_COL: e,
                "target_3m": rng.poisson(mu).astype(float),
            }
        )
        config = GlmConfig(
            name="offset",
            family="poisson",
            alpha=0.0,
            use_offset=True,
            scale=False,
            numeric_features=("x1", "x2"),
        )
        modelo = fit_glm(frame, config)
        coef = modelo.pipeline.named_steps["model"].coef_
        self.assertAlmostEqual(0.30, float(coef[0]), places=2)
        self.assertAlmostEqual(-0.20, float(coef[1]), places=2)
        self.assertAlmostEqual(0.15, float(modelo.pipeline.named_steps["model"].intercept_), places=2)

    def test_piso_do_baseline_evita_log_de_zero(self):
        frame = _painel([dt.date(2024, 1, 1)], n_series=6)
        frame[BASELINE_COL] = 0.0
        config = FEATURE_STEPS["passo2_offset"]
        modelo = fit_glm(frame, config)
        pred = predict_total(modelo, frame)
        self.assertTrue(np.all(np.isfinite(pred)))
        self.assertTrue(np.all(pred >= 0))
        self.assertEqual(len(frame), modelo.n_baseline_no_piso)

    def test_intercepto_puro_recalibra_a_regua(self):
        rng = np.random.default_rng(7)
        n = 20000
        e = rng.gamma(2.0, 2.0, size=n) + 0.05
        frame = pd.DataFrame(
            {BASELINE_COL: e, "target_3m": rng.poisson(e * 1.37).astype(float)}
        )
        modelo = fit_glm(frame, FEATURE_STEPS["passo2_offset"])
        fator = float(np.exp(modelo.pipeline.named_steps["model"].intercept_))
        esperado = float(frame["target_3m"].sum() / e.sum())
        self.assertAlmostEqual(esperado, fator, places=4)


class NestedBaselineTest(unittest.TestCase):
    """A régua é um caso particular do passo 1 — e o código tem de saber disso."""

    def test_passo1_reproduz_a_regua_quando_ela_e_a_verdade(self):
        rng = np.random.default_rng(3)
        n = 3000
        nivel = rng.gamma(4.0, 3.0, size=n) + 1.0
        estacao = rng.uniform(2.0, 4.0, size=n)
        tendencia = rng.uniform(0.9, 1.3, size=n)
        regua = nivel / 12.0 * estacao * tendencia
        frame = pd.DataFrame(
            {
                "categoria_local_avg_12m": nivel,
                "season_sum_next_3m": estacao,
                "trend_factor": tendencia,
                BASELINE_COL: regua,
                "target_3m": regua,
            }
        )
        modelo = fit_glm(frame, FEATURE_STEPS["passo1_nested"])
        coef = dict(zip(modelo.feature_names, modelo.pipeline.named_steps["model"].coef_, strict=True))
        for nome, valor in coef.items():
            self.assertAlmostEqual(1.0, float(valor), places=3, msg=f"{nome} deveria valer 1")
        self.assertAlmostEqual(
            -np.log(12.0), float(modelo.pipeline.named_steps["model"].intercept_), places=3
        )
        np.testing.assert_allclose(predict_total(modelo, frame), regua, rtol=1e-4)


class PipelineContractTest(unittest.TestCase):
    """Nenhuma coluna proibida chega ao modelo, por construção."""

    def test_features_proibidas_fora_de_todos_os_passos(self):
        for nome, config in FEATURE_STEPS.items():
            with self.subTest(passo=nome):
                self.assertEqual(
                    set(), set(config.all_features) & set(EXCLUDED_FROM_TRAINING)
                )

    def test_column_transformer_descarta_colunas_extras(self):
        frame = _painel([dt.date(2024, 1, 1)], n_series=8)
        modelo = fit_glm(frame, FEATURE_STEPS["passo3_historico"])
        nomes = " ".join(modelo.feature_names)
        for proibida in ("sku", "product_name", "cutoff", "target_3m"):
            self.assertNotIn(proibida, nomes)

    def test_fit_recusa_feature_proibida(self):
        frame = _painel([dt.date(2024, 1, 1)], n_series=6)
        config = GlmConfig(name="ruim", use_offset=False, numeric_features=("target_3m",))
        with self.assertRaises(ValueError) as ctx:
            fit_glm(frame, config)
        self.assertIn("proibidas", str(ctx.exception))

    def test_previsao_nunca_negativa_nem_nan(self):
        frame = _painel([dt.date(2024, 1, 1)], n_series=8)
        modelo = fit_glm(frame, FEATURE_STEPS["passo3_historico"])
        extremo = frame.copy()
        extremo["sum_12m"] = 1e9
        pred = predict_total(modelo, extremo)
        self.assertTrue(np.all(np.isfinite(pred)))
        self.assertTrue(np.all(pred >= 0))
        teto = modelo.config.mu_cap_ratio * np.maximum(
            extremo[BASELINE_COL], modelo.config.baseline_floor
        )
        self.assertTrue(np.all(pred <= teto + 1e-9))

    def test_check_no_nulls_nomeia_a_coluna(self):
        frame = _painel([dt.date(2024, 1, 1)], n_series=3)
        frame.loc[0, "sum_12m"] = np.nan
        with self.assertRaises(ValueError) as ctx:
            check_no_nulls(frame, ["sum_12m", "sum_3m"])
        self.assertIn("sum_12m=1", str(ctx.exception))

    def test_add_predictions_preserva_linhas(self):
        frame = _painel([dt.date(2024, 1, 1)], n_series=5)
        modelo = fit_glm(frame, FEATURE_STEPS["passo2_offset"])
        saida = add_predictions(frame, modelo, "pred_glm")
        self.assertEqual(len(frame), len(saida))
        self.assertIn("pred_glm", saida.columns)
        self.assertNotIn("pred_glm", frame.columns)


class DecomposeMonthsTest(unittest.TestCase):
    """O total de 3 meses vira 3 meses sem criar nem perder demanda."""

    def setUp(self):
        self.frame = _painel([dt.date(2026, 8, 1)], n_series=3)
        self.frame["pred_total"] = [6.0, 9.0, 3.0]

    def test_decomposicao_soma_o_total(self):
        mensal = decompose_months(self.frame, "pred_total")
        self.assertEqual(9, len(mensal))
        soma = mensal.groupby(["sk_product", "sk_location"])["demanda_prevista"].sum()
        esperado = self.frame.set_index(["sk_product", "sk_location"])["pred_total"]
        pd.testing.assert_series_equal(
            soma.sort_index(), esperado.sort_index(), check_names=False
        )

    def test_decomposicao_gera_os_tres_meses_seguintes(self):
        mensal = decompose_months(self.frame, "pred_total")
        self.assertEqual(
            {dt.date(2026, 9, 1), dt.date(2026, 10, 1), dt.date(2026, 11, 1)},
            set(mensal["mes_previsto"]),
        )
        self.assertEqual({1, 2, 3}, set(mensal["horizonte_mes"]))

    def test_decomposicao_ignora_season_sum_arredondado(self):
        errado = self.frame.copy()
        errado["season_sum_next_3m"] = 99.0
        pd.testing.assert_frame_equal(
            decompose_months(self.frame, "pred_total"),
            decompose_months(errado, "pred_total").assign(season_sum_next_3m=3.0),
        )

    def test_decomposicao_usa_o_peso_sazonal(self):
        mensal = decompose_months(self.frame, "pred_total")
        primeiro = mensal[mensal["horizonte_mes"] == 1]["share_sazonal"].unique()
        self.assertAlmostEqual(1.0 / 3.0, float(primeiro[0]))

    def test_decomposicao_rejeita_indice_nao_positivo(self):
        ruim = self.frame.copy()
        ruim[["seasonal_index_month_plus1", "seasonal_index_month_plus2", "seasonal_index_month_plus3"]] = 0.0
        with self.assertRaises(ValueError):
            decompose_months(ruim, "pred_total")

    def test_decomposicao_preserva_nao_negatividade(self):
        mensal = decompose_months(self.frame, "pred_total")
        self.assertTrue(np.all(mensal["demanda_prevista"] >= 0))


class MetricsTest(unittest.TestCase):
    """As métricas do projeto continuam valendo, e ganham RMSE."""

    def setUp(self):
        self.frame = pd.DataFrame(
            {
                "cutoff": [dt.date(2025, 1, 1)] * 4,
                "category_name": ["A", "A", "B", "B"],
                "sk_location": [1, 1, 2, 2],
                "target_3m": [0.0, 2.0, 4.0, 6.0],
                "pred": [1.0, 1.0, 5.0, 5.0],
            }
        )

    def test_rmse_valor_conhecido(self):
        actual = pd.Series([0.0, 2.0, 4.0, 6.0])
        pred = pd.Series([1.0, 1.0, 5.0, 5.0])
        self.assertAlmostEqual(1.0, root_mean_squared_error(actual, pred))

    def test_comparison_scorecard_mantem_colunas_anteriores(self):
        placar = comparison_scorecard(self.frame, {"teste": "pred"})
        for coluna in (
            "wape_produto",
            "wape_categoria_local",
            "wape_local",
            "vies",
            "mae_produto",
            "desvio_poisson",
            "rmse_produto",
        ):
            self.assertIn(coluna, placar.columns)
        for legado in ("erro_produto", "erro_categoria_local", "erro_local", "erro_medio_unidades", "raiz_erro_quadratico"):
            self.assertNotIn(legado, placar.columns)
        self.assertAlmostEqual(4.0 / 12.0, float(placar.loc["teste", "wape_produto"]), places=4)
        self.assertAlmostEqual(1.0, float(placar.loc["teste", "mae_produto"]))
        self.assertAlmostEqual(1.0, float(placar.loc["teste", "rmse_produto"]))

    def test_wape_soma_absoluta_sobre_soma_real(self):
        placar = comparison_scorecard(self.frame, {"teste": "pred"})
        esperado = (self.frame["pred"] - self.frame["target_3m"]).abs().sum() / self.frame[
            "target_3m"
        ].sum()
        self.assertAlmostEqual(esperado, float(placar.loc["teste", "wape_produto"]), places=4)


class ConfigTest(unittest.TestCase):
    """Os nomes de tabela saem do ambiente, nunca hardcoded no código."""

    def test_ml_model_config_usa_variaveis_de_ambiente(self):
        with unittest.mock.patch.dict(
            "os.environ",
            {"ML_CATALOG": "prod_lh_nautical", "ML_FORECAST_TABLE": "outra_tabela"},
            clear=False,
        ):
            config = MlModelConfig.from_environment()
        self.assertEqual("prod_lh_nautical.ml.outra_tabela", config.forecast_target)
        self.assertEqual(
            "prod_lh_nautical.ml.ml_features_produto_loja_mes", config.features_source
        )

    def test_defaults_apontam_para_dev(self):
        with unittest.mock.patch.dict("os.environ", {}, clear=True):
            config = MlModelConfig.from_environment()
        self.assertEqual("dev_lh_nautical.ml.ml_forecast_demanda_mensal", config.forecast_monthly_target)


# ── Testes adicionais (pytest) ──────────────────────────────────────

SCORECARD_COLUMNS = [
    "wape_produto",
    "mae_produto",
    "rmse_produto",
    "wape_categoria_local",
    "wape_local",
    "vies",
    "desvio_poisson",
]


def test_module_constants():
    assert TARGET_COL == "target_3m"
    assert BASELINE_COL == "baseline_pred_categoria_local_idx_trend"
    assert CUTOFF_COL == "cutoff"
    assert ID_COLS == ("sk_product", "sk_location")
    assert SEASONAL_COLS == (
        "seasonal_index_month_plus1",
        "seasonal_index_month_plus2",
        "seasonal_index_month_plus3",
    )
    assert NEVER_SOLD_MONTHS == 60.0
    assert (TRAIN_END, VALIDATION_END, TEST_END) == (dt.date(2024, 5, 1), dt.date(2025, 5, 1), dt.date(2026, 5, 1))
    for coluna in ("sk_product", "sk_location", "sku", "product_name", "cutoff", "target_3m", "is_target_complete", "trend_ready"):
        assert coluna in EXCLUDED_FROM_TRAINING


def test_glm_config_features_order_and_effective_power():
    config = GlmConfig(
        name="x",
        log_features=("a",),
        log1p_features=("b",),
        numeric_features=("c",),
        categorical_features=("d",),
        family="poisson",
        power=1.7,
    )
    assert config.all_features == ("a", "b", "c", "d")
    assert config.tweedie_power == 1.0  # Poisson ignora o power informado
    assert GlmConfig(name="y", family="tweedie", power=1.7).tweedie_power == 1.7


def test_feature_steps_are_named_after_their_keys_and_defined_in_order():
    assert list(FEATURE_STEPS) == [
        "passo1_nested",
        "passo2_offset",
        "passo3_historico",
        "passo4_categoricas_baratas",
        "passo5_categoricas_caras",
    ]
    for chave, config in FEATURE_STEPS.items():
        assert config.name == chave
    assert FEATURE_STEPS["passo1_nested"].use_offset is False
    assert all(FEATURE_STEPS[c].use_offset for c in list(FEATURE_STEPS)[1:])


# ── normalize_panel / prepare_features ──────────────────────────────


def test_normalize_panel_converts_decimal_columns_and_leaves_the_rest():
    frame = pd.DataFrame(
        {
            "dec": [Decimal("1.50"), None, Decimal("3.25")],
            "texto": ["a", "b", "c"],
            "sk_product": ["abc123", "def456", "0f0f0f"],
            "num": [1.0, 2.0, 3.0],
            "so_none": [None, None, None],
        }
    )
    out = normalize_panel(frame)
    assert out["dec"].dtype == np.float64
    assert out["dec"].iloc[0] == 1.5 and out["dec"].iloc[2] == 3.25 and np.isnan(out["dec"].iloc[1])
    assert out["texto"].tolist() == ["a", "b", "c"]
    assert out["sk_product"].tolist() == ["abc123", "def456", "0f0f0f"]  # hash em texto não vira número
    assert out["so_none"].isna().all()
    assert frame["dec"].dtype == object  # a entrada não é alterada


def test_prepare_features_flags_never_sold_series_with_a_fixed_sentinel():
    frame = pd.DataFrame(
        {
            "months_since_last_sale": [Decimal("3"), None, Decimal("0"), None],  # DECIMAL do Delta
            "sum_12m": [5.0, 0.0, 2.0, 0.0],
        }
    )
    out = prepare_features(frame)
    assert out["nunca_vendeu"].tolist() == [False, True, False, True]
    assert out["months_since_last_sale"].tolist() == [3.0, 60.0, 0.0, 60.0]
    assert out["months_since_last_sale"].notna().all()
    assert frame["months_since_last_sale"].isna().sum() == 2  # entrada intacta


# ── split_panel ─────────────────────────────────────────────────────


def test_split_boundaries_are_inclusive_on_the_right_and_leave_nothing_out_of_order():
    cutoffs = [
        dt.date(2024, 5, 1),  # = TRAIN_END: treino
        dt.date(2024, 6, 1),  # 1º mês da validação
        dt.date(2025, 5, 1),  # = VALIDATION_END: validação
        dt.date(2025, 6, 1),  # 1º mês do teste
        dt.date(2026, 5, 1),  # = TEST_END: teste
        dt.date(2026, 6, 1),  # depois do teste, com alvo completo: fora de todos
    ]
    splits = split_panel(_painel(cutoffs, n_series=2))
    assert set(splits.train["cutoff"]) == {dt.date(2024, 5, 1)}
    assert set(splits.validation["cutoff"]) == {dt.date(2024, 6, 1), dt.date(2025, 5, 1)}
    assert set(splits.test["cutoff"]) == {dt.date(2025, 6, 1), dt.date(2026, 5, 1)}
    assert len(splits.inference) == 0
    assert splits.train["cutoff"].max() < splits.validation["cutoff"].min()
    assert splits.validation["cutoff"].max() < splits.test["cutoff"].min()
    total = len(splits.train) + len(splits.validation) + len(splits.test)
    assert total == 5 * 2  # o corte de jun/2026 não entra em nenhum recorte


def test_split_does_not_modify_the_input_and_resets_indexes():
    painel = _painel([dt.date(2024, 4, 1), dt.date(2024, 8, 1)], n_series=2)
    antes = painel.copy()
    splits = split_panel(painel)
    pd.testing.assert_frame_equal(painel, antes)
    for parte in (splits.train, splits.validation, splits.test, splits.inference):
        assert list(parte.index) == list(range(len(parte)))


def test_split_treats_null_target_complete_as_inference():
    painel = _painel([dt.date(2024, 4, 1)], n_series=2)
    painel["is_target_complete"] = [None, False]
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # nenhum FutureWarning de fillna em coluna de objetos
        splits = split_panel(painel)
    assert len(splits.inference) == 2 and len(splits.train) == 0


def test_split_inference_without_trend_is_an_error():
    painel = _painel([dt.date(2026, 8, 1)], n_series=2, target_complete=False, trend_ready=False)
    with pytest.raises(ValueError, match="inferencia"):
        split_panel(painel)


def test_split_validation_without_trend_is_an_error():
    painel = _painel([dt.date(2024, 8, 1)], n_series=2, trend_ready=False)
    with pytest.raises(ValueError, match="validacao"):
        split_panel(painel)


def test_split_accepts_string_and_timestamp_cutoffs():
    painel = _painel([dt.date(2024, 4, 1), dt.date(2024, 8, 1)], n_series=2)
    painel["cutoff"] = pd.to_datetime(painel["cutoff"])
    splits = split_panel(painel)
    assert set(splits.train["cutoff"]) == {dt.date(2024, 4, 1)}
    assert set(splits.validation["cutoff"]) == {dt.date(2024, 8, 1)}


def test_split_custom_boundaries():
    painel = _painel([dt.date(2023, 1, 1), dt.date(2023, 2, 1), dt.date(2023, 3, 1)], n_series=1)
    splits = split_panel(
        painel, train_end=dt.date(2023, 1, 1), validation_end=dt.date(2023, 2, 1), test_end=dt.date(2023, 3, 1)
    )
    assert [len(p) for p in (splits.train, splits.validation, splits.test)] == [1, 1, 1]


def test_embargo_drops_cutoffs_whose_target_overlaps_the_validation():
    cutoffs = [dt.date(2024, m, 1) for m in (3, 4, 5)] + [dt.date(2024, 8, 1)]
    splits = split_panel(_painel(cutoffs, n_series=1), embargo_cutoffs=2)
    # Treino termina em maio - 2 meses = março.
    assert set(splits.train["cutoff"]) == {dt.date(2024, 3, 1)}


def test_demand_splits_defaults():
    vazio = pd.DataFrame()
    assert DemandSplits(vazio, vazio, vazio, vazio).n_discarded == 0


# ── check_no_nulls / offset_values ──────────────────────────────────


def test_check_no_nulls_reports_missing_columns_before_nulls():
    frame = pd.DataFrame({"a": [1.0, np.nan]})
    with pytest.raises(ValueError, match="ausentes"):
        check_no_nulls(frame, ["a", "b"])


def test_check_no_nulls_lists_every_affected_column_with_counts():
    frame = pd.DataFrame({"a": [1.0, np.nan, np.nan], "b": [None, 1.0, 2.0], "c": [1, 2, 3]})
    with pytest.raises(ValueError) as erro:
        check_no_nulls(frame, ["a", "b", "c"])
    assert "a=2" in str(erro.value) and "b=1" in str(erro.value) and "c=" not in str(erro.value)
    check_no_nulls(frame, ["c"])  # sem nulos: não levanta


def test_offset_values_apply_the_floor():
    frame = pd.DataFrame({BASELINE_COL: [0.0, 0.005, 0.01, 2.0]})
    np.testing.assert_array_equal(offset_values(frame, 0.01), [0.01, 0.01, 0.01, 2.0])


# ── Pipeline e ajuste ───────────────────────────────────────────────


def test_build_pipeline_selects_estimator_by_family_and_drops_extra_columns():
    poisson = build_pipeline(GlmConfig(name="p", numeric_features=("x",)))
    assert type(poisson.named_steps["model"]).__name__ == "PoissonRegressor"
    tweedie = build_pipeline(GlmConfig(name="t", family="tweedie", power=1.5, alpha=0.3, numeric_features=("x",)))
    modelo = tweedie.named_steps["model"]
    assert type(modelo).__name__ == "TweedieRegressor"
    assert (modelo.power, modelo.alpha, modelo.link) == (1.5, 0.3, "log")
    assert poisson.named_steps["prep"].remainder == "drop"


def test_intercept_only_pipeline_has_a_single_dead_column():
    frame = pd.DataFrame({BASELINE_COL: [1.0, 2.0, 3.0], "target_3m": [1.0, 2.0, 4.0]})
    config = GlmConfig(name="i", use_offset=False, alpha=1e-8, solver="lbfgs", max_iter=1000, tol=1e-12)
    modelo = fit_glm(frame, config)
    assert modelo.feature_names == ("intercepto__intercepto",)  # <transformador>__<coluna>
    assert float(modelo.pipeline.named_steps["model"].coef_[0]) == pytest.approx(0.0, abs=1e-6)


def test_intercept_only_poisson_recovers_the_sample_mean_and_pearson_dispersion_one():
    frame = pd.DataFrame({BASELINE_COL: [1.0, 1.0], "target_3m": [1.0, 3.0]})
    config = GlmConfig(name="i", use_offset=False, alpha=1e-8, solver="lbfgs", max_iter=1000, tol=1e-12)
    modelo = fit_glm(frame, config)
    # MLE de Poisson só com intercepto: exp(b0) = média = 2.
    np.testing.assert_allclose(predict_total(modelo, frame), [2.0, 2.0], rtol=1e-6)
    # Dispersão de Pearson: soma((y - mu)^2 / mu) = (1 + 1) / 2 = 1, dividida por max(n - p, 1) = 1
    # (2 observações, 2 parâmetros: o piso de 1 grau de liberdade entra em ação).
    assert modelo.dispersao_pearson == pytest.approx(1.0, rel=1e-5)
    assert modelo.n_train == 2


@pytest.mark.parametrize(
    ("family", "power"),
    [("poisson", 1.0), ("tweedie", 1.5), ("tweedie", 1.9)],
)
def test_offset_intercept_matches_the_closed_form_for_each_power(family, power):
    # Com offset e, previsão = e * c. A equação de score do Tweedie com link log dá
    # c = soma(y * e^(1-p)) / soma(e^(2-p)). Para Poisson (p = 1): soma(y) / soma(e).
    e = np.array([1.0, 4.0, 9.0])
    y = np.array([2.0, 3.0, 20.0])
    frame = pd.DataFrame({BASELINE_COL: e, "target_3m": y})
    config = GlmConfig(
        name="t", family=family, power=power, alpha=0.0, use_offset=True, solver="lbfgs", max_iter=1000, tol=1e-12
    )
    modelo = fit_glm(frame, config)
    esperado = (y * e ** (1 - power)).sum() / (e ** (2 - power)).sum()
    assert float(np.exp(modelo.pipeline.named_steps["model"].intercept_)) == pytest.approx(esperado, rel=1e-5)
    np.testing.assert_allclose(predict_total(modelo, frame), e * esperado, rtol=1e-5)


def test_poisson_offset_closed_form_value():
    frame = pd.DataFrame({BASELINE_COL: [1.0, 4.0, 9.0], "target_3m": [2.0, 3.0, 20.0]})
    config = GlmConfig(name="p", alpha=0.0, use_offset=True, solver="lbfgs", max_iter=1000, tol=1e-12)
    modelo = fit_glm(frame, config)
    assert float(np.exp(modelo.pipeline.named_steps["model"].intercept_)) == pytest.approx(25.0 / 14.0, rel=1e-6)


def test_fit_glm_counts_baselines_below_the_floor_strictly():
    frame = pd.DataFrame({BASELINE_COL: [0.0, 0.01, 0.5, 1.0], "target_3m": [0.0, 1.0, 2.0, 3.0]})
    modelo = fit_glm(frame, FEATURE_STEPS["passo2_offset"])
    assert modelo.n_baseline_no_piso == 1  # só o 0,0; o valor exatamente igual ao piso não conta


def test_fit_glm_requires_the_baseline_only_when_using_offset():
    frame = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0], "target_3m": [1.0, 2.0, 2.0, 5.0]})
    sem_offset = GlmConfig(name="s", use_offset=False, numeric_features=("x",), alpha=0.0)
    assert fit_glm(frame, sem_offset).n_train == 4
    com_offset = GlmConfig(name="c", use_offset=True, numeric_features=("x",))
    with pytest.raises(ValueError, match="ausentes"):
        fit_glm(frame, com_offset)


def test_fit_glm_rejects_nulls_in_features_and_target():
    frame = pd.DataFrame({"x": [1.0, np.nan, 3.0, 4.0], "target_3m": [1.0, 2.0, 2.0, 5.0]})
    config = GlmConfig(name="s", use_offset=False, numeric_features=("x",))
    with pytest.raises(ValueError, match="x=1"):
        fit_glm(frame, config)
    frame_alvo = pd.DataFrame({"x": [1.0, 2.0, 3.0], "target_3m": [1.0, np.nan, 2.0]})
    with pytest.raises(ValueError, match="target_3m=1"):
        fit_glm(frame_alvo, config)


def test_fit_glm_reports_non_convergence_as_value_error():
    rng = np.random.default_rng(0)
    frame = pd.DataFrame({"x": rng.normal(size=200), "target_3m": rng.poisson(3.0, size=200).astype(float)})
    config = GlmConfig(
        name="lento", use_offset=False, numeric_features=("x",), solver="lbfgs", max_iter=1, tol=1e-14, alpha=0.0
    )
    with pytest.raises(ValueError, match="não convergiu"):
        fit_glm(frame, config)


def test_predict_total_rejects_frames_with_nulls_and_keeps_input_order():
    frame = _painel([dt.date(2024, 1, 1)], n_series=8)
    modelo = fit_glm(frame, FEATURE_STEPS["passo3_historico"])
    quebrado = frame.copy()
    quebrado.loc[0, "sum_3m"] = np.nan
    with pytest.raises(ValueError, match="sum_3m"):
        predict_total(modelo, quebrado)
    invertido = frame.iloc[::-1].reset_index(drop=True)
    np.testing.assert_allclose(predict_total(modelo, invertido), predict_total(modelo, frame)[::-1])


def test_prediction_scales_with_the_baseline_for_the_offset_model():
    frame = pd.DataFrame({BASELINE_COL: [1.0, 2.0, 4.0, 8.0], "target_3m": [1.0, 3.0, 3.0, 9.0]})
    modelo = fit_glm(frame, FEATURE_STEPS["passo2_offset"])
    dobro = frame.assign(**{BASELINE_COL: frame[BASELINE_COL] * 2})
    np.testing.assert_allclose(predict_total(modelo, dobro), 2 * predict_total(modelo, frame), rtol=1e-9)


def test_coefficient_table_is_sorted_by_absolute_value_with_multiplicative_effect():
    rng = np.random.default_rng(1)
    n = 5000
    frame = pd.DataFrame({"x1": rng.normal(size=n), "x2": rng.normal(size=n), BASELINE_COL: np.ones(n)})
    frame["target_3m"] = rng.poisson(np.exp(0.1 + 0.6 * frame["x1"] - 0.1 * frame["x2"])).astype(float)
    config = GlmConfig(name="c", alpha=0.0, scale=False, numeric_features=("x1", "x2"))
    tabela = coefficient_table(fit_glm(frame, config))
    assert list(tabela.columns) == ["feature", "coeficiente", "efeito_multiplicativo"]
    assert tabela["feature"].tolist() == ["num__x1", "num__x2"]  # |0,6| antes de |-0,1|
    assert abs(tabela.loc[0, "coeficiente"] - 0.6) < 0.05
    np.testing.assert_allclose(tabela["efeito_multiplicativo"], np.exp(tabela["coeficiente"]), atol=2e-4)
    assert tabela["coeficiente"].abs().is_monotonic_decreasing


# ── decompose_months ────────────────────────────────────────────────


def _mensal_frame(cutoff, pred):
    frame = _painel([cutoff], n_series=len(pred))
    frame["pred_total"] = pred
    return frame


def test_decompose_months_hand_computed_shares_and_year_rollover():
    frame = _mensal_frame(dt.date(2025, 11, 1), [9.0])
    mensal = decompose_months(frame, "pred_total")
    # Índices (1,0; 1,2; 0,8) somam 3,0: pesos 1/3, 0,4 e 4/15 aplicados a 9 unidades.
    assert mensal["mes_previsto"].tolist() == [dt.date(2025, 12, 1), dt.date(2026, 1, 1), dt.date(2026, 2, 1)]
    assert mensal["horizonte_mes"].tolist() == [1, 2, 3]
    np.testing.assert_allclose(mensal["share_sazonal"], [1 / 3, 0.4, 4 / 15])
    np.testing.assert_allclose(mensal["demanda_prevista"], [3.0, 3.6, 2.4])
    assert mensal["demanda_prevista"].sum() == pytest.approx(9.0)


def test_decompose_months_is_sorted_by_series_cutoff_and_horizon():
    a = _mensal_frame(dt.date(2025, 1, 1), [3.0, 6.0])
    b = _mensal_frame(dt.date(2025, 2, 1), [3.0, 6.0])
    mensal = decompose_months(pd.concat([b, a], ignore_index=True), "pred_total")
    chaves = list(zip(mensal["sk_product"], mensal["sk_location"], mensal["cutoff"], mensal["horizonte_mes"], strict=True))
    assert chaves == sorted(chaves)
    assert len(mensal) == 4 * 3


def test_decompose_months_rejects_nulls_and_supports_other_horizons():
    frame = _mensal_frame(dt.date(2025, 1, 1), [3.0, 6.0])
    ruim = frame.copy()
    ruim.loc[0, "pred_total"] = np.nan
    with pytest.raises(ValueError, match="pred_total"):
        decompose_months(ruim, "pred_total")
    curto = decompose_months(frame, "pred_total", horizon=2)
    assert set(curto["horizonte_mes"]) == {1, 2}
    # Com horizonte 2 o denominador continua sendo a soma dos 3 índices (3,0): os dois primeiros meses
    # ficam com (1,0 + 1,2) / 3,0 do total.
    assert curto.groupby("sk_product")["share_sazonal"].sum().tolist() == pytest.approx([(1.0 + 1.2) / 3.0] * 2)


def test_decompose_months_of_an_empty_frame_is_empty():
    frame = _mensal_frame(dt.date(2025, 1, 1), [3.0]).iloc[0:0]
    mensal = decompose_months(frame, "pred_total")
    assert mensal.empty
    assert {"mes_previsto", "horizonte_mes", "share_sazonal", "demanda_prevista"} <= set(mensal.columns)


# ── scorecard_by_cutoff / wins_by_cutoff ────────────────────────────


def _cutoff_frame():
    return pd.DataFrame(
        {
            "cutoff": [dt.date(2025, 1, 1)] * 2 + [dt.date(2025, 2, 1)] * 2,
            "category_name": ["A", "A", "A", "A"],
            "sk_location": [1, 1, 1, 1],
            "target_3m": [2.0, 3.0, 4.0, 6.0],
            "pred_glm": [4.0, 4.0, 6.0, 3.0],
            "pred_regua": [2.0, 3.0, 4.0, 6.0],
        }
    )


def test_scorecard_by_cutoff_hand_computed():
    tabela = scorecard_by_cutoff(_cutoff_frame(), {"glm": "pred_glm", "regua": "pred_regua"})
    assert list(tabela.columns) == ["cutoff", "regua", "n", "wape", "vies"]
    glm = tabela[tabela["regua"] == "glm"].set_index("cutoff")
    # Corte jan: categoria A x loja 1 soma real 5 e previsto 8 -> WAPE 3/5 = 0,6 e viés +0,6.
    assert glm.loc[dt.date(2025, 1, 1), "wape"] == 0.6
    assert glm.loc[dt.date(2025, 1, 1), "vies"] == 0.6
    # Corte fev: real 10, previsto 9 -> 0,1 e viés -0,1.
    assert glm.loc[dt.date(2025, 2, 1), "wape"] == 0.1
    assert glm.loc[dt.date(2025, 2, 1), "vies"] == -0.1
    assert (glm["n"] == 1).all()  # uma série agregada por corte
    regua = tabela[tabela["regua"] == "regua"]
    assert (regua["wape"] == 0.0).all()


def test_scorecard_by_cutoff_adds_relative_error_when_mm12_is_a_label():
    frame = _cutoff_frame().assign(pred_mm12=[3.0, 3.0, 4.0, 4.0])
    tabela = scorecard_by_cutoff(frame, {"MM12": "pred_mm12", "glm": "pred_glm"})
    assert "erro_relativo" in tabela.columns
    assert (tabela[tabela["regua"] == "MM12"]["erro_relativo"] == 1.0).all()


def test_wins_by_cutoff_counts_strictly_better_cutoffs():
    tabela = scorecard_by_cutoff(_cutoff_frame(), {"glm": "pred_glm", "regua": "pred_regua"})
    assert wins_by_cutoff(tabela, "regua", "glm") == 2  # a régua acerta tudo nos dois cortes
    assert wins_by_cutoff(tabela, "glm", "regua") == 0
    assert wins_by_cutoff(tabela, "glm", "glm") == 0  # empate não conta


def test_wins_by_cutoff_bias_compares_absolute_values():
    tabela = pd.DataFrame(
        {
            "cutoff": [dt.date(2025, 1, 1), dt.date(2025, 1, 1), dt.date(2025, 2, 1), dt.date(2025, 2, 1)],
            "regua": ["a", "b", "a", "b"],
            "vies": [-0.1, 0.3, 0.5, -0.2],
            "wape": [0.9, 0.1, 0.9, 0.1],
        }
    )
    assert wins_by_cutoff(tabela, "a", "b", metrica="vies") == 1  # jan: |-0,1| < |0,3|; fev: 0,5 > 0,2
    assert wins_by_cutoff(tabela, "a", "b") == 0  # WAPE: a é pior nos dois


def test_wins_by_cutoff_unknown_label_is_a_key_error():
    tabela = scorecard_by_cutoff(_cutoff_frame(), {"glm": "pred_glm"})
    with pytest.raises(KeyError):
        wins_by_cutoff(tabela, "glm", "inexistente")


# ── select_power ────────────────────────────────────────────────────


def _train_validation():
    treino = _painel([dt.date(2023, m, 1) for m in range(1, 7)], n_series=8, seed=11)
    validacao = _painel([dt.date(2024, 1, 1), dt.date(2024, 2, 1)], n_series=8, seed=12)
    return treino, validacao


def test_select_power_output_contract_and_ordering():
    treino, validacao = _train_validation()
    grade = select_power(
        treino, validacao, FEATURE_STEPS["passo2_offset"], powers=(1.0, 1.5), alphas=(0.0, 0.1)
    )
    assert list(grade.columns) == [
        "familia",
        "power",
        "alpha",
        "wape_produto",
        "wape_categoria_local",
        "wape_local",
        "mae_produto",
        "rmse_produto",
        "vies",
        "desvio_poisson",
        "dispersao_treino",
    ]
    assert len(grade) == 4
    assert grade["wape_categoria_local"].is_monotonic_increasing
    assert set(grade["familia"]) == {"poisson", "tweedie"}
    assert (grade.loc[grade["power"] == 1.0, "familia"] == "poisson").all()
    assert (grade.loc[grade["power"] == 1.5, "familia"] == "tweedie").all()
    assert set(zip(grade["power"], grade["alpha"], strict=True)) == {(1.0, 0.0), (1.0, 0.1), (1.5, 0.0), (1.5, 0.1)}


def test_select_power_scores_match_an_independent_calculation_on_validation():
    treino, validacao = _train_validation()
    config = replace(FEATURE_STEPS["passo2_offset"], name="ref", family="poisson", power=1.0, alpha=0.0)
    modelo = fit_glm(treino, config)
    previsto = predict_total(modelo, validacao)
    real = validacao["target_3m"].to_numpy()
    grade = select_power(treino, validacao, FEATURE_STEPS["passo2_offset"], powers=(1.0,), alphas=(0.0,))
    linha = grade.iloc[0]
    assert linha["wape_produto"] == round(float(np.abs(previsto - real).sum() / real.sum()), 4)
    assert linha["mae_produto"] == round(float(np.abs(previsto - real).mean()), 2)
    assert linha["rmse_produto"] == round(float(np.sqrt(((previsto - real) ** 2).mean())), 2)
    assert linha["vies"] == round(float((previsto.sum() - real.sum()) / real.sum()), 4)


def test_select_power_never_receives_the_test_split():
    assert "test" not in inspect.signature(select_power).parameters
    assert list(inspect.signature(select_power).parameters)[:3] == ["train", "validation", "base_config"]


def test_select_power_does_not_mutate_its_inputs():
    treino, validacao = _train_validation()
    antes_treino, antes_validacao = treino.copy(), validacao.copy()
    select_power(treino, validacao, FEATURE_STEPS["passo2_offset"], powers=(1.0,), alphas=(0.0,))
    pd.testing.assert_frame_equal(treino, antes_treino)
    pd.testing.assert_frame_equal(validacao, antes_validacao)


if __name__ == "__main__":
    unittest.main()
