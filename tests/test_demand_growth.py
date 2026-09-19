"""Testes do crescimento da demanda prevista por CD e PDV.

Todos offline, em pandas puro. O que está protegido aqui é a validação da
tabela mensal, a regra de vínculo PDV → CD, as fórmulas de crescimento (com
seus casos de borda) e a hipótese que torna o crescimento percentual
idêntico entre unidades quando a repartição mensal usa um índice único.
"""

import datetime as dt
import unittest

import numpy as np
import pandas as pd

from src.analytics_ai.demand_growth import (
    CD,
    PDV,
    concentracao,
    contribuicao_produtos,
    crescimento_vs_ano_anterior,
    enriquecer,
    evolucao_mensal,
    preparar_locais,
    trajetoria_por_unidade,
    validar_previsao_mensal,
)

CORTE = dt.date(2026, 8, 1)
MESES = (dt.date(2026, 9, 1), dt.date(2026, 10, 1), dt.date(2026, 11, 1))
SHARES = (0.2, 0.3, 0.5)


def _dim_locations() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"sk_location": "cd_a", "nk_location_id": 2, "location_name": "Armazem A", "location_type": "warehouse", "state": "PR", "region": "Sul"},
            {"sk_location": "cd_b", "nk_location_id": 4, "location_name": "Armazem B", "location_type": "warehouse", "state": "PI", "region": "Nordeste"},
            {"sk_location": "pdv_1", "nk_location_id": 1, "location_name": "Loja 1", "location_type": "store", "state": "PR", "region": "Sul"},
            {"sk_location": "pdv_2", "nk_location_id": 5, "location_name": "Loja 2", "location_type": "store", "state": "AL", "region": "Nordeste"},
            {"sk_location": "tec", "nk_location_id": -1, "location_name": "Nao informada", "location_type": "nao_informado", "state": None, "region": None},
        ]
    )


def _mensal(totais: dict[str, dict[str, float]], shares=SHARES) -> pd.DataFrame:
    """Tabela mensal sintética: `totais[local][produto]` é o total de 3 meses."""
    linhas = []
    for local, por_produto in totais.items():
        for produto, total in por_produto.items():
            for k, (mes, share) in enumerate(zip(MESES, shares), start=1):
                linhas.append(
                    {
                        "model_name": "glm_poisson",
                        "sk_product": produto,
                        "sku": f"SKU-{produto}",
                        "sk_location": local,
                        "location_name": local.upper(),
                        "cutoff": CORTE,
                        "mes_previsto": mes,
                        "horizonte_mes": k,
                        "demanda_prevista": total * share,
                        "demanda_prevista_3m": total,
                        "share_sazonal": share,
                    }
                )
    return pd.DataFrame(linhas)


TOTAIS = {
    "cd_a": {"p1": 100.0, "p2": 50.0, "p3": 10.0},
    "cd_b": {"p1": 80.0, "p2": 80.0, "p3": 0.0},
    "pdv_1": {"p1": 30.0, "p2": 20.0, "p3": 10.0},
    "pdv_2": {"p1": 90.0, "p2": 0.0, "p3": 0.0},
}


def _real(por_local_mes: dict[str, dict[dt.date, float]]) -> pd.DataFrame:
    linhas = []
    for local, por_mes in por_local_mes.items():
        for mes, valor in por_mes.items():
            for produto, peso in (("p1", 0.5), ("p2", 0.3), ("p3", 0.2)):
                linhas.append(
                    {"sk_product": produto, "sk_location": local, "month_start_date": mes, "demand_quantity": valor * peso}
                )
    return pd.DataFrame(linhas)


def _real_ano_anterior(totais_2025: dict[str, float]) -> pd.DataFrame:
    """Realizado de set–nov/2025 com o total dado, repartido 1/3 por mês."""
    return _real(
        {
            local: {dt.date(2025, m, 1): total / 3 for m in (9, 10, 11)}
            for local, total in totais_2025.items()
        }
    )


def _produtos() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sk_product": ["p1", "p2", "p3"],
            "product_name": ["Produto 1", "Produto 2", "Produto 3"],
            "category_name": ["Cat A", "Cat A", "Cat B"],
        }
    )


