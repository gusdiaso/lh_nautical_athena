"""GLM Poisson/Tweedie para a previsão de demanda de 3 meses (Etapa 4 do plano).

Treina um Modelo Linear Generalizado sobre a tabela de features
`ml_features_produto_loja_mes` para prever `target_3m` — o total vendido por
uma série produto × loja nos 3 meses seguintes a um mês de corte.

A régua da Etapa 2 (`baseline_pred_categoria_local_idx_trend`) entra como
*offset* de log, não como feature comum. Com link log isso dá

    demanda_esperada = régua × exp(X · beta)

ou seja, o modelo aprende uma correção multiplicativa sobre a régua, em vez de
reaprender a mesma conta do zero. Como efeito colateral desejável, qualquer
regularização encolhe a previsão na direção da régua, e não na direção da
média global.

Este módulo é pandas/numpy/scikit-learn puro: não lê nem escreve no Databricks.
A camada Spark vive em `demand_predictions.py`, e as métricas são as mesmas de
`demand_baselines.py` — nenhum erro é recalculado aqui.
"""

from __future__ import annotations

import datetime as dt
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import PoissonRegressor, TweedieRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from src.analytics_ai.demand_baselines import (
    HORIZON,
    add_months,
    comparison_scorecard,
    error_table,
)

TARGET_COL = "target_3m"
BASELINE_COL = "baseline_pred_categoria_local_idx_trend"
CUTOFF_COL = "cutoff"
ID_COLS = ("sk_product", "sk_location")
SEASONAL_COLS = (
    "seasonal_index_month_plus1",
    "seasonal_index_month_plus2",
    "seasonal_index_month_plus3",
)

# Nunca entram no treino: identificadores de alta cardinalidade que não
# generalizam, o próprio alvo, e as flags que dependem do futuro.
EXCLUDED_FROM_TRAINING = (
    "sk_product",
    "sk_location",
    "sku",
    "product_name",
    "cutoff",
    "target_3m",
    "is_target_complete",
    "trend_ready",
)

# Fronteiras do split temporal, em meses de corte. O teste são os 12 cortes
# mais recentes com alvo completo — os mesmos 12 em que a régua foi medida,
# o que torna os números diretamente comparáveis.
# Recência atribuída a quem nunca vendeu: acima do maior valor já observado
# no painel (53 meses), e fixa, para não depender do recorte.
NEVER_SOLD_MONTHS = 60.0

TRAIN_END = dt.date(2024, 5, 1)
VALIDATION_END = dt.date(2025, 5, 1)
TEST_END = dt.date(2026, 5, 1)


def _safe_log(x: np.ndarray) -> np.ndarray:
    """Log com piso, para quantidades que deveriam ser positivas mas podem zerar."""
    return np.log(np.clip(np.asarray(x, dtype=float), 1e-6, None))


def _zeros_column(x: np.ndarray) -> np.ndarray:
    """Coluna constante de zeros, para o modelo só de intercepto.

    O scikit-learn recusa uma matriz sem nenhuma coluna, mas o passo que só
    recalibra a régua não tem feature alguma. Uma coluna de zeros deixa o
    intercepto carregar todo o ajuste e recebe coeficiente zero.
    """
    return np.zeros((len(np.asarray(x)), 1), dtype=float)


def _intercept_name(transformer, input_features) -> np.ndarray:
    """Nome da coluna morta do modelo só de intercepto."""
    return np.asarray(["intercepto"], dtype=object)


