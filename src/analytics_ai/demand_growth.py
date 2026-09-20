"""Crescimento da demanda prevista por Centro de Distribuição e Ponto de Venda.

Lê a previsão mês a mês do GLM (`ml_forecast_demanda_mensal`), cruza com a
dimensão de locais e responde: qual CD e qual PDV crescem mais nos três meses
previstos. Duas definições convivem:

- **trajetória dentro do horizonte** — mês 3 contra mês 1 da própria previsão,
  que é o que a pergunta pede ao pé da letra;
- **contra o ano anterior** — o trimestre previsto contra o mesmo trimestre
  realizado um ano antes, que retira a estação da conta.

CD e PDV não existem como vocabulário nas tabelas: CD é `location_type =
'warehouse'` e PDV é `location_type = 'store'`. Também não existe vínculo de
abastecimento entre loja e armazém em nenhuma tabela; o vínculo usado aqui é
geográfico (mesma UF, senão mesma região) e deve ser lido como hipótese.

Módulo pandas puro: não abre sessão Spark. A leitura das tabelas fica no
notebook 06.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from src.analytics_ai.demand_baselines import add_months

CD = "warehouse"
PDV = "store"
TIPO_LOCAL = {CD: "Centro de Distribuição", PDV: "Ponto de Venda"}
HORIZONTES = (1, 2, 3)
SERIE_MES = ("sk_product", "sk_location", "mes_previsto")
COLUNAS_MENSAL = (*SERIE_MES, "cutoff", "horizonte_mes", "demanda_prevista")
COLUNAS_LOCAIS = ("sk_location", "nk_location_id", "location_name", "location_type", "state", "region")
COLUNAS_VINCULO = ("cd_sk_location", "cd_associado", "criterio_vinculo", "ambiguo")


def _as_date(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values).dt.date


def _pct(numerador: pd.Series, base: pd.Series) -> pd.Series:
    base = base.astype(float)
    return pd.Series(
        np.where(base > 0, (numerador.astype(float) / base.where(base > 0, np.nan) - 1.0) * 100.0, np.nan),
        index=numerador.index,
    )


# Percentuais iguais por construção diferem na 12ª casa por acumulação de
# ponto flutuante; sem arredondar, o ranking seria decidido por esse ruído.
RANK_DECIMALS = 6


def _ranquear(frame: pd.DataFrame, coluna: str, nome: str, desempate: str) -> pd.DataFrame:
    """Posição de cada linha ordenando por `coluna` (desc), `desempate` (desc) e nome (asc)."""
    chave = frame[coluna].round(RANK_DECIMALS)
    ordem = (
        frame.assign(_chave=chave)
        .sort_values(["_chave", desempate, "location_name"], ascending=[False, False, True], na_position="last")
        .index
    )
    frame[nome] = pd.Series(np.arange(1, len(frame) + 1), index=ordem).reindex(frame.index).astype(int)
    return frame


def _exigir_tipo(tipo: str) -> None:
    if tipo not in TIPO_LOCAL:
        raise ValueError(f"tipo de local desconhecido: {tipo!r}; use {sorted(TIPO_LOCAL)}")


def validar_previsao_mensal(mensal: pd.DataFrame) -> None:
    """Garante que a tabela mensal tem a forma que a análise supõe.

    Um único corte, uma linha por produto × loja × mês, sem nulos nem
    negativos, e exatamente os horizontes 1, 2 e 3 em toda série. Qualquer
    desvio levanta `ValueError` em vez de virar NaN silencioso nas somas.
    """
    faltando = [c for c in COLUNAS_MENSAL if c not in mensal.columns]
    if faltando:
        raise ValueError(f"colunas ausentes na previsão mensal: {faltando}")
    n_nulos = int(mensal["demanda_prevista"].isna().sum())
    if n_nulos:
        raise ValueError(f"demanda_prevista com {n_nulos} valores nulos")
    n_negativos = int((mensal["demanda_prevista"] < 0).sum())
    if n_negativos:
        raise ValueError(f"demanda_prevista com {n_negativos} valores negativos")
    cortes = mensal["cutoff"].nunique(dropna=False)
    if cortes != 1:
        raise ValueError(f"a análise supõe um único corte; a tabela tem {cortes}")
    n_dup = int(mensal.duplicated(list(SERIE_MES)).sum())
    if n_dup:
        raise ValueError(f"{n_dup} linhas duplicadas em {SERIE_MES}")
    esperado = set(HORIZONTES)
    por_serie = mensal.groupby(["sk_product", "sk_location"])["horizonte_mes"].agg(lambda h: set(h))
    fora = por_serie[por_serie != esperado]
    if len(fora):
        raise ValueError(f"{len(fora)} séries sem exatamente os horizontes {sorted(esperado)}")
    meses = mensal["mes_previsto"].nunique()
    if meses != len(HORIZONTES):
        raise ValueError(f"esperava {len(HORIZONTES)} meses previstos, encontrou {meses}")


def atribui_cd(locais: pd.DataFrame) -> pd.DataFrame:
    """Associa cada PDV a um CD por geografia: mesma UF, senão mesma região.

    Não há dado de abastecimento no projeto, então o vínculo é uma hipótese
    de proximidade. Com mais de um candidato no mesmo nível, fica o de menor
    `nk_location_id` e a linha é marcada como ambígua.
    """
    saida = locais.copy()
    cds = saida[saida["location_type"] == CD]
    vinculo = {}
    for idx, pdv in saida[saida["location_type"] == PDV].iterrows():
        candidatos, criterio = cds[cds["state"] == pdv["state"]], "mesma UF"
        if candidatos.empty:
            candidatos, criterio = cds[cds["region"] == pdv["region"]], "mesma região"
        if candidatos.empty:
            vinculo[idx] = (None, None, "sem CD", False)
            continue
        escolhido = candidatos.sort_values("nk_location_id").iloc[0]
        vinculo[idx] = (escolhido["sk_location"], escolhido["location_name"], criterio, len(candidatos) > 1)
    colunas = pd.DataFrame.from_dict(vinculo, orient="index", columns=list(COLUNAS_VINCULO))
    saida = saida.join(colunas)
    saida["ambiguo"] = saida["ambiguo"].map(lambda v: bool(v) if pd.notna(v) else False)
    return saida


def preparar_locais(dim_locations: pd.DataFrame) -> pd.DataFrame:
    """Reduz `dim_locations` aos CDs e PDVs, com rótulo em português e vínculo PDV → CD."""
    locais = dim_locations.loc[dim_locations["location_type"].isin(TIPO_LOCAL), list(COLUNAS_LOCAIS)].copy()
    locais["tipo"] = locais["location_type"].map(TIPO_LOCAL)
    return atribui_cd(locais).reset_index(drop=True)


def enriquecer(mensal: pd.DataFrame, locais: pd.DataFrame) -> pd.DataFrame:
    """Junta tipo, UF, região e vínculo de CD a cada linha da previsão mensal."""
    desconhecidos = sorted(set(mensal["sk_location"]) - set(locais["sk_location"]))
    if desconhecidos:
        raise ValueError(f"locais da previsão ausentes na dimensão: {desconhecidos}")
    atributos = locais[["sk_location", "location_type", "tipo", "state", "region", *COLUNAS_VINCULO]]
    saida = mensal.merge(atributos, on="sk_location", how="inner", validate="many_to_one")
    saida["mes_previsto"] = _as_date(saida["mes_previsto"])
    return saida


def _atributos_unidade(sub: pd.DataFrame, tipo: str) -> pd.DataFrame:
    colunas = ["sk_location", "location_name"]
    if tipo == PDV:
        colunas += ["cd_associado", "criterio_vinculo"]
    return sub[colunas].drop_duplicates("sk_location").set_index("sk_location")


def trajetoria_por_unidade(enriquecido: pd.DataFrame, tipo: str) -> pd.DataFrame:
    """Demanda prevista por unidade e mês, com as variações e o ranking.

    `cresc_abs_1_3` é a resposta principal; `cresc_pct_1_3` fica ao lado e
    vale NaN quando o mês 1 é zero. Os rankings ordenam por crescimento,
    depois pelo mês 3 e por fim pelo nome, para serem reprodutíveis.
    """
    _exigir_tipo(tipo)
    sub = enriquecido[enriquecido["location_type"] == tipo]
    por_mes = sub.groupby(["sk_location", "horizonte_mes"])["demanda_prevista"].sum().unstack("horizonte_mes")
    por_mes = por_mes.reindex(columns=list(HORIZONTES)).rename(columns=lambda h: f"mes_{h}")
    tab = _atributos_unidade(sub, tipo).join(por_mes).reset_index()
    tab["var_abs_1_2"] = tab["mes_2"] - tab["mes_1"]
    tab["var_pct_1_2"] = _pct(tab["mes_2"], tab["mes_1"])
    tab["var_abs_2_3"] = tab["mes_3"] - tab["mes_2"]
    tab["var_pct_2_3"] = _pct(tab["mes_3"], tab["mes_2"])
    tab["cresc_abs_1_3"] = tab["mes_3"] - tab["mes_1"]
    tab["cresc_pct_1_3"] = _pct(tab["mes_3"], tab["mes_1"])
    tab["base_zero"] = tab["mes_1"] <= 0
    tab = _ranquear(tab, "cresc_abs_1_3", "rank_abs", "mes_3")
    tab = _ranquear(tab, "cresc_pct_1_3", "rank_pct", "mes_3")
    return tab.sort_values("rank_abs").reset_index(drop=True)


def _meses_referencia(enriquecido: pd.DataFrame) -> list[dt.date]:
    return [add_months(m, -12) for m in sorted(enriquecido["mes_previsto"].unique())]


def _realizado_referencia(real: pd.DataFrame, meses: list[dt.date]) -> pd.DataFrame:
    real = real.assign(month_start_date=_as_date(real["month_start_date"]))
    return real[real["month_start_date"].isin(meses)]


def crescimento_vs_ano_anterior(enriquecido: pd.DataFrame, real: pd.DataFrame, tipo: str) -> pd.DataFrame:
    """Trimestre previsto contra o mesmo trimestre realizado doze meses antes.

    A unidade cujo realizado não tem os três meses de referência fica com
    `referencia_incompleta=True` e crescimento NaN, em vez de comparar com
    uma soma parcial.
    """
    _exigir_tipo(tipo)
    sub = enriquecido[enriquecido["location_type"] == tipo]
    meses = _meses_referencia(enriquecido)
    ref = _realizado_referencia(real, meses)
    tab = _atributos_unidade(sub, tipo)
    tab["previsto"] = sub.groupby("sk_location")["demanda_prevista"].sum()
    presentes = ref.groupby("sk_location")["month_start_date"].nunique().reindex(tab.index).fillna(0)
    tab["referencia_incompleta"] = presentes < len(meses)
    realizado = ref.groupby("sk_location")["demand_quantity"].sum().astype(float).reindex(tab.index)
    tab["realizado_ano_anterior"] = realizado.where(~tab["referencia_incompleta"])
    tab = tab.reset_index()
    tab["cresc_abs"] = tab["previsto"] - tab["realizado_ano_anterior"]
    tab["cresc_pct"] = _pct(tab["previsto"], tab["realizado_ano_anterior"])
    tab["queda"] = tab["cresc_abs"] < 0
    tab = _ranquear(tab, "cresc_abs", "rank_abs", "previsto")
    tab = _ranquear(tab, "cresc_pct", "rank_pct", "previsto")
    return tab.sort_values("rank_abs").reset_index(drop=True)


def contribuicao_produtos(
    enriquecido: pd.DataFrame, real: pd.DataFrame, produtos: pd.DataFrame, sk_location: str
) -> pd.DataFrame:
    """Quanto cada produto contribui para o crescimento de uma unidade, nas duas definições.

    As contribuições somam exatamente o crescimento da unidade. Produto sem
    realizado no ano anterior conta como zero — a série existe, só não vendeu.
    """
    sub = enriquecido[enriquecido["sk_location"] == sk_location]
    if sub.empty:
        raise ValueError(f"nenhuma previsão para o local {sk_location!r}")
    por_mes = sub.groupby(["sk_product", "horizonte_mes"])["demanda_prevista"].sum().unstack("horizonte_mes")
    tab = pd.DataFrame(
        {
            "mes_1": por_mes[HORIZONTES[0]],
            "mes_3": por_mes[HORIZONTES[-1]],
            "previsto": por_mes.sum(axis=1),
        }
    )
    ref = _realizado_referencia(real[real["sk_location"] == sk_location], _meses_referencia(enriquecido))
    tab["realizado_ano_anterior"] = (
        ref.groupby("sk_product")["demand_quantity"].sum().astype(float).reindex(tab.index).fillna(0.0)
    )
    tab["cresc_abs_1_3"] = tab["mes_3"] - tab["mes_1"]
    tab["cresc_ano_anterior_abs"] = tab["previsto"] - tab["realizado_ano_anterior"]
    nomes = sub[["sk_product", "sku"]].drop_duplicates("sk_product").merge(
        produtos[["sk_product", "product_name", "category_name"]], on="sk_product", how="left", validate="one_to_one"
    )
    tab = nomes.merge(tab.reset_index(), on="sk_product", how="left", validate="one_to_one")
    return tab.sort_values(
        ["cresc_ano_anterior_abs", "previsto", "sku"], ascending=[False, False, True]
    ).reset_index(drop=True)


def concentracao(valores: pd.Series, top_n: int = 10) -> dict[str, float]:
    """Quanto do crescimento total está nos `top_n` maiores e quantos itens fazem metade dele.

    Só faz sentido quando o total é positivo; caso contrário devolve NaN.
    """
    total = float(valores.sum())
    if total <= 0:
        return {"n": int(len(valores)), "total": total, "share_top_n": np.nan, "n_para_metade": np.nan}
    ordenado = valores.sort_values(ascending=False).to_numpy(dtype=float)
    acumulado = np.cumsum(ordenado) / total
    return {
        "n": int(len(valores)),
        "total": total,
        "share_top_n": float(ordenado[:top_n].sum() / total),
        "n_para_metade": int(np.argmax(acumulado >= 0.5) + 1),
    }


def evolucao_mensal(
    enriquecido: pd.DataFrame, real: pd.DataFrame, tipo: str, desde: dt.date
) -> pd.DataFrame:
    """Realizado (a partir de `desde`) e previsto, por unidade e mês, numa só tabela longa."""
    _exigir_tipo(tipo)
    sub = enriquecido[enriquecido["location_type"] == tipo]
    nomes = _atributos_unidade(sub, tipo)["location_name"]
    previsto = (
        sub.groupby(["sk_location", "mes_previsto"])["demanda_prevista"].sum().rename("valor").reset_index()
    ).rename(columns={"mes_previsto": "mes"})
    previsto["origem"] = "previsto"
    hist = real.assign(month_start_date=_as_date(real["month_start_date"]))
    hist = hist[hist["sk_location"].isin(nomes.index) & (hist["month_start_date"] >= desde)]
    realizado = (
        hist.groupby(["sk_location", "month_start_date"])["demand_quantity"].sum().astype(float).rename("valor")
    ).reset_index().rename(columns={"month_start_date": "mes"})
    realizado["origem"] = "realizado"
    saida = pd.concat([realizado, previsto], ignore_index=True)
    saida.insert(1, "location_name", saida["sk_location"].map(nomes))
    return saida.sort_values(["location_name", "mes"]).reset_index(drop=True)
