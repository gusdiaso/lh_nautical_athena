"""Testes da recomendação de expansão da rede.

Todos offline, em pandas puro. O que está protegido aqui é a geometria (haversine
e o ganho de um ponto novo, que nunca pode ser negativo), a disciplina com dados
incompletos (crescimento sem base, unidade sem coordenada, canal de balcão fora
da distância) e a regra que separa loja de armazém.
"""

import datetime as dt
import unittest

import numpy as np
import pandas as pd

from src.analytics_ai.network_expansion import (
    CD,
    PDV,
    classificar_tipo,
    crescimento_yoy_por_uf,
    demanda_por_uf,
    frequencia_no_topo,
    distancia_atendimento_atual,
    distancia_real_de_atendimento,
    distancia_uf_local,
    ganho_por_candidato,
    haversine_km,
    matriz_uf_uf,
    participacao_unidade_mais_proxima,
    preparar_vendas,
    ranquear_candidatos,
    selecao_gulosa,
    separar_canal_entrega,
    sinalizar_baixa_confianca,
    validar_vendas_uf,
)

# Capitais reais: SP, RJ e Curitiba dão distâncias conhecidas.
UFS = pd.DataFrame(
    [
        {"state": "SP", "latitude": -23.5505, "longitude": -46.6333},
        {"state": "RJ", "latitude": -22.9068, "longitude": -43.1729},
        {"state": "PR", "latitude": -25.4284, "longitude": -49.2733},
        {"state": "AM", "latitude": -3.1190, "longitude": -60.0217},
        {"state": "PA", "latitude": -1.4558, "longitude": -48.4902},
    ]
)


def _locais(*linhas) -> pd.DataFrame:
    """Cada linha: (sk, tipo, uf, ativo)."""
    ufs = UFS.set_index("state")
    return pd.DataFrame(
        [
            {
                "sk_location": sk,
                "location_name": sk,
                "location_type": tipo,
                "state": uf,
                "is_active": ativo,
                "latitude": ufs.loc[uf, "latitude"],
                "longitude": ufs.loc[uf, "longitude"],
            }
            for sk, tipo, uf, ativo in linhas
        ]
    )


def _vendas(**substituicoes) -> pd.DataFrame:
    base = {
        "month_start_date": [dt.date(2026, 1, 1)] * 3,
        "customer_state": ["SP", "RJ", "AM"],
        "sk_location": ["cd_sp", "cd_sp", "cd_sp"],
        "channel": ["ecommerce", "ecommerce", "ecommerce"],
        "quantity_ordered": [100.0, 50.0, 10.0],
        "net_revenue": [1000.0, 500.0, 100.0],
        "estimated_gross_profit": [300.0, 150.0, 30.0],
        "order_item_count": [40, 20, 5],
    }
    base.update(substituicoes)
    return pd.DataFrame(base)


class HaversineTest(unittest.TestCase):
    def test_mesmo_ponto_tem_distancia_zero(self):
        self.assertAlmostEqual(float(haversine_km(-23.55, -46.63, -23.55, -46.63)), 0.0, places=6)

    def test_e_simetrica(self):
        ida = float(haversine_km(-23.5505, -46.6333, -22.9068, -43.1729))
        volta = float(haversine_km(-22.9068, -43.1729, -23.5505, -46.6333))
        self.assertAlmostEqual(ida, volta, places=6)

    def test_sao_paulo_rio_fica_perto_de_360_km(self):
        self.assertAlmostEqual(float(haversine_km(-23.5505, -46.6333, -22.9068, -43.1729)), 360.0, delta=10.0)


class ValidarVendasTest(unittest.TestCase):
    def test_tabela_limpa_passa(self):
        validar_vendas_uf(_vendas())

    def test_coluna_ausente_falha(self):
        with self.assertRaisesRegex(ValueError, "colunas ausentes"):
            validar_vendas_uf(_vendas().drop(columns="net_revenue"))

    def test_quantidade_negativa_falha(self):
        with self.assertRaisesRegex(ValueError, "negativos"):
            validar_vendas_uf(_vendas(quantity_ordered=[-1.0, 50.0, 10.0]))

    def test_nulo_em_medida_falha(self):
        with self.assertRaisesRegex(ValueError, "nulos"):
            validar_vendas_uf(_vendas(net_revenue=[1000.0, None, 100.0]))

    def test_grao_duplicado_falha(self):
        with self.assertRaisesRegex(ValueError, "duplicadas"):
            validar_vendas_uf(_vendas(customer_state=["SP", "SP", "AM"]))