@dataclass(frozen=True)
class GlmConfig:
    """Configuração de um GLM: família, regularização e conjunto de features.

    Attributes:
        name: Rótulo do modelo; vai para o scorecard e para a tabela Delta.
        family: `poisson` ou `tweedie`.
        power: Parâmetro de potência do Tweedie (ignorado quando family=poisson).
        alpha: Força da penalidade L2 do scikit-learn.
        use_offset: Usa a régua como offset de log.
        log_features: Colunas positivas que entram como log(x) — efeito
            multiplicativo x**beta sobre a média.
        log1p_features: Contagens com zeros legítimos, entram como log1p(x).
        numeric_features: Colunas numéricas usadas sem transformação.
        categorical_features: Colunas categóricas, codificadas em one-hot.
        scale: Padroniza as colunas numéricas depois das transformações.
        solver: Solver do scikit-learn. `newton-cholesky` é o indicado para
            n >> p; o modelo só de intercepto precisa de `lbfgs`, porque a
            coluna morta deixa a hessiana singular.
        max_iter: Iterações máximas do solver.
        tol: Tolerância de convergência.
        mu_cap_ratio: Teto da previsão, em múltiplos do offset.
        baseline_floor: Piso da régua, para evitar log(0) no offset.
    """

    name: str
    family: str = "poisson"
    power: float = 1.0
    alpha: float = 1e-4
    use_offset: bool = True
    log_features: tuple[str, ...] = ()
    log1p_features: tuple[str, ...] = ()
    numeric_features: tuple[str, ...] = ()
    categorical_features: tuple[str, ...] = ()
    scale: bool = True
    solver: str = "newton-cholesky"
    max_iter: int = 300
    tol: float = 1e-8
    mu_cap_ratio: float = 20.0
    baseline_floor: float = 0.01

    @property
    def all_features(self) -> tuple[str, ...]:
        """Todas as colunas que o modelo consome, na ordem das transformações."""
        return (
            *self.log_features,
            *self.log1p_features,
            *self.numeric_features,
            *self.categorical_features,
        )

    @property
    def tweedie_power(self) -> float:
        """Potência efetiva da família: Poisson é o caso power=1."""
        return 1.0 if self.family == "poisson" else self.power


@dataclass(frozen=True)
class DemandSplits:
    """Os quatro recortes temporais do painel de features."""

    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    inference: pd.DataFrame
    n_discarded: int = 0


@dataclass(frozen=True)
class FittedGlm:
    """Um GLM ajustado, com o que é preciso para prever e para interpretar."""

    pipeline: Pipeline
    config: GlmConfig
    n_train: int
    dispersao_pearson: float
    n_baseline_no_piso: int = 0
    feature_names: tuple[str, ...] = field(default=())


# ── Normalização do painel ──────────────────────────────────────────


def normalize_panel(features: pd.DataFrame) -> pd.DataFrame:
    """Converte os tipos que vêm do Delta para os que o scikit-learn aceita.

    As colunas criadas com `round()` no dbt chegam como DECIMAL e viram
    objetos `decimal.Decimal` no pandas — que não suportam aritmética com
    float e quebram tanto o treino quanto as métricas.

    As chaves `sk_product` e `sk_location` são hashes MD5 em texto, não
    números, e ficam como estão.

    Args:
        features: Painel lido de `ml_features_produto_loja_mes`.

    Returns:
        Cópia do painel com as colunas numéricas em float64.
    """
    frame = features.copy()
    for coluna in frame.columns:
        if frame[coluna].dtype != object:
            continue
        amostra = frame[coluna].dropna()
        if amostra.empty or not isinstance(amostra.iloc[0], Decimal):
            continue
        frame[coluna] = pd.to_numeric(frame[coluna], errors="coerce").astype(float)
    return frame


def prepare_features(features: pd.DataFrame) -> pd.DataFrame:
    """Torna explícito o único nulo legítimo do painel: a série que nunca vendeu.

    `months_since_last_sale` é nulo quando a série jamais registrou venda — não
    há "última venda" para contar a partir dela. São 0,9% das linhas de treino,
    todas com `sum_12m = 0`. Em vez de imputar um número qualquer, a
    informação vira duas colunas: a bandeira `nunca_vendeu` e um sentinela fixo
    de recência, maior que qualquer valor observado.

    O sentinela é uma constante definida a priori, não uma estatística dos
    dados, e por isso não transporta informação entre treino e teste.

    Args:
        features: Painel já normalizado.

    Returns:
        Cópia do painel com `nunca_vendeu` e `months_since_last_sale` completa.
    """
    frame = normalize_panel(features)
    nunca = frame["months_since_last_sale"].isna()
    frame["nunca_vendeu"] = nunca
    frame["months_since_last_sale"] = frame["months_since_last_sale"].fillna(NEVER_SOLD_MONTHS)
    return frame


# ── Split temporal ──────────────────────────────────────────────────


