"""Onde abrir o próximo ponto da rede: UF candidata e tipo (loja ou armazém).

Cruza a demanda por UF do cliente (`agg_sales_by_customer_state_month`), a
distância até a unidade mais próxima e o crescimento ano contra ano para
responder onde um novo ponto reduziria mais o deslocamento da rede e se ele
deve ser loja (`store`) ou armazém (`warehouse`).

Não há frete, latitude/longitude de cliente nem histórico de entrega no
projeto. Três hipóteses sustentam a análise e devem ser lidas como tal:

- o cliente é representado pela capital da sua UF e a unidade também (os
  nomes de cidade das unidades são fictícios), então duas unidades na mesma
  UF ficam a distância zero uma da outra;
- o custo logístico é modelado como demanda × km, em linha reta, e não como
  frete real;
- o ganho de um candidato é o de abrir **um** ponto (p-median de uma
  instalação), sem capacidade, sem custo de investimento e sem reação da
  demanda à nova cobertura.

Módulo pandas puro: não abre sessão Spark. A leitura das tabelas fica no
notebook 09.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata

import numpy as np
import pandas as pd

from src.analytics_ai.demand_common import add_months

RAIO_TERRA_KM = 6371.0088
CD = "warehouse"
PDV = "store"
SEM_UF = "SEM_UF"
COLUNAS_VENDAS = (
    "month_start_date",
    "customer_state",
    "sk_location",
    "channel",
    "quantity_ordered",
    "net_revenue",
    "estimated_gross_profit",
    "order_item_count",
)
GRAO_VENDAS = ("month_start_date", "customer_state", "sk_location", "channel")
COLUNAS_UFS = ("state", "latitude", "longitude")
COLUNAS_LOCAIS = ("sk_location", "location_name", "location_type", "state", "is_active", "latitude", "longitude")
PESOS_PADRAO = {"unidades": 0.25, "receita": 0.25, "distancia": 0.30, "crescimento": 0.20}
LIMITE_CONCENTRACAO = 0.7
LIMITE_KM_ARMAZEM_PERTO = 300.0
LIMITE_LINHAS_BAIXA_CONFIANCA = 30

# Percentuais iguais por construção diferem na 12ª casa por acumulação de
# ponto flutuante; sem arredondar, o ranking seria decidido por esse ruído.
RANK_DECIMALS = 6


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Distância em linha reta (km) entre pares de coordenadas em graus, vetorizada."""
    p1, p2 = np.radians(np.asarray(lat1, dtype=float)), np.radians(np.asarray(lat2, dtype=float))
    dlat = p2 - p1
    dlon = np.radians(np.asarray(lon2, dtype=float)) - np.radians(np.asarray(lon1, dtype=float))
    a = np.sin(dlat / 2.0) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * RAIO_TERRA_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _exigir_colunas(frame: pd.DataFrame, colunas: tuple[str, ...], nome: str) -> None:
    faltando = [c for c in colunas if c not in frame.columns]
    if faltando:
        raise ValueError(f"colunas ausentes em {nome}: {faltando}")


def _normalizar_texto(valor: str) -> str:
    """Minúsculas, sem acento e só letras e dígitos: 'E-commerce ' vira 'ecommerce'."""
    sem_acento = unicodedata.normalize("NFKD", str(valor)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())


def _as_date(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values).dt.date


def preparar_vendas(vendas: pd.DataFrame) -> pd.DataFrame:
    """Tipos de trabalho: medidas em float (o Spark entrega `Decimal`) e mês como `date`."""
    _exigir_colunas(vendas, COLUNAS_VENDAS, "vendas por UF")
    saida = vendas.copy()
    for coluna in ("quantity_ordered", "net_revenue", "estimated_gross_profit"):
        saida[coluna] = pd.to_numeric(saida[coluna]).astype(float)
    saida["month_start_date"] = _as_date(saida["month_start_date"])
    return saida


