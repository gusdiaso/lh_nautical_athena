"""Testes do GLM de previsão de demanda.

Todos offline: nenhum teste aqui abre sessão Spark nem lê tabela do
Databricks. O que é exercitado é a matemática do offset, a integridade do
split temporal, a decomposição mensal e os contratos de métrica.
"""

import datetime as dt
import unittest
import unittest.mock

import numpy as np
import pandas as pd

from src.analytics_ai.demand_baselines import comparison_scorecard, root_mean_squared_error
from src.analytics_ai.demand_glm import (
    BASELINE_COL,
    EXCLUDED_FROM_TRAINING,
    FEATURE_STEPS,
    GlmConfig,
    add_predictions,
    check_no_nulls,
    decompose_months,
    prepare_features,
    fit_glm,
    offset_weights,
    predict_total,
    split_panel,
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
            "erro_produto",
            "erro_categoria_local",
            "erro_local",
            "vies",
            "erro_medio_unidades",
            "desvio_poisson",
        ):
            self.assertIn(coluna, placar.columns)
        self.assertIn("raiz_erro_quadratico", placar.columns)
        self.assertAlmostEqual(4.0 / 12.0, float(placar.loc["teste", "erro_produto"]), places=4)
        self.assertAlmostEqual(1.0, float(placar.loc["teste", "erro_medio_unidades"]))
        self.assertAlmostEqual(1.0, float(placar.loc["teste", "raiz_erro_quadratico"]))

    def test_wape_soma_absoluta_sobre_soma_real(self):
        placar = comparison_scorecard(self.frame, {"teste": "pred"})
        esperado = (self.frame["pred"] - self.frame["target_3m"]).abs().sum() / self.frame[
            "target_3m"
        ].sum()
        self.assertAlmostEqual(esperado, float(placar.loc["teste", "erro_produto"]), places=4)


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


if __name__ == "__main__":
    unittest.main()