def split_panel(
    features: pd.DataFrame,
    train_end: dt.date = TRAIN_END,
    validation_end: dt.date = VALIDATION_END,
    test_end: dt.date = TEST_END,
    embargo_cutoffs: int = 0,
) -> DemandSplits:
    """Separa o painel por mês de corte, sem nunca sortear linhas.

    O treino ainda exige `trend_ready`, porque nos cortes sem 24 meses de
    histórico a régua e o crescimento são nulos. Validação, teste e inferência
    não podem conter essas linhas — se contiverem, é erro de dado e a função
    falha em vez de adivinhar.

    Args:
        features: Painel completo de `ml_features_produto_loja_mes`.
        train_end: Último mês de corte do treino.
        validation_end: Último mês de corte da validação.
        test_end: Último mês de corte do teste.
        embargo_cutoffs: Meses removidos do fim do treino, para medir o efeito
            da sobreposição entre a janela-alvo do treino e a da validação.

    Returns:
        DemandSplits com treino, validação, teste, inferência e a contagem de
        linhas descartadas por falta de `trend_ready`.

    Raises:
        ValueError: Se algum split de avaliação contiver linhas sem tendência.
    """
    frame = prepare_features(features)
    frame[CUTOFF_COL] = pd.to_datetime(frame[CUTOFF_COL]).dt.date

    completo = frame["is_target_complete"].fillna(False).astype(bool)
    pronto = frame["trend_ready"].fillna(False).astype(bool)

    fim_treino = add_months(train_end, -embargo_cutoffs)
    e_treino = completo & pronto & (frame[CUTOFF_COL] <= fim_treino)
    e_validacao = completo & (frame[CUTOFF_COL] > train_end) & (frame[CUTOFF_COL] <= validation_end)
    e_teste = completo & (frame[CUTOFF_COL] > validation_end) & (frame[CUTOFF_COL] <= test_end)
    e_inferencia = ~completo

    splits = DemandSplits(
        train=frame[e_treino].reset_index(drop=True),
        validation=frame[e_validacao].reset_index(drop=True),
        test=frame[e_teste].reset_index(drop=True),
        inference=frame[e_inferencia].reset_index(drop=True),
        n_discarded=int((completo & ~pronto).sum()),
    )
    for nome, parte in (
        ("validacao", splits.validation),
        ("teste", splits.test),
        ("inferencia", splits.inference),
    ):
        sem_tendencia = int((~parte["trend_ready"].fillna(False).astype(bool)).sum())
        if sem_tendencia:
            raise ValueError(
                f"{sem_tendencia} linhas sem trend_ready no split '{nome}'; "
                "a régua seria nula e o offset impossível."
            )
    return splits


def check_no_nulls(frame: pd.DataFrame, columns: Sequence[str]) -> None:
    """Falha nomeando a coluna e a contagem, em vez de imputar silenciosamente.

    Args:
        frame: Quadro a conferir.
        columns: Colunas que precisam estar completas.

    Raises:
        ValueError: Se faltar coluna ou houver nulos.
    """
    faltando = [c for c in columns if c not in frame.columns]
    if faltando:
        raise ValueError(f"colunas ausentes no painel: {sorted(faltando)}")
    nulos = {c: int(frame[c].isna().sum()) for c in columns if frame[c].isna().any()}
    if nulos:
        detalhe = ", ".join(f"{c}={n}" for c, n in sorted(nulos.items()))
        raise ValueError(f"nulos inesperados nas features: {detalhe}")


# ── Offset ──────────────────────────────────────────────────────────


def offset_values(frame: pd.DataFrame, floor: float) -> np.ndarray:
    """A régua como exposição do GLM, com piso para evitar log(0).

    Args:
        frame: Quadro com a coluna da régua.
        floor: Valor mínimo, em unidades vendidas em 3 meses.

    Returns:
        Vetor de offsets estritamente positivos.
    """
    return np.maximum(frame[BASELINE_COL].to_numpy(dtype=float), floor)


def offset_weights(offset: np.ndarray, family: str, power: float) -> np.ndarray:
    """Peso que transforma o ajuste de `y/e` no ajuste de `y` com offset `e`.

    O scikit-learn não tem parâmetro de offset/exposição, só `sample_weight`.
    A desviância unitária de Tweedie é homogênea de grau `2 - p`, isto é
    `d(c·y, c·mu) = c**(2-p) · d(y, mu)`. Logo ajustar `y/e` com peso
    `e**(2-p)` é exatamente o mesmo problema de otimização que ajustar `y`
    com offset `log(e)` — não é aproximação.

    Para Poisson (p=1) o peso é o próprio `e`. Usar `e` para qualquer p é o
    erro mais fácil de cometer aqui: o modelo treina sem reclamar e sai
    calibrado errado.

    Args:
        offset: Exposição por linha, positiva.
        family: `poisson` ou `tweedie`.
        power: Potência do Tweedie.

    Returns:
        Vetor de pesos de amostra.
    """
    if family == "poisson":
        return np.asarray(offset, dtype=float)
    return np.asarray(offset, dtype=float) ** (2.0 - power)