def validar_vendas_uf(vendas: pd.DataFrame) -> None:
    """Garante que a tabela de vendas por UF tem a forma que a análise supõe.

    Colunas presentes, sem nulos nas medidas, sem quantidade negativa e uma
    única linha por mês × UF × unidade × canal. Qualquer desvio levanta
    `ValueError` em vez de virar NaN silencioso nas somas.
    """
    _exigir_colunas(vendas, COLUNAS_VENDAS, "vendas por UF")
    for coluna in ("quantity_ordered", "net_revenue"):
        n_nulos = int(vendas[coluna].isna().sum())
        if n_nulos:
            raise ValueError(f"{coluna} com {n_nulos} valores nulos")
    n_negativos = int((vendas["quantity_ordered"] < 0).sum())
    if n_negativos:
        raise ValueError(f"quantity_ordered com {n_negativos} valores negativos")
    n_dup = int(vendas.duplicated(list(GRAO_VENDAS)).sum())
    if n_dup:
        raise ValueError(f"{n_dup} linhas duplicadas em {GRAO_VENDAS}")


def separar_canal_entrega(vendas: pd.DataFrame, canais_entrega: tuple[str, ...] = ("ecommerce",)) -> pd.DataFrame:
    """Só os canais em que a distância origem → cliente é um sinal real.

    Na venda de balcão o cliente foi até a unidade, então misturar os dois
    canais puxa a distância média para baixo e esconde as UFs mal atendidas.
    A comparação ignora caixa, acento e pontuação do nome do canal.
    """
    _exigir_colunas(vendas, ("channel",), "vendas por UF")
    alvo = {_normalizar_texto(c) for c in canais_entrega}
    return vendas[vendas["channel"].map(_normalizar_texto).isin(alvo)].copy()


def _validar_coordenadas(frame: pd.DataFrame, nome: str) -> None:
    sem_coordenada = frame[frame["latitude"].isna() | frame["longitude"].isna()]
    if len(sem_coordenada):
        raise ValueError(f"{len(sem_coordenada)} linhas de {nome} sem coordenada")


