"""Funções reutilizáveis para ingestão de dados."""

import os
from typing import Optional

from databricks.connect import DatabricksSession
from pyspark.sql import DataFrame, SparkSession

# ── Spark ───────────────────────────────────────────────────────────


def build_spark_session() -> SparkSession:
    """Retorna uma sessão Spark do Databricks Runtime ou conexão externa.

    Returns:
        Instância SparkSession configurada para o ambiente atual.
    """
    if os.getenv("DATABRICKS_RUNTIME_VERSION"):
        return SparkSession.builder.getOrCreate()

    profile = os.getenv("DATABRICKS_PROFILE", "lh_nautical_developers")
    builder = DatabricksSession.builder.profile(profile)

    cluster_id = os.getenv("DATABRICKS_CLUSTER_ID")
    if cluster_id:
        builder = builder.clusterId(cluster_id)
    else:
        builder = builder.serverless()

    return builder.getOrCreate()


def get_dbutils():
    """Retorna dbutils do Databricks para acesso a segredos.

    Returns:
        Instância dbutils do Databricks runtime.
    """
    from databricks.sdk.runtime import dbutils as runtime_dbutils

    return runtime_dbutils


# ── Delta Lake ──────────────────────────────────────────────────────


def save_full(spark: SparkSession, df: DataFrame, table_name: str) -> None:
    """Salva o DataFrame sobrescrevendo a tabela inteira (carga full).

    Args:
        spark: SparkSession ativa.
        df: DataFrame a ser salvo.
        table_name: Nome completo da tabela (catalog.schema.table).
    """
    (
        df.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(table_name)
    )


def save_append(spark: SparkSession, df: DataFrame, table_name: str) -> None:
    """Acrescenta novas linhas à tabela existente (append).

    Args:
        spark: SparkSession ativa.
        df: DataFrame a ser acrescentado.
        table_name: Nome completo da tabela (catalog.schema.table).
    """
    df.write.format("delta").mode("append").saveAsTable(table_name)


# ── Schema ──────────────────────────────────────────────────────────


def create_schema(spark: SparkSession, catalog: str, schema: str) -> None:
    """Cria o schema se ele não existir.

    Args:
        spark: SparkSession ativa.
        catalog: Nome do catálogo de destino.
        schema: Nome do schema a ser criado.
    """
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")


def table_exists(spark: SparkSession, table_name: str) -> bool:
    """Verifica se a tabela existe no catálogo.

    Args:
        spark: SparkSession ativa.
        table_name: Nome completo da tabela.

    Returns:
        True se a tabela existir, False caso contrário.
    """
    return spark.catalog.tableExists(table_name)