# ── Pipeline e treino ───────────────────────────────────────────────


def build_pipeline(config: GlmConfig) -> Pipeline:
    """Monta o pré-processamento e o regressor, sem ajustar nada.

    `remainder="drop"` é garantia estrutural: nenhuma coluna fora das listas
    de `config` chega ao modelo, mesmo que o quadro traga `sku` ou `cutoff`.

    Args:
        config: Configuração do modelo.

    Returns:
        Pipeline scikit-learn com os passos `prep` e `model`.
    """

    def _numerico(func) -> Pipeline:
        passos: list[tuple] = [
            ("func", FunctionTransformer(func, feature_names_out="one-to-one"))
        ]
        if config.scale:
            passos.append(("scale", StandardScaler()))
        return Pipeline(passos)

    blocos: list[tuple] = []
    if config.log_features:
        blocos.append(("log", _numerico(_safe_log), list(config.log_features)))
    if config.log1p_features:
        blocos.append(("log1p", _numerico(np.log1p), list(config.log1p_features)))
    if config.numeric_features:
        blocos.append(
            (
                "num",
                StandardScaler() if config.scale else "passthrough",
                list(config.numeric_features),
            )
        )
    if config.categorical_features:
        blocos.append(
            (
                "cat",
                OneHotEncoder(
                    handle_unknown="ignore",
                    drop="first",
                    sparse_output=False,
                    min_frequency=0.01,
                    max_categories=20,
                ),
                list(config.categorical_features),
            )
        )

    if not blocos:
        blocos.append(
            (
                "intercepto",
                FunctionTransformer(_zeros_column, feature_names_out=_intercept_name),
                [BASELINE_COL],
            )
        )

    if config.family == "poisson":
        modelo = PoissonRegressor(
            alpha=config.alpha,
            solver=config.solver,
            max_iter=config.max_iter,
            tol=config.tol,
        )
    else:
        modelo = TweedieRegressor(
            power=config.power,
            alpha=config.alpha,
            link="log",
            solver=config.solver,
            max_iter=config.max_iter,
            tol=config.tol,
        )

    return Pipeline(
        [("prep", ColumnTransformer(blocos, remainder="drop")), ("model", modelo)]
    )


def _pearson_dispersion(y: np.ndarray, mu: np.ndarray, power: float, n_params: int) -> float:
    """Dispersão de Pearson: >1 indica variância acima da que a família supõe."""
    mu = np.clip(mu, 1e-6, None)
    graus = max(len(y) - n_params, 1)
    return float(np.sum((y - mu) ** 2 / mu**power) / graus)


def _feature_names(pipeline: Pipeline) -> tuple[str, ...]:
    """Nomes das colunas que saem do pré-processamento."""
    prep = pipeline.named_steps["prep"]
    if isinstance(prep, str):
        return ()
    return tuple(str(nome) for nome in prep.get_feature_names_out())


def _predict_mu(
    pipeline: Pipeline,
    frame: pd.DataFrame,
    config: GlmConfig,
    offset: np.ndarray | None,
) -> np.ndarray:
    """Média prevista, já com o offset reaplicado e limitada a valores sãos."""
    mu = np.asarray(pipeline.predict(frame), dtype=float)
    if offset is not None:
        mu = mu * offset
        mu = np.minimum(mu, config.mu_cap_ratio * offset)
    return np.clip(np.nan_to_num(mu, nan=0.0, posinf=0.0, neginf=0.0), 0.0, None)