def matriz_uf_uf(ufs: pd.DataFrame) -> pd.DataFrame:
    """Distância (km) entre as capitais de todas as UFs, quadrada, indexada por UF."""
    _exigir_colunas(ufs, COLUNAS_UFS, "ufs")
    _validar_coordenadas(ufs, "ufs")
    lat = ufs["latitude"].to_numpy(dtype=float)
    lon = ufs["longitude"].to_numpy(dtype=float)
    matriz = haversine_km(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    return pd.DataFrame(matriz, index=ufs["state"].to_numpy(), columns=ufs["state"].to_numpy())


def distancia_uf_local(ufs: pd.DataFrame, locais: pd.DataFrame) -> pd.DataFrame:
    """UF × unidade ativa, com a distância (km) entre a capital da UF e a unidade.

    Unidade inativa não atende ninguém e fica de fora. Unidade ativa sem
    coordenada levanta `ValueError`: sumir em silêncio deixaria a rede
    parecer mais esparsa do que é.
    """
    _exigir_colunas(ufs, COLUNAS_UFS, "ufs")
    _exigir_colunas(locais, COLUNAS_LOCAIS, "locais")
    ativos = locais[locais["is_active"].astype(bool)]
    if ativos.empty:
        raise ValueError("nenhuma unidade ativa nos locais")
    _validar_coordenadas(ufs, "ufs")
    _validar_coordenadas(ativos, "locais ativos")
    cruzado = ufs[["state", "latitude", "longitude"]].merge(
        ativos[["sk_location", "location_type", "latitude", "longitude"]],
        how="cross",
        suffixes=("_uf", "_local"),
    )
    cruzado["distancia_km"] = haversine_km(
        cruzado["latitude_uf"], cruzado["longitude_uf"], cruzado["latitude_local"], cruzado["longitude_local"]
    )
    return cruzado[["state", "sk_location", "location_type", "distancia_km"]].reset_index(drop=True)


def distancia_atendimento_atual(distancias: pd.DataFrame, tipo: str | None = None) -> pd.Series:
    """Menor distância (km) de cada UF a uma unidade ativa; `tipo` restringe a loja ou armazém.

    UF sem nenhuma unidade do tipo pedido fica com NaN, não com zero.
    """
    base = distancias if tipo is None else distancias[distancias["location_type"] == tipo]
    minimo = base.groupby("state")["distancia_km"].min()
    return minimo.reindex(distancias["state"].unique()).rename("distancia_km").sort_index()


def distancia_real_de_atendimento(vendas: pd.DataFrame, distancias: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Distância média (km) que cada UF de fato percorre até a unidade que a atendeu.

    Pondera por unidades vendidas, a partir do par origem → UF do próprio
    fato. Devolve a tabela por UF e a fração das unidades que ficou de fora
    por não ter par (SEM_UF ou unidade que não está nas distâncias).
    """
    _exigir_colunas(vendas, COLUNAS_VENDAS, "vendas por UF")
    pares = distancias[["state", "sk_location", "distancia_km"]]
    juntado = vendas.merge(
        pares, how="left", left_on=["customer_state", "sk_location"], right_on=["state", "sk_location"]
    )
    total = float(vendas["quantity_ordered"].sum())
    valido = juntado[juntado["distancia_km"].notna()].copy()
    descartado = float(juntado.loc[juntado["distancia_km"].isna(), "quantity_ordered"].sum())
    valido["_ponderado"] = valido["quantity_ordered"] * valido["distancia_km"]
    tabela = valido.groupby("customer_state").agg(
        unidades=("quantity_ordered", "sum"), _ponderado=("_ponderado", "sum")
    )
    tabela["distancia_media_km"] = tabela["_ponderado"] / tabela["unidades"].where(tabela["unidades"] > 0)
    tabela = tabela.drop(columns="_ponderado").rename_axis("state").reset_index()
    return tabela, (descartado / total if total > 0 else float("nan"))


def demanda_por_uf(vendas: pd.DataFrame, desde: dt.date, ate: dt.date) -> pd.DataFrame:
    """Unidades, receita, lucro estimado e linhas de venda por UF do cliente, com `desde` e `ate` inclusive.

    SEM_UF fica fora: não tem coordenada e não pode ser candidata nem cliente
    de distância. A cobertura correspondente é reportada no notebook.
    """
    _exigir_colunas(vendas, COLUNAS_VENDAS, "vendas por UF")
    mes = _as_date(vendas["month_start_date"])
    janela = vendas[(mes >= desde) & (mes <= ate) & (vendas["customer_state"] != SEM_UF)]
    tabela = janela.groupby("customer_state").agg(
        unidades=("quantity_ordered", "sum"),
        receita=("net_revenue", "sum"),
        lucro_estimado=("estimated_gross_profit", "sum"),
        linhas=("order_item_count", "sum"),
    )
    return tabela.rename_axis("state")


def crescimento_yoy_por_uf(vendas: pd.DataFrame, mes_fim: dt.date) -> pd.DataFrame:
    """Unidades dos 12 meses até `mes_fim` contra os 12 anteriores, por UF.

    `mes_fim` deve ser um mês completo. Se a base não cobre os 24 meses, a
    referência é marcada incompleta e o crescimento vira NaN para todas as
    UFs, em vez de comparar com uma base parcial. UF sem venda na referência
    também fica NaN: crescimento sobre zero não é número.
    """
    _exigir_colunas(vendas, COLUNAS_VENDAS, "vendas por UF")
    inicio_atual = add_months(mes_fim, -11)
    inicio_anterior = add_months(mes_fim, -23)
    mes = _as_date(vendas["month_start_date"])
    com_uf = vendas["customer_state"] != SEM_UF
    atual = vendas[com_uf & (mes >= inicio_atual) & (mes <= mes_fim)].groupby("customer_state")["quantity_ordered"].sum()
    anterior = (
        vendas[com_uf & (mes >= inicio_anterior) & (mes < inicio_atual)].groupby("customer_state")["quantity_ordered"].sum()
    )
    tabela = pd.DataFrame({"atual": atual, "anterior": anterior}).fillna(0.0).rename_axis("state")
    incompleta = bool(mes.min() > inicio_anterior)
    tabela["referencia_incompleta"] = incompleta
    base = tabela["anterior"].where(tabela["anterior"] > 0)
    crescimento = (tabela["atual"] / base - 1.0) * 100.0
    tabela["crescimento_pct"] = np.nan if incompleta else crescimento
    return tabela


def ganho_por_candidato(demanda_uf: pd.Series, distancia_atual: pd.Series, uf_uf: pd.DataFrame) -> pd.DataFrame:
    """O que abrir um ponto em cada UF economizaria, em unidade·km.

    Para a candidata `u`, a distância de cada UF `v` passa a ser
    `min(atual_v, dist(v, u))`; o ganho é a soma de `demanda_v × (atual_v −
    nova_v)`. Nunca é negativo: um ponto novo só pode aproximar. Uma UF que
    já tem unidade ganha zero, porque ninguém fica mais perto dela do que ela
    mesma.

    Devolve, por candidata: `ganho_unidade_km`, `km_medio_evitado` (ganho
    dividido pela demanda total da rede), `ganho_propria_uf` (fração do ganho
    que fica na própria UF) e `n_ufs_beneficiadas`.
    """
    estados = list(uf_uf.index)
    demanda = demanda_uf.reindex(estados).fillna(0.0).to_numpy(dtype=float)
    atual = distancia_atual.reindex(estados).to_numpy(dtype=float)
    if np.isnan(atual).any():
        raise ValueError("distância atual ausente para: " + ", ".join(np.array(estados)[np.isnan(atual)]))
    economia = np.clip(atual[:, None] - uf_uf.to_numpy(dtype=float), 0.0, None)  # linha v, coluna u
    ganho_vu = demanda[:, None] * economia
    total = ganho_vu.sum(axis=0)
    propria = np.diag(ganho_vu)
    tabela = pd.DataFrame(
        {
            "ganho_unidade_km": total,
            "km_medio_evitado": total / demanda.sum() if demanda.sum() > 0 else np.nan,
            "ganho_propria_uf": np.where(total > 0, propria / np.where(total > 0, total, 1.0), np.nan),
            "n_ufs_beneficiadas": (ganho_vu > 0).sum(axis=0),
        },
        index=pd.Index(estados, name="state"),
    )
    return tabela


def classificar_tipo(
    ganho: pd.DataFrame,
    distancia_armazem: pd.Series,
    limite_concentracao: float = LIMITE_CONCENTRACAO,
    limite_km_armazem_perto: float = LIMITE_KM_ARMAZEM_PERTO,
) -> pd.DataFrame:
    """Loja, armazém ou ambíguo, com o motivo em texto.

    - ganho espalhado pelas vizinhas (fração na própria UF abaixo do limite)
      → `warehouse`: o ponto serve uma região, não só a UF;
    - ganho concentrado na própria UF e já existe armazém a até
      `limite_km_armazem_perto` km → `store`: a UF precisa de presença, não de
      um centro de distribuição;
    - ganho concentrado e nenhum armazém por perto → `ambiguo`: seria um CD
      isolado, sem demanda regional que o sustente;
    - ganho zero → `sem_ganho`.
    """
    dist_armazem = distancia_armazem.reindex(ganho.index)
    linhas = []
    for estado, linha in ganho.iterrows():
        concentracao = linha["ganho_propria_uf"]
        if not linha["ganho_unidade_km"] > 0:
            linhas.append(("sem_ganho", "não reduz a distância de nenhuma UF"))
        elif concentracao < limite_concentracao:
            linhas.append(
                (
                    CD,
                    f"ganho espalhado: {(1 - concentracao) * 100:.0f}% fora da própria UF, "
                    f"{int(linha['n_ufs_beneficiadas'])} UFs beneficiadas",
                )
            )
        elif dist_armazem.loc[estado] <= limite_km_armazem_perto:
            linhas.append(
                (
                    PDV,
                    f"ganho concentrado ({concentracao * 100:.0f}% na própria UF) e armazém a "
                    f"{dist_armazem.loc[estado]:.0f} km",
                )
            )
        else:
            linhas.append(
                (
                    "ambiguo",
                    f"ganho concentrado ({concentracao * 100:.0f}% na própria UF), mas o armazém mais "
                    f"próximo está a {dist_armazem.loc[estado]:.0f} km",
                )
            )
    return pd.DataFrame(linhas, index=ganho.index, columns=["tipo_recomendado", "motivo"])


def sinalizar_baixa_confianca(linhas_por_uf: pd.Series, limite: int = LIMITE_LINHAS_BAIXA_CONFIANCA) -> pd.Series:
    """UF com poucas linhas de venda: pode ser demanda reprimida pela distância, não ausência de mercado."""
    return (linhas_por_uf < limite).rename("baixa_confianca")


def _minmax(valores: pd.Series) -> pd.Series:
    """Normaliza para 0–1; coluna constante vira 0 (não discrimina) e NaN vira 0."""
    v = valores.astype(float)
    amplitude = v.max() - v.min()
    if not amplitude > 0:
        return pd.Series(0.0, index=v.index)
    return ((v - v.min()) / amplitude).fillna(0.0)


def _posicao(valores: pd.Series) -> pd.Series:
    """Posição decrescente; o empate se resolve pelo nome da UF, para ser reprodutível."""
    chave = pd.DataFrame({"v": valores.round(RANK_DECIMALS).to_numpy(), "estado": valores.index.to_numpy()})
    ordem = valores.index[chave.sort_values(["v", "estado"], ascending=[False, True]).index]
    return pd.Series(np.arange(1, len(valores) + 1), index=ordem).reindex(valores.index).astype(int)


def ranquear_candidatos(
    demanda: pd.DataFrame,
    crescimento: pd.Series,
    ufs: pd.DataFrame,
    locais: pd.DataFrame,
    pesos: dict[str, float] | None = None,
    limite_concentracao: float = LIMITE_CONCENTRACAO,
    limite_km_armazem_perto: float = LIMITE_KM_ARMAZEM_PERTO,
    limite_linhas: int = LIMITE_LINHAS_BAIXA_CONFIANCA,
) -> pd.DataFrame:
    """Uma linha por UF candidata, com duas leituras do mesmo problema lado a lado.

    - `rank_ganho`: qual ponto novo economiza mais unidade·km na rede toda;
    - `rank_score`: nota composta de unidades, receita, distância atual ao
      ponto mais próximo (quanto maior, melhor) e crescimento, cada parcela
      normalizada de 0 a 1 e visível em colunas próprias.

    Concordância entre os dois rankings fortalece a conclusão; divergência é
    o achado. `crescimento` sem valor entra com parcela zero e
    `crescimento_indisponivel=True`.
    """
    pesos = dict(PESOS_PADRAO if pesos is None else pesos)
    if set(pesos) != set(PESOS_PADRAO) or abs(sum(pesos.values()) - 1.0) > 1e-9:
        raise ValueError(f"pesos devem ter as chaves {sorted(PESOS_PADRAO)} e somar 1")
    distancias = distancia_uf_local(ufs, locais)
    atual = distancia_atendimento_atual(distancias)
    dist_armazem = distancia_atendimento_atual(distancias, CD)
    ganho = ganho_por_candidato(demanda["unidades"], atual, matriz_uf_uf(ufs))
    estados = ganho.index
    tabela = ganho.join(classificar_tipo(ganho, dist_armazem, limite_concentracao, limite_km_armazem_perto))
    tabela["distancia_atual_km"] = atual.reindex(estados)
    tabela["distancia_armazem_km"] = dist_armazem.reindex(estados)
    tabela["unidades"] = demanda["unidades"].reindex(estados).fillna(0.0)
    tabela["receita"] = demanda["receita"].reindex(estados).fillna(0.0)
    tabela["crescimento_pct"] = crescimento.reindex(estados)
    tabela["crescimento_indisponivel"] = tabela["crescimento_pct"].isna()
    tabela["baixa_confianca"] = sinalizar_baixa_confianca(demanda["linhas"].reindex(estados).fillna(0.0), limite_linhas)
    ativos = set(locais.loc[locais["is_active"].astype(bool), "state"])
    tabela["ja_tem_unidade"] = [e in ativos for e in estados]
    parcelas = {
        "unidades": _minmax(tabela["unidades"]),
        "receita": _minmax(tabela["receita"]),
        "distancia": _minmax(tabela["distancia_atual_km"]),
        "crescimento": _minmax(tabela["crescimento_pct"]),
    }
    for nome, serie in parcelas.items():
        tabela[f"parcela_{nome}"] = serie
    tabela["score"] = sum(pesos[nome] * serie for nome, serie in parcelas.items())
    tabela["rank_ganho"] = _posicao(tabela["ganho_unidade_km"])
    tabela["rank_score"] = _posicao(tabela["score"])
    return tabela.sort_values("rank_ganho")


def frequencia_no_topo(
    ranking: pd.DataFrame, top: int = 3, n_sorteios: int = 1000, semente: int = 0
) -> pd.Series:
    """Em que fração de pesos sorteados cada UF fica entre as `top` primeiras do score.

    Os pesos vêm de uma Dirichlet uniforme (todas as combinações que somam 1
    são igualmente prováveis), aplicada às parcelas já normalizadas de
    `ranquear_candidatos`. UF que só lidera com um peso específico aparece
    pouco; UF que lidera qualquer que seja o peso, muito.
    """
    parcelas = [f"parcela_{nome}" for nome in PESOS_PADRAO]
    _exigir_colunas(ranking, tuple(parcelas), "ranking")
    if not 1 <= top <= len(ranking):
        raise ValueError(f"top deve estar entre 1 e {len(ranking)}")
    pesos = np.random.default_rng(semente).dirichlet(np.ones(len(parcelas)), size=n_sorteios)
    notas = pesos @ ranking[parcelas].to_numpy(dtype=float).T  # sorteio × UF
    estados = np.array(ranking.index)
    # desempate por nome da UF, como no ranking: ordena por (nota desc, nome asc)
    ordem_nome = np.argsort(estados, kind="stable")
    notas_ord = notas[:, ordem_nome]
    posicoes = np.argsort(-np.round(notas_ord, RANK_DECIMALS), axis=1, kind="stable")[:, :top]
    contagem = np.bincount(ordem_nome[posicoes].ravel(), minlength=len(estados))
    return pd.Series(contagem / n_sorteios, index=estados, name="frequencia_no_topo")


def selecao_gulosa(
    demanda_uf: pd.Series, distancia_atual: pd.Series, uf_uf: pd.DataFrame, n_pontos: int = 3
) -> pd.DataFrame:
    """Abre um ponto por vez, sempre o de maior ganho dado o que já foi aberto.

    Mostra quanto o segundo e o terceiro ponto valem depois do primeiro: UFs
    vizinhas disputam a mesma demanda, então o segundo colocado do ranking
    simples costuma valer bem menos quando o primeiro já existe.
    """
    estados = list(uf_uf.index)
    atual = distancia_atual.reindex(estados).astype(float).copy()
    demanda = demanda_uf.reindex(estados).fillna(0.0).astype(float)
    total = float(demanda.sum())
    passos = []
    for passo in range(1, n_pontos + 1):
        ganho = ganho_por_candidato(demanda, atual, uf_uf)["ganho_unidade_km"]
        ordenado = ganho.round(RANK_DECIMALS).reset_index().sort_values(["ganho_unidade_km", "state"], ascending=[False, True])
        escolhida = ordenado["state"].iloc[0]
        atual = np.minimum(atual, uf_uf[escolhida].reindex(estados).astype(float))
        passos.append(
            {
                "passo": passo,
                "state": escolhida,
                "ganho_unidade_km": float(ganho[escolhida]),
                "distancia_media_apos_km": float((demanda * atual).sum() / total) if total > 0 else float("nan"),
            }
        )
    return pd.DataFrame(passos)


def participacao_unidade_mais_proxima(vendas: pd.DataFrame, distancias: pd.DataFrame, tolerancia_km: float = 1e-6) -> float:
    """Fração das unidades vendidas que saiu de uma unidade mais próxima do cliente.

    Empate conta como acerto (duas unidades na mesma UF ficam a distância
    zero uma da outra). Vale para qualquer recorte de `vendas`; linhas sem par
    UF × unidade (SEM_UF, unidade fora das distâncias) ficam de fora da conta.
    """
    _exigir_colunas(vendas, COLUNAS_VENDAS, "vendas por UF")
    minimo = distancias.groupby("state")["distancia_km"].min().rename("minimo_km")
    pares = distancias[["state", "sk_location", "distancia_km"]].join(minimo, on="state")
    juntado = vendas.merge(pares, how="inner", left_on=["customer_state", "sk_location"], right_on=["state", "sk_location"])
    total = float(juntado["quantity_ordered"].sum())
    if total <= 0:
        return float("nan")
    certas = juntado["distancia_km"] <= juntado["minimo_km"] + tolerancia_km
    return float(juntado.loc[certas, "quantity_ordered"].sum() / total)
