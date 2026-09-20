"""Leitura das features e gravação das previsões do GLM no Unity Catalog.

Única camada com Spark do modelo de demanda: `demand_glm.py` é pandas puro e
não sabe que o Databricks existe. Manter a fronteira aqui é o que permite
testar a modelagem offline.

As tabelas de previsão são particionadas por `model_name` e escritas com
`replaceWhere`, de modo que reexecutar um modelo substitui só as linhas dele e
os demais modelos do time (regressão linear, XGBoost) convivem na mesma tabela.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import (
    BooleanType,
    DateType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from src.analytics_ai.ml_config import MlModelConfig

# Schemas explícitos: inferir de um pandas.DataFrame troca date por timestamp e
# transforma uma coluna toda nula (o alvo, nas linhas de inferência) em void.
FORECAST_3M_SCHEMA = StructType(
    [
        StructField("model_name", StringType(), nullable=False),
        StructField("model_family", StringType(), nullable=False),
        StructField("model_power", DoubleType(), nullable=True),
        StructField("model_alpha", DoubleType(), nullable=True),
        StructField("split_name", StringType(), nullable=False),
        StructField("cutoff", DateType(), nullable=False),
        StructField("sk_product", StringType(), nullable=False),
        StructField("sku", StringType(), nullable=True),
        StructField("sk_location", StringType(), nullable=False),
        StructField("location_name", StringType(), nullable=True),
        StructField("category_name", StringType(), nullable=True),
        StructField("pred_total_3m", DoubleType(), nullable=False),
        StructField("baseline_pred_3m", DoubleType(), nullable=True),
        StructField("target_3m", DoubleType(), nullable=True),
        StructField("is_target_complete", BooleanType(), nullable=False),
        StructField("trained_at", TimestampType(), nullable=False),
    ]
)

FORECAST_MENSAL_SCHEMA = StructType(
    [
        StructField("model_name", StringType(), nullable=False),
        StructField("sk_product", StringType(), nullable=False),
        StructField("sku", StringType(), nullable=True),
        StructField("sk_location", StringType(), nullable=False),
        StructField("location_name", StringType(), nullable=True),
        StructField("cutoff", DateType(), nullable=False),
        StructField("mes_previsto", DateType(), nullable=False),
        StructField("horizonte_mes", IntegerType(), nullable=False),
        StructField("demanda_prevista", DoubleType(), nullable=False),
        StructField("demanda_prevista_3m", DoubleType(), nullable=False),
        StructField("share_sazonal", DoubleType(), nullable=False),
        StructField("generated_at", TimestampType(), nullable=False),
    ]
)


def read_features(spark: SparkSession, config: MlModelConfig | None = None) -> pd.DataFrame:
    """Lê a tabela de features inteira para pandas.

    São ~382 mil linhas por ~33 colunas: cabe com folga na memória do driver, e
    treinar em pandas evita reimplementar o GLM em Spark.

    Args:
        spark: Sessão Spark ativa.
        config: Configuração das tabelas; por padrão vem do ambiente.

    Returns:
        Painel de features como pandas.DataFrame.
    """
    config = config or MlModelConfig.from_environment()
    frame = spark.table(config.features_source).toPandas()
    # O Databricks Connect pendura métricas do plano em .attrs, e elas não são
    # serializáveis — quebram um to_parquet/to_pickle do quadro mais adiante.
    frame.attrs.clear()
    return frame


def _write(spark: SparkSession, frame: pd.DataFrame, schema: StructType, table: str, model_name: str) -> int:
    """Grava substituindo apenas as linhas do modelo informado."""
    colunas = [campo.name for campo in schema.fields]
    faltando = [c for c in colunas if c not in frame.columns]
    if faltando:
        raise ValueError(f"colunas ausentes para gravar em {table}: {faltando}")
    # `replaceWhere` monta o predicado em SQL: uma aspa no nome quebraria a instrução.
    if "'" in model_name:
        raise ValueError(f"model_name não pode conter aspas simples: {model_name!r}")
    if not (frame["model_name"] == model_name).all():
        raise ValueError(f"o quadro tem linhas de outro model_name além de '{model_name}'; nada foi gravado")
    # Um quadro vazio apagaria as linhas do modelo (replaceWhere) sem gravar nada no lugar.
    if frame.empty:
        raise ValueError(f"quadro vazio para '{model_name}' em {table}: gravar apagaria as linhas do modelo")

    sdf: DataFrame = spark.createDataFrame(frame[colunas], schema=schema)
    (
        sdf.write.format("delta")
        .mode("overwrite")
        .option("replaceWhere", f"model_name = '{model_name}'")
        .option("overwriteSchema", "true")
        .partitionBy("model_name")
        .saveAsTable(table)
    )
    return len(frame)


def write_forecast_3m(
    spark: SparkSession,
    frame: pd.DataFrame,
    model_name: str,
    config: MlModelConfig | None = None,
) -> int:
    """Grava a previsão do total de 3 meses por série × corte.

    Args:
        spark: Sessão Spark ativa.
        frame: Quadro já no formato de `FORECAST_3M_SCHEMA`.
        model_name: Rótulo do modelo; é a partição substituída.
        config: Configuração das tabelas; por padrão vem do ambiente.

    Returns:
        Quantidade de linhas gravadas.
    """
    config = config or MlModelConfig.from_environment()
    return _write(spark, frame, FORECAST_3M_SCHEMA, config.forecast_target, model_name)


def write_forecast_mensal(
    spark: SparkSession,
    frame: pd.DataFrame,
    model_name: str,
    config: MlModelConfig | None = None,
) -> int:
    """Grava a previsão mês a mês — o entregável de demanda dos 3 meses seguintes.

    Args:
        spark: Sessão Spark ativa.
        frame: Quadro já no formato de `FORECAST_MENSAL_SCHEMA`.
        model_name: Rótulo do modelo; é a partição substituída.
        config: Configuração das tabelas; por padrão vem do ambiente.

    Returns:
        Quantidade de linhas gravadas.
    """
    config = config or MlModelConfig.from_environment()
    return _write(spark, frame, FORECAST_MENSAL_SCHEMA, config.forecast_monthly_target, model_name)


def build_forecast_3m_frame(
    frame: pd.DataFrame,
    pred_col: str,
    model_name: str,
    family: str,
    power: float | None,
    alpha: float | None,
    split_name: str,
    trained_at: dt.datetime,
) -> pd.DataFrame:
    """Monta as colunas de `ml_forecast_demanda_3m` a partir do painel previsto.

    Args:
        frame: Painel com features, alvo e a coluna de previsão.
        pred_col: Coluna com o total previsto.
        model_name: Rótulo do modelo.
        family: `poisson` ou `tweedie`.
        power: Potência do Tweedie, ou None para Poisson.
        alpha: Regularização usada.
        split_name: `treino`, `validacao`, `teste` ou `inferencia`.
        trained_at: Momento do treino.

    Returns:
        Quadro pronto para `write_forecast_3m`.
    """
    saida = pd.DataFrame(
        {
            "model_name": model_name,
            "model_family": family,
            "model_power": power,
            "model_alpha": alpha,
            "split_name": split_name,
            "cutoff": frame["cutoff"],
            "sk_product": frame["sk_product"].astype(str),
            "sku": frame["sku"],
            "sk_location": frame["sk_location"].astype(str),
            "location_name": frame["location_name"],
            "category_name": frame["category_name"],
            "pred_total_3m": frame[pred_col].astype(float),
            "baseline_pred_3m": frame["baseline_pred_categoria_local_idx_trend"].astype(float),
            "target_3m": frame["target_3m"].astype(float),
            "is_target_complete": frame["is_target_complete"].astype(bool),
            "trained_at": trained_at,
        }
    )
    return saida.reset_index(drop=True)


def build_forecast_mensal_frame(
    mensal: pd.DataFrame,
    pred_col: str,
    model_name: str,
    generated_at: dt.datetime,
) -> pd.DataFrame:
    """Monta as colunas de `ml_forecast_demanda_mensal`.

    Args:
        mensal: Saída de `demand_glm.decompose_months`.
        pred_col: Coluna com o total previsto dos 3 meses.
        model_name: Rótulo do modelo.
        generated_at: Momento da geração.

    Returns:
        Quadro pronto para `write_forecast_mensal`.
    """
    saida = pd.DataFrame(
        {
            "model_name": model_name,
            "sk_product": mensal["sk_product"].astype(str),
            "sku": mensal["sku"],
            "sk_location": mensal["sk_location"].astype(str),
            "location_name": mensal["location_name"],
            "cutoff": mensal["cutoff"],
            "mes_previsto": mensal["mes_previsto"],
            "horizonte_mes": mensal["horizonte_mes"].astype("int32"),
            "demanda_prevista": mensal["demanda_prevista"].astype(float),
            "demanda_prevista_3m": mensal[pred_col].astype(float),
            "share_sazonal": mensal["share_sazonal"].astype(float),
            "generated_at": generated_at,
        }
    )
    return saida.reset_index(drop=True)