class CanalTest(unittest.TestCase):
    def test_reconhece_variacoes_de_caixa_acento_e_pontuacao(self):
        vendas = _vendas(channel=["E-commerce ", "ecommerce", "Loja física"])
        self.assertEqual(len(separar_canal_entrega(vendas)), 2)

    def test_balcao_fica_de_fora(self):
        vendas = _vendas(channel=["loja", "loja", "loja"])
        self.assertTrue(separar_canal_entrega(vendas).empty)


class DistanciaTest(unittest.TestCase):
    def setUp(self):
        self.locais = _locais(("cd_sp", CD, "SP", True), ("loja_rj", PDV, "RJ", True), ("cd_am_off", CD, "AM", False))
        self.dist = distancia_uf_local(UFS, self.locais)

    def test_linhas_sao_ufs_vezes_unidades_ativas(self):
        self.assertEqual(len(self.dist), len(UFS) * 2)

    def test_unidade_inativa_nao_entra_no_minimo(self):
        atual = distancia_atendimento_atual(self.dist)
        self.assertGreater(atual["AM"], 2000.0)  # sem CD ativo em AM, o mais perto está a milhares de km

    def test_unidade_na_propria_uf_tem_distancia_zero(self):
        self.assertAlmostEqual(distancia_atendimento_atual(self.dist)["SP"], 0.0, places=6)

    def test_tipo_sem_unidade_devolve_nan_e_nao_zero(self):
        so_lojas = distancia_uf_local(UFS, _locais(("loja_rj", PDV, "RJ", True)))
        self.assertTrue(distancia_atendimento_atual(so_lojas, CD).isna().all())

    def test_unidade_ativa_sem_coordenada_falha_em_vez_de_sumir(self):
        locais = self.locais.copy()
        locais.loc[0, "latitude"] = np.nan
        with self.assertRaisesRegex(ValueError, "sem coordenada"):
            distancia_uf_local(UFS, locais)

    def test_distancia_real_pondera_por_unidades_e_reporta_o_descarte(self):
        vendas = _vendas(customer_state=["SP", "RJ", "SEM_UF"])
        tabela, descartado = distancia_real_de_atendimento(vendas, self.dist)
        self.assertAlmostEqual(descartado, 10.0 / 160.0)
        rj = tabela.set_index("state").loc["RJ"]
        self.assertAlmostEqual(rj["distancia_media_km"], self.dist.query("state == 'RJ' and sk_location == 'cd_sp'")["distancia_km"].iloc[0])


class ProximaTest(unittest.TestCase):
    def setUp(self):
        locais = _locais(("cd_sp", CD, "SP", True), ("cd_pa", CD, "PA", True))
        self.dist = distancia_uf_local(UFS, locais)

    def test_conta_so_o_que_saiu_da_unidade_mais_proxima(self):
        # SP e AM: a mais próxima de SP é cd_sp; a de AM é cd_pa. Só a venda de SP (100) acerta.
        vendas = _vendas(customer_state=["SP", "AM", "AM"], sk_location=["cd_sp", "cd_sp", "cd_sp"], quantity_ordered=[100.0, 50.0, 10.0])
        vendas["month_start_date"] = [dt.date(2026, 1, 1), dt.date(2026, 1, 1), dt.date(2026, 2, 1)]
        self.assertAlmostEqual(participacao_unidade_mais_proxima(vendas, self.dist), 100.0 / 160.0)

    def test_tudo_certo_da_um(self):
        vendas = _vendas(customer_state=["SP", "PA", "AM"], sk_location=["cd_sp", "cd_pa", "cd_pa"])
        self.assertAlmostEqual(participacao_unidade_mais_proxima(vendas, self.dist), 1.0)