class ValidacaoTest(unittest.TestCase):
    """A tabela mensal só entra na análise se tiver exatamente a forma esperada."""

    def test_tabela_limpa_passa(self):
        validar_previsao_mensal(_mensal(TOTAIS))

    def test_nulo_e_negativo_falham(self):
        with_nan = _mensal(TOTAIS)
        with_nan.loc[0, "demanda_prevista"] = np.nan
        with self.assertRaisesRegex(ValueError, "nul"):
            validar_previsao_mensal(with_nan)
        negativo = _mensal(TOTAIS)
        negativo.loc[0, "demanda_prevista"] = -1.0
        with self.assertRaisesRegex(ValueError, "negativ"):
            validar_previsao_mensal(negativo)

    def test_duplicidade_falha(self):
        dup = pd.concat([_mensal(TOTAIS)] * 2, ignore_index=True)
        with self.assertRaisesRegex(ValueError, "duplic"):
            validar_previsao_mensal(dup)

    def test_mais_de_um_corte_falha(self):
        dois = _mensal(TOTAIS)
        dois.loc[dois.index[:3], "cutoff"] = dt.date(2026, 7, 1)
        with self.assertRaisesRegex(ValueError, "corte"):
            validar_previsao_mensal(dois)

    def test_serie_sem_os_tres_meses_falha(self):
        faltando = _mensal(TOTAIS).drop(index=[2])
        with self.assertRaisesRegex(ValueError, "horizonte"):
            validar_previsao_mensal(faltando)


class LocaisTest(unittest.TestCase):
    """CD = warehouse, PDV = store; o vínculo PDV → CD vem da geografia."""

    def test_membro_tecnico_sai_e_tipos_ganham_rotulo(self):
        locais = preparar_locais(_dim_locations())
        self.assertEqual(len(locais), 4)
        self.assertEqual(set(locais["location_type"]), {CD, PDV})
        self.assertEqual(locais.set_index("sk_location").loc["cd_a", "tipo"], "Centro de Distribuição")
        self.assertEqual(locais.set_index("sk_location").loc["pdv_1", "tipo"], "Ponto de Venda")

    def test_vinculo_prefere_mesma_uf_depois_regiao(self):
        locais = preparar_locais(_dim_locations()).set_index("sk_location")
        self.assertEqual(locais.loc["pdv_1", "cd_sk_location"], "cd_a")
        self.assertEqual(locais.loc["pdv_1", "criterio_vinculo"], "mesma UF")
        self.assertEqual(locais.loc["pdv_2", "cd_sk_location"], "cd_b")
        self.assertEqual(locais.loc["pdv_2", "criterio_vinculo"], "mesma região")
        self.assertEqual(locais.loc["pdv_2", "cd_associado"], "Armazem B")

    def test_pdv_sem_cd_fica_marcado(self):
        dim = _dim_locations()
        dim.loc[dim["sk_location"] == "pdv_2", ["state", "region"]] = ["AM", "Norte"]
        locais = preparar_locais(dim).set_index("sk_location")
        self.assertTrue(pd.isna(locais.loc["pdv_2", "cd_sk_location"]))
        self.assertEqual(locais.loc["pdv_2", "criterio_vinculo"], "sem CD")

    def test_cd_nao_recebe_vinculo(self):
        locais = preparar_locais(_dim_locations()).set_index("sk_location")
        self.assertTrue(pd.isna(locais.loc["cd_a", "cd_sk_location"]))
        self.assertFalse(locais.loc["cd_a", "ambiguo"])

    def test_ambiguidade_escolhe_menor_nk_e_marca(self):
        dim = _dim_locations()
        extra = {"sk_location": "cd_c", "nk_location_id": 3, "location_name": "Armazem C", "location_type": "warehouse", "state": "PR", "region": "Sul"}
        dim = pd.concat([dim, pd.DataFrame([extra])], ignore_index=True)
        locais = preparar_locais(dim).set_index("sk_location")
        self.assertEqual(locais.loc["pdv_1", "cd_sk_location"], "cd_a")
        self.assertTrue(locais.loc["pdv_1", "ambiguo"])

    def test_enriquecer_exige_todo_local_conhecido(self):
        mensal = _mensal(TOTAIS)
        locais = preparar_locais(_dim_locations())
        enriquecido = enriquecer(mensal, locais)
        self.assertEqual(len(enriquecido), len(mensal))
        self.assertIn("cd_associado", enriquecido.columns)
        with self.assertRaisesRegex(ValueError, "cd_a"):
            enriquecer(mensal, locais[locais["sk_location"] != "cd_a"])