def fit_glm(train: pd.DataFrame, config: GlmConfig) -> FittedGlm:
    """Ajusta o GLM no treino, com a régua como offset quando configurado.

    Args:
        train: Apenas linhas de treino — nunca o painel inteiro.
        config: Configuração do modelo.

    Returns:
        FittedGlm com o pipeline ajustado e diagnósticos do ajuste.

    Raises:
        ValueError: Se houver nulos, feature proibida, ou o solver não convergir.
    """
    check_no_nulls(train, [*config.all_features, TARGET_COL])
    proibidas = set(config.all_features) & set(EXCLUDED_FROM_TRAINING)
    if proibidas:
        raise ValueError(f"features proibidas em '{config.name}': {sorted(proibidas)}")

    y = train[TARGET_COL].to_numpy(dtype=float)
    pipeline = build_pipeline(config)

    if config.use_offset:
        check_no_nulls(train, [BASELINE_COL])
        offset = offset_values(train, config.baseline_floor)
        n_piso = int((train[BASELINE_COL].to_numpy(dtype=float) < config.baseline_floor).sum())
        alvo = y / offset
        peso = offset_weights(offset, config.family, config.tweedie_power)
    else:
        offset, n_piso, alvo, peso = None, 0, y, None

    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        try:
            pipeline.fit(train, alvo, model__sample_weight=peso)
        except ConvergenceWarning as erro:
            raise ValueError(
                f"GLM '{config.name}' não convergiu em {config.max_iter} iterações: {erro}"
            ) from erro

    mu = _predict_mu(pipeline, train, config, offset)
    n_params = len(np.atleast_1d(pipeline.named_steps["model"].coef_)) + 1
    return FittedGlm(
        pipeline=pipeline,
        config=config,
        n_train=len(train),
        dispersao_pearson=_pearson_dispersion(y, mu, config.tweedie_power, n_params),
        n_baseline_no_piso=n_piso,
        feature_names=_feature_names(pipeline),
    )


def predict_total(model: FittedGlm, frame: pd.DataFrame) -> np.ndarray:
    """Prevê o total dos 3 meses seguintes, sempre >= 0 e sem NaN.

    Args:
        model: GLM ajustado.
        frame: Linhas a prever (validação, teste ou inferência).

    Returns:
        Vetor de demanda prevista para o total de 3 meses.
    """
    config = model.config
    check_no_nulls(frame, list(config.all_features))
    offset = None
    if config.use_offset:
        check_no_nulls(frame, [BASELINE_COL])
        offset = offset_values(frame, config.baseline_floor)
    return _predict_mu(model.pipeline, frame, config, offset)


def add_predictions(frame: pd.DataFrame, model: FittedGlm, column: str) -> pd.DataFrame:
    """Cópia do quadro com a coluna de previsão, no formato do scorecard.

    Args:
        frame: Linhas a prever.
        model: GLM ajustado.
        column: Nome da coluna de previsão a criar.

    Returns:
        Cópia de `frame` com a coluna nova.
    """
    saida = frame.copy()
    saida[column] = predict_total(model, frame)
    return saida


def coefficient_table(model: FittedGlm) -> pd.DataFrame:
    """Coeficientes e o efeito multiplicativo de cada feature sobre a média.

    Com link log, `exp(coef)` é o fator aplicado à previsão quando a feature
    sobe uma unidade na escala já transformada.

    Args:
        model: GLM ajustado.

    Returns:
        Uma linha por feature, da maior para a menor em valor absoluto.
    """
    regressor = model.pipeline.named_steps["model"]
    tabela = pd.DataFrame(
        {
            "feature": list(model.feature_names),
            "coeficiente": np.asarray(regressor.coef_, dtype=float),
        }
    )
    tabela["efeito_multiplicativo"] = np.exp(tabela["coeficiente"])
    ordem = tabela["coeficiente"].abs().sort_values(ascending=False).index
    tabela = tabela.reindex(ordem).reset_index(drop=True)
    return tabela.round({"coeficiente": 4, "efeito_multiplicativo": 4})


# ── Decomposição mensal ─────────────────────────────────────────────