class GanhoTest(unittest.TestCase):
    def setUp(self):
        self.uf_uf = matriz_uf_uf(UFS)
        self.locais = _locais(("cd_sp", CD, "SP", True))
        self.atual = distancia_atendimento_atual(distancia_uf_local(UFS, self.locais))
        self.demanda = pd.Series({"SP": 100.0, "RJ": 50.0, "PR": 30.0, "AM": 10.0, "PA": 40.0})

    def test_ganho_nunca_e_negativo(self):
        ganho = ganho_por_candidato(self.demanda, self.atual, self.uf_uf)
        self.assertTrue((ganho["ganho_unidade_km"] >= 0).all())

    def test_uf_que_ja_tem_unidade_ganha_zero(self):
        ganho = ganho_por_candidato(self.demanda, self.atual, self.uf_uf)
        self.assertAlmostEqual(ganho.loc["SP", "ganho_unidade_km"], 0.0, places=6)

    def test_candidata_no_norte_beneficia_o_norte_todo(self):
        ganho = ganho_por_candidato(self.demanda, self.atual, self.uf_uf)
        self.assertGreater(ganho.loc["PA", "ganho_unidade_km"], ganho.loc["RJ", "ganho_unidade_km"])
        self.assertGreaterEqual(ganho.loc["PA", "n_ufs_beneficiadas"], 2)  # PA e AM

    def test_ganho_bate_com_a_conta_a_mao(self):
        ganho = ganho_por_candidato(self.demanda, self.atual, self.uf_uf)
        d = self.uf_uf
        esperado = sum(
            self.demanda[v] * max(0.0, self.atual[v] - d.loc[v, "PA"]) for v in UFS["state"]
        )
        self.assertAlmostEqual(ganho.loc["PA", "ganho_unidade_km"], esperado, places=4)

    def test_ganho_propria_uf_e_fracao_entre_zero_e_um(self):
        ganho = ganho_por_candidato(self.demanda, self.atual, self.uf_uf)
        fracoes = ganho["ganho_propria_uf"].dropna()
        self.assertTrue(((fracoes >= 0) & (fracoes <= 1.0 + 1e-9)).all())

    def test_distancia_atual_ausente_falha(self):
        with self.assertRaisesRegex(ValueError, "distância atual ausente"):
            ganho_por_candidato(self.demanda, self.atual.drop("AM"), self.uf_uf)