class TrajetoriaTest(unittest.TestCase):
    """Crescimento mês a mês dentro do horizonte, por unidade."""

    def setUp(self):
        self.enriquecido = enriquecer(_mensal(TOTAIS), preparar_locais(_dim_locations()))

    def test_somas_e_variacoes(self):
        cds = trajetoria_por_unidade(self.enriquecido, CD).set_index("sk_location")
        # cd_a: total 160 → meses 32, 48, 80
        self.assertAlmostEqual(cds.loc["cd_a", "mes_1"], 32.0)
        self.assertAlmostEqual(cds.loc["cd_a", "mes_2"], 48.0)
        self.assertAlmostEqual(cds.loc["cd_a", "mes_3"], 80.0)
        self.assertAlmostEqual(cds.loc["cd_a", "var_abs_1_2"], 16.0)
        self.assertAlmostEqual(cds.loc["cd_a", "var_pct_1_2"], 50.0)
        self.assertAlmostEqual(cds.loc["cd_a", "var_abs_2_3"], 32.0)
        self.assertAlmostEqual(cds.loc["cd_a", "cresc_abs_1_3"], 48.0)
        self.assertAlmostEqual(cds.loc["cd_a", "cresc_pct_1_3"], 150.0)

    def test_ranking_absoluto_ordena_e_desempata(self):
        cds = trajetoria_por_unidade(self.enriquecido, CD)
        self.assertEqual(list(cds["sk_location"]), ["cd_a", "cd_b"])
        self.assertEqual(list(cds["rank_abs"]), [1, 2])
        # cd_b tem os mesmos 160 de total: empate exato → desempata pelo nome.
        empate = enriquecer(
            _mensal({"cd_a": {"p1": 160.0}, "cd_b": {"p1": 160.0}}), preparar_locais(_dim_locations())
        )
        self.assertEqual(list(trajetoria_por_unidade(empate, CD)["sk_location"]), ["cd_a", "cd_b"])

    def test_share_unico_torna_o_percentual_igual_em_todas_as_unidades(self):
        # Esta é a propriedade que faz o ranking absoluto virar ranking de volume
        # na previsão real: o índice sazonal é o mesmo para todas as séries.
        tudo = pd.concat(
            [trajetoria_por_unidade(self.enriquecido, CD), trajetoria_por_unidade(self.enriquecido, PDV)]
        )
        esperado = (SHARES[2] / SHARES[0] - 1) * 100
        np.testing.assert_allclose(tudo["cresc_pct_1_3"], esperado)
        np.testing.assert_allclose(tudo["cresc_abs_1_3"], tudo[["mes_1", "mes_2", "mes_3"]].sum(axis=1) * (SHARES[2] - SHARES[0]))

    def test_base_zero_da_percentual_nulo_e_vai_para_o_fim(self):
        enriquecido = enriquecer(
            _mensal({"cd_a": {"p1": 0.0}, "cd_b": {"p1": 10.0}}), preparar_locais(_dim_locations())
        )
        cds = trajetoria_por_unidade(enriquecido, CD).set_index("sk_location")
        self.assertTrue(cds.loc["cd_a", "base_zero"])
        self.assertTrue(np.isnan(cds.loc["cd_a", "cresc_pct_1_3"]))
        self.assertEqual(cds.loc["cd_b", "rank_pct"], 1)
        self.assertEqual(cds.loc["cd_a", "rank_pct"], 2)

    def test_pdv_carrega_o_cd_associado(self):
        pdvs = trajetoria_por_unidade(self.enriquecido, PDV).set_index("sk_location")
        self.assertEqual(pdvs.loc["pdv_1", "cd_associado"], "Armazem A")
        self.assertEqual(pdvs.loc["pdv_2", "criterio_vinculo"], "mesma região")

    def test_tipo_desconhecido_falha(self):
        with self.assertRaises(ValueError):
            trajetoria_por_unidade(self.enriquecido, "loja")


class AnoAnteriorTest(unittest.TestCase):
    """Trimestre previsto contra o mesmo trimestre realizado um ano antes."""

    def setUp(self):
        self.enriquecido = enriquecer(_mensal(TOTAIS), preparar_locais(_dim_locations()))

    def test_alinha_os_meses_doze_atras(self):
        real = _real_ano_anterior({"cd_a": 100.0, "cd_b": 200.0, "pdv_1": 60.0, "pdv_2": 45.0})
        cds = crescimento_vs_ano_anterior(self.enriquecido, real, CD).set_index("sk_location")
        self.assertAlmostEqual(cds.loc["cd_a", "realizado_ano_anterior"], 100.0)
        self.assertAlmostEqual(cds.loc["cd_a", "previsto"], 160.0)
        self.assertAlmostEqual(cds.loc["cd_a", "cresc_abs"], 60.0)
        self.assertAlmostEqual(cds.loc["cd_a", "cresc_pct"], 60.0)
        self.assertAlmostEqual(cds.loc["cd_b", "cresc_abs"], -40.0)
        self.assertEqual(list(cds.sort_values("rank_abs").index), ["cd_a", "cd_b"])
        self.assertTrue(cds.loc["cd_b", "queda"])

    def test_meses_fora_da_referencia_sao_ignorados(self):
        real = _real_ano_anterior({"cd_a": 100.0, "cd_b": 100.0, "pdv_1": 1.0, "pdv_2": 1.0})
        ruido = _real({"cd_a": {dt.date(2025, 8, 1): 999.0, dt.date(2026, 8, 1): 999.0}})
        cds = crescimento_vs_ano_anterior(self.enriquecido, pd.concat([real, ruido]), CD).set_index("sk_location")
        self.assertAlmostEqual(cds.loc["cd_a", "realizado_ano_anterior"], 100.0)

    def test_referencia_incompleta_da_nulo(self):
        real = _real_ano_anterior({"cd_a": 100.0, "cd_b": 100.0, "pdv_1": 1.0, "pdv_2": 1.0})
        real = real[~((real["sk_location"] == "cd_b") & (real["month_start_date"] == dt.date(2025, 10, 1)))]
        cds = crescimento_vs_ano_anterior(self.enriquecido, real, CD).set_index("sk_location")
        self.assertTrue(cds.loc["cd_b", "referencia_incompleta"])
        self.assertTrue(np.isnan(cds.loc["cd_b", "cresc_pct"]))
        self.assertFalse(cds.loc["cd_a", "referencia_incompleta"])