def decompose_months(
    frame: pd.DataFrame,
    pred_col: str,
    cutoff_col: str = CUTOFF_COL,
    horizon: int = HORIZON,
) -> pd.DataFrame:
    """Reparte o total previsto de 3 meses entre os meses, pelo peso sazonal.

    O denominador é recalculado a partir dos três índices mensais, e não lido
    de `season_sum_next_3m`: a tabela dbt grava essa soma arredondada, e usar
    a soma explícita garante que os três meses somem exatamente o total.

    Não usa informação do futuro: os índices vêm de `ml_seasonal_trend`, que
    os calcula em cada corte só com histórico até o próprio corte.

    Args:
        frame: Linhas com o total previsto e os índices sazonais.
        pred_col: Coluna com o total previsto dos 3 meses.
        cutoff_col: Coluna do mês de corte.
        horizon: Quantidade de meses previstos.

    Returns:
        `horizon` linhas por linha de entrada, com mes_previsto,
        horizonte_mes, share_sazonal e demanda_prevista.

    Raises:
        ValueError: Se a soma dos índices sazonais não for positiva.
    """
    check_no_nulls(frame, [pred_col, cutoff_col, *SEASONAL_COLS])
    indices = frame[list(SEASONAL_COLS)].to_numpy(dtype=float)
    denominador = indices.sum(axis=1)
    if not np.all(denominador > 0):
        ruins = int((denominador <= 0).sum())
        raise ValueError(f"{ruins} linhas com soma de índices sazonais <= 0")

    cortes = pd.to_datetime(frame[cutoff_col]).dt.date
    partes = []
    for k in range(1, horizon + 1):
        parte = frame.copy()
        parte["horizonte_mes"] = k
        parte["mes_previsto"] = [add_months(c, k) for c in cortes]
        parte["share_sazonal"] = indices[:, k - 1] / denominador
        parte["demanda_prevista"] = frame[pred_col].to_numpy(dtype=float) * parte["share_sazonal"]
        partes.append(parte)

    saida = pd.concat(partes, ignore_index=True)
    ordenacao = [c for c in (*ID_COLS, cutoff_col, "horizonte_mes") if c in saida.columns]
    return saida.sort_values(ordenacao).reset_index(drop=True)


# ── Avaliação e seleção ─────────────────────────────────────────────


def scorecard_by_cutoff(
    frame: pd.DataFrame,
    forecasts: Mapping[str, str],
    actual_col: str = TARGET_COL,
) -> pd.DataFrame:
    """Erro somado por categoria × loja, corte a corte.

    É a tabela que responde à regra do relatório — manter uma mudança só se
    ela melhorar o erro somado ou o viés na maioria dos 12 meses de teste.

    Args:
        frame: Painel com o alvo e as colunas de previsão.
        forecasts: Rótulo da previsão → nome da coluna.
        actual_col: Coluna da venda real.

    Returns:
        Uma linha por corte × previsão, com wape e viés.
    """
    somado = frame.groupby(
        [CUTOFF_COL, "category_name", "sk_location"], as_index=False
    )[[actual_col, *forecasts.values()]].sum()
    return error_table(somado, forecasts, by=[CUTOFF_COL], actual_col=actual_col)


def wins_by_cutoff(
    por_corte: pd.DataFrame,
    candidato: str,
    referencia: str,
    metrica: str = "wape",
) -> int:
    """Em quantos cortes o candidato bate a referência.

    Args:
        por_corte: Saída de `scorecard_by_cutoff`.
        candidato: Rótulo da previsão avaliada.
        referencia: Rótulo da previsão de comparação.
        metrica: `wape` ou `vies` (no viés compara o valor absoluto).

    Returns:
        Número de cortes em que o candidato erra menos.
    """
    pivot = por_corte.pivot(index=CUTOFF_COL, columns="regua", values=metrica)
    esquerda, direita = pivot[candidato], pivot[referencia]
    if metrica == "vies":
        esquerda, direita = esquerda.abs(), direita.abs()
    return int((esquerda < direita).sum())