class CrescimentoTest(unittest.TestCase):
    def _serie(self, primeiro_mes: dt.date, n_meses: int, por_mes: float) -> pd.DataFrame:
        meses = [dt.date(primeiro_mes.year + (primeiro_mes.month - 1 + i) // 12, (primeiro_mes.month - 1 + i) % 12 + 1, 1) for i in range(n_meses)]
        return pd.DataFrame(
            {
                "month_start_date": meses,
                "customer_state": "SP",
                "sk_location": "cd_sp",
                "channel": "ecommerce",
                "quantity_ordered": por_mes,
                "net_revenue": por_mes * 10,
                "estimated_gross_profit": por_mes * 3,
                "order_item_count": 5,
            }
        )

    def test_crescimento_com_24_meses(self):
        vendas = pd.concat([self._serie(dt.date(2024, 1, 1), 12, 10.0), self._serie(dt.date(2025, 1, 1), 12, 15.0)])
        tabela = crescimento_yoy_por_uf(vendas, dt.date(2025, 12, 1))
        self.assertAlmostEqual(tabela.loc["SP", "crescimento_pct"], 50.0)
        self.assertFalse(tabela.loc["SP", "referencia_incompleta"])

    def test_historico_incompleto_vira_nan_e_nao_numero_inflado(self):
        vendas = self._serie(dt.date(2025, 1, 1), 12, 15.0)
        tabela = crescimento_yoy_por_uf(vendas, dt.date(2025, 12, 1))
        self.assertTrue(tabela.loc["SP", "referencia_incompleta"])
        self.assertTrue(np.isnan(tabela.loc["SP", "crescimento_pct"]))

    def test_uf_sem_venda_na_referencia_e_nan(self):
        vendas = pd.concat([self._serie(dt.date(2024, 1, 1), 12, 10.0), self._serie(dt.date(2025, 1, 1), 12, 15.0)])
        novo = self._serie(dt.date(2025, 1, 1), 12, 5.0).assign(customer_state="RJ")
        tabela = crescimento_yoy_por_uf(pd.concat([vendas, novo]), dt.date(2025, 12, 1))
        self.assertTrue(np.isnan(tabela.loc["RJ", "crescimento_pct"]))

    def test_demanda_por_uf_exclui_sem_uf_e_respeita_a_janela(self):
        vendas = pd.concat([self._serie(dt.date(2025, 1, 1), 12, 10.0), self._serie(dt.date(2025, 1, 1), 12, 99.0).assign(customer_state="SEM_UF")])
        tabela = demanda_por_uf(vendas, dt.date(2025, 1, 1), dt.date(2025, 6, 1))
        self.assertEqual(list(tabela.index), ["SP"])
        self.assertAlmostEqual(tabela.loc["SP", "unidades"], 60.0)


class TipoTest(unittest.TestCase):
    def _ganho(self, propria: float, total: float = 100.0, n: int = 3) -> pd.DataFrame:
        return pd.DataFrame(
            {"ganho_unidade_km": [total], "ganho_propria_uf": [propria], "n_ufs_beneficiadas": [n]}, index=pd.Index(["XX"], name="state")
        )

    def test_ganho_espalhado_e_armazem(self):
        tipo = classificar_tipo(self._ganho(0.3), pd.Series({"XX": 2000.0}))
        self.assertEqual(tipo.loc["XX", "tipo_recomendado"], CD)

    def test_ganho_concentrado_com_armazem_perto_e_loja(self):
        tipo = classificar_tipo(self._ganho(0.9), pd.Series({"XX": 100.0}))
        self.assertEqual(tipo.loc["XX", "tipo_recomendado"], PDV)

    def test_ganho_concentrado_e_longe_de_armazem_e_ambiguo(self):
        tipo = classificar_tipo(self._ganho(0.9), pd.Series({"XX": 2000.0}))
        self.assertEqual(tipo.loc["XX", "tipo_recomendado"], "ambiguo")

    def test_sem_ganho(self):
        tipo = classificar_tipo(self._ganho(np.nan, total=0.0, n=0), pd.Series({"XX": 10.0}))
        self.assertEqual(tipo.loc["XX", "tipo_recomendado"], "sem_ganho")
        self.assertTrue(tipo.loc["XX", "motivo"])


class RankingTest(unittest.TestCase):
    def setUp(self):
        self.locais = _locais(("cd_sp", CD, "SP", True))
        self.demanda = pd.DataFrame(
            {
                "unidades": [100.0, 50.0, 30.0, 10.0, 40.0],
                "receita": [1000.0, 500.0, 300.0, 100.0, 400.0],
                "lucro_estimado": [1.0] * 5,
                "linhas": [100, 50, 30, 5, 40],
            },
            index=pd.Index(["SP", "RJ", "PR", "AM", "PA"], name="state"),
        )
        self.crescimento = pd.Series({"SP": 5.0, "RJ": 10.0, "PR": -2.0, "AM": np.nan, "PA": 40.0})

    def test_uma_linha_por_uf_com_ranks_de_1_a_n(self):
        tabela = ranquear_candidatos(self.demanda, self.crescimento, UFS, self.locais)
        self.assertEqual(len(tabela), 5)
        self.assertEqual(sorted(tabela["rank_ganho"]), [1, 2, 3, 4, 5])
        self.assertEqual(sorted(tabela["rank_score"]), [1, 2, 3, 4, 5])

    def test_uf_com_unidade_fica_sem_ganho(self):
        tabela = ranquear_candidatos(self.demanda, self.crescimento, UFS, self.locais)
        self.assertEqual(tabela.loc["SP", "tipo_recomendado"], "sem_ganho")
        self.assertTrue(tabela.loc["SP", "ja_tem_unidade"])

    def test_crescimento_indisponivel_e_baixa_confianca_sao_sinalizados(self):
        tabela = ranquear_candidatos(self.demanda, self.crescimento, UFS, self.locais)
        self.assertTrue(tabela.loc["AM", "crescimento_indisponivel"])
        self.assertTrue(tabela.loc["AM", "baixa_confianca"])
        self.assertFalse(tabela.loc["SP", "baixa_confianca"])

    def test_pesos_precisam_somar_um(self):
        with self.assertRaisesRegex(ValueError, "somar 1"):
            ranquear_candidatos(self.demanda, self.crescimento, UFS, self.locais, pesos={"unidades": 1, "receita": 1, "distancia": 1, "crescimento": 1})

    def test_peso_do_crescimento_pode_inverter_o_score(self):
        so_crescimento = {"unidades": 0.0, "receita": 0.0, "distancia": 0.0, "crescimento": 1.0}
        tabela = ranquear_candidatos(self.demanda, self.crescimento, UFS, self.locais, pesos=so_crescimento)
        self.assertEqual(tabela["rank_score"].idxmin(), "PA")

    def test_empate_se_resolve_pelo_nome_da_uf(self):
        demanda = self.demanda.assign(unidades=10.0, receita=100.0, linhas=100)
        crescimento = pd.Series({e: 1.0 for e in demanda.index})
        so_volume = {"unidades": 1.0, "receita": 0.0, "distancia": 0.0, "crescimento": 0.0}
        tabela = ranquear_candidatos(demanda, crescimento, UFS, self.locais, pesos=so_volume)
        self.assertEqual(list(tabela.sort_values("rank_score").index), sorted(tabela.index))

    def test_baixa_confianca_isolada(self):
        sinal = sinalizar_baixa_confianca(pd.Series({"A": 5, "B": 500}), limite=30)
        self.assertEqual(sinal.to_dict(), {"A": True, "B": False})


class PrepararTest(unittest.TestCase):
    def test_decimal_vira_float_e_mes_vira_date(self):
        from decimal import Decimal

        vendas = _vendas(quantity_ordered=[Decimal("100"), Decimal("50"), Decimal("10")])
        vendas["month_start_date"] = pd.to_datetime(vendas["month_start_date"])
        saida = preparar_vendas(vendas)
        self.assertEqual(saida["quantity_ordered"].dtype, float)
        self.assertIsInstance(saida["month_start_date"].iloc[0], dt.date)


class GulosaTest(unittest.TestCase):
    def setUp(self):
        self.uf_uf = matriz_uf_uf(UFS)
        locais = _locais(("cd_sp", CD, "SP", True))
        self.atual = distancia_atendimento_atual(distancia_uf_local(UFS, locais))
        self.demanda = pd.Series({"SP": 100.0, "RJ": 50.0, "PR": 30.0, "AM": 10.0, "PA": 40.0})

    def test_primeiro_passo_e_o_maior_ganho_simples(self):
        passos = selecao_gulosa(self.demanda, self.atual, self.uf_uf, n_pontos=2)
        ganho = ganho_por_candidato(self.demanda, self.atual, self.uf_uf)["ganho_unidade_km"]
        self.assertEqual(passos["state"].iloc[0], ganho.idxmax())

    def test_distancia_media_cai_e_o_ganho_marginal_nao_cresce(self):
        passos = selecao_gulosa(self.demanda, self.atual, self.uf_uf, n_pontos=3)
        self.assertTrue(passos["distancia_media_apos_km"].is_monotonic_decreasing)
        self.assertTrue(passos["ganho_unidade_km"].is_monotonic_decreasing)

    def test_nao_repete_uf(self):
        passos = selecao_gulosa(self.demanda, self.atual, self.uf_uf, n_pontos=3)
        self.assertEqual(passos["state"].nunique(), 3)


class FrequenciaTest(unittest.TestCase):
    def setUp(self):
        locais = _locais(("cd_sp", CD, "SP", True))
        demanda = pd.DataFrame(
            {"unidades": [100.0, 50.0, 30.0, 10.0, 40.0], "receita": [1000.0, 500.0, 300.0, 100.0, 400.0], "lucro_estimado": [1.0] * 5, "linhas": [100] * 5},
            index=pd.Index(["SP", "RJ", "PR", "AM", "PA"], name="state"),
        )
        crescimento = pd.Series({"SP": 5.0, "RJ": 10.0, "PR": -2.0, "AM": 8.0, "PA": 40.0})
        self.ranking = ranquear_candidatos(demanda, crescimento, UFS, locais)

    def test_frequencias_ficam_entre_zero_e_um_e_somam_top(self):
        freq = frequencia_no_topo(self.ranking, top=2, n_sorteios=200)
        self.assertTrue(((freq >= 0) & (freq <= 1)).all())
        self.assertAlmostEqual(float(freq.sum()), 2.0, places=6)

    def test_e_reprodutivel_com_a_mesma_semente(self):
        pd.testing.assert_series_equal(frequencia_no_topo(self.ranking, 2, 200, 7), frequencia_no_topo(self.ranking, 2, 200, 7))

    def test_top_fora_do_intervalo_falha(self):
        with self.assertRaisesRegex(ValueError, "top"):
            frequencia_no_topo(self.ranking, top=99)


if __name__ == "__main__":
    unittest.main()