class ContribuicaoTest(unittest.TestCase):
    """Os produtos explicam o crescimento da unidade, e as contribuições fecham."""

    def setUp(self):
        self.enriquecido = enriquecer(_mensal(TOTAIS), preparar_locais(_dim_locations()))
        self.real = _real_ano_anterior({"cd_a": 100.0, "cd_b": 200.0, "pdv_1": 60.0, "pdv_2": 45.0})

    def test_contribuicoes_fecham_com_a_unidade(self):
        contrib = contribuicao_produtos(self.enriquecido, self.real, _produtos(), "cd_a")
        cds = trajetoria_por_unidade(self.enriquecido, CD).set_index("sk_location")
        aa = crescimento_vs_ano_anterior(self.enriquecido, self.real, CD).set_index("sk_location")
        self.assertAlmostEqual(contrib["cresc_abs_1_3"].sum(), cds.loc["cd_a", "cresc_abs_1_3"])
        self.assertAlmostEqual(contrib["cresc_ano_anterior_abs"].sum(), aa.loc["cd_a", "cresc_abs"])
        self.assertEqual(list(contrib.columns[:3]), ["sk_product", "sku", "product_name"])

    def test_ordena_pela_contribuicao_ano_anterior(self):
        contrib = contribuicao_produtos(self.enriquecido, self.real, _produtos(), "cd_a")
        # p1: previsto 100, realizado 50 → +50; p2: 50 − 30 = +20; p3: 10 − 20 = −10
        self.assertEqual(list(contrib["sk_product"]), ["p1", "p2", "p3"])
        self.assertAlmostEqual(contrib.iloc[0]["cresc_ano_anterior_abs"], 50.0)
        self.assertAlmostEqual(contrib.iloc[2]["cresc_ano_anterior_abs"], -10.0)

    def test_produto_sem_realizado_conta_como_zero(self):
        real = self.real[self.real["sk_product"] != "p3"]
        contrib = contribuicao_produtos(self.enriquecido, real, _produtos(), "cd_a").set_index("sk_product")
        self.assertAlmostEqual(contrib.loc["p3", "realizado_ano_anterior"], 0.0)
        self.assertAlmostEqual(contrib.loc["p3", "cresc_ano_anterior_abs"], 10.0)

    def test_concentracao(self):
        resumo = concentracao(pd.Series([50.0, 20.0, -10.0]), top_n=2)
        self.assertAlmostEqual(resumo["total"], 60.0)
        self.assertAlmostEqual(resumo["share_top_n"], 70.0 / 60.0)
        self.assertEqual(resumo["n_para_metade"], 1)
        vazio = concentracao(pd.Series([-1.0, -2.0]), top_n=2)
        self.assertTrue(np.isnan(vazio["share_top_n"]))


class EvolucaoTest(unittest.TestCase):
    def test_junta_realizado_e_previsto_por_unidade(self):
        enriquecido = enriquecer(_mensal(TOTAIS), preparar_locais(_dim_locations()))
        real = _real({"cd_a": {dt.date(2026, 7, 1): 10.0, dt.date(2026, 8, 1): 20.0, dt.date(2025, 1, 1): 5.0}})
        evolucao = evolucao_mensal(enriquecido, real, CD, desde=dt.date(2026, 7, 1))
        cd_a = evolucao[evolucao["sk_location"] == "cd_a"].sort_values("mes")
        self.assertEqual(list(cd_a["origem"]), ["realizado", "realizado", "previsto", "previsto", "previsto"])
        self.assertAlmostEqual(cd_a.iloc[0]["valor"], 10.0)
        self.assertAlmostEqual(cd_a.iloc[2]["valor"], 32.0)
        self.assertNotIn(dt.date(2025, 1, 1), set(cd_a["mes"]))


if __name__ == "__main__":
    unittest.main()