def select_power(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    base_config: GlmConfig,
    powers: Sequence[float] = (1.0, 1.1, 1.3, 1.5, 1.7, 1.9),
    alphas: Sequence[float] = (0.0, 1e-4, 1e-3, 1e-2, 1e-1),
) -> pd.DataFrame:
    """Varre potência e regularização, pontuando somente na validação.

    O conjunto de teste não é parâmetro desta função — é a garantia estrutural
    de que nenhum hiperparâmetro é escolhido olhando o teste.

    `power = 1.0` é tratado como Poisson. A comparação entre potências usa
    `erro_categoria_local` e `desvio_poisson`, nunca a desviância da própria
    família: potências diferentes vivem em escalas diferentes.

    Args:
        train: Linhas de treino.
        validation: Linhas de validação.
        base_config: Configuração de features a reaproveitar.
        powers: Potências do Tweedie a testar.
        alphas: Valores de regularização a testar.

    Returns:
        Uma linha por combinação, ordenada por erro_categoria_local.
    """
    linhas = []
    for power in powers:
        for alpha in alphas:
            familia = "poisson" if power == 1.0 else "tweedie"
            rotulo = f"{familia}_p{power:g}_a{alpha:g}"
            config = replace(
                base_config, name=rotulo, family=familia, power=power, alpha=alpha
            )
            modelo = fit_glm(train, config)
            marcado = add_predictions(validation, modelo, "pred_glm")
            placar = comparison_scorecard(marcado, {rotulo: "pred_glm"}).iloc[0]
            linhas.append(
                {
                    "familia": familia,
                    "power": power,
                    "alpha": alpha,
                    "erro_produto": placar["erro_produto"],
                    "erro_categoria_local": placar["erro_categoria_local"],
                    "erro_local": placar["erro_local"],
                    "vies": placar["vies"],
                    "erro_medio_unidades": placar["erro_medio_unidades"],
                    "raiz_erro_quadratico": placar["raiz_erro_quadratico"],
                    "desvio_poisson": placar["desvio_poisson"],
                    "dispersao_treino": round(modelo.dispersao_pearson, 3),
                }
            )
    tabela = pd.DataFrame(linhas)
    return tabela.sort_values("erro_categoria_local").reset_index(drop=True)


# ── Passos de features, na ordem prescrita pelo relatório ──────────

# Cada passo acrescenta um grupo de informação ao anterior. A regra de decisão
# é pré-registrada: só adotar um passo se ele melhorar o erro somado ou o
# viés na maioria dos 12 cortes de teste. Não confundir com as 4 macro-etapas
# do projeto (EDA → régua → engenharia de features → modelo de ML) — estes
# são os passos internos da modelagem, dentro da etapa 4.

_HISTORICO_LOG1P = (
    "sum_12m",
    "sum_3m",
    "produto_locais_avg_12m",
    "categoria_local_n_series",
    "produto_locais_n_locations",
)
_HISTORICO_NUM = (
    "months_with_sale_12m",
    "months_since_last_sale",
    "is_stopped_12m",
    "nunca_vendeu",
)

FEATURE_STEPS: dict[str, GlmConfig] = {
    # A régua é o caso beta=(1,1,1) deste modelo, com intercepto -log(12).
    # Sem offset, sem penalidade e sem escala, para que os coeficientes sejam
    # lidos diretamente como elasticidades e o empate seja verificável.
    "passo1_nested": GlmConfig(
        name="passo1_nested",
        family="poisson",
        alpha=0.0,
        use_offset=False,
        scale=False,
        log_features=("categoria_local_avg_12m", "season_sum_next_3m", "trend_factor"),
    ),
    # Só recalibra a régua por um fator multiplicativo global. Sem feature
    # alguma, a hessiana do newton-cholesky fica singular, então usa lbfgs; o
    # alpha mínimo identifica o coeficiente da coluna morta sem tocar no
    # intercepto, que é o único parâmetro que importa aqui.
    "passo2_offset": GlmConfig(
        name="passo2_offset",
        family="poisson",
        alpha=1e-8,
        use_offset=True,
        solver="lbfgs",
        max_iter=1000,
        tol=1e-12,
    ),
    "passo3_historico": GlmConfig(
        name="passo3_historico",
        family="poisson",
        use_offset=True,
        log1p_features=_HISTORICO_LOG1P,
        numeric_features=_HISTORICO_NUM,
    ),
    "passo4_categoricas_baratas": GlmConfig(
        name="passo4_categoricas_baratas",
        family="poisson",
        use_offset=True,
        log1p_features=_HISTORICO_LOG1P,
        numeric_features=_HISTORICO_NUM,
        categorical_features=("frequency_class", "location_type", "region"),
    ),
    "passo5_categoricas_caras": GlmConfig(
        name="passo5_categoricas_caras",
        family="poisson",
        use_offset=True,
        log1p_features=(*_HISTORICO_LOG1P, "sale_price"),
        numeric_features=_HISTORICO_NUM,
        categorical_features=(
            "frequency_class",
            "location_type",
            "region",
            "category_name",
            "brand_name",
        ),
    ),
}
