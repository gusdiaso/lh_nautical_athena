"""Funcoes reutilizaveis para ingestao de dados."""

import os

from databricks.connect import DatabricksSession
from pyspark.sql import SparkSession


# ── Spark ──────────────────────────────────────────────


def build_spark_session():
    """Retorna uma sessao Spark do Databricks Runtime ou conexao externa."""
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
    """Retorna dbutils do Databricks para acesso a segredos."""
    from databricks.sdk.runtime import dbutils as runtime_dbutils

    return runtime_dbutils


# ── Delta Lake ─────────────────────────────────────────


def save_full(spark, df, table_name):
    """Salva o DataFrame sobrescrevendo a tabela inteira (full)."""
    (
        df.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(table_name)
    )


def save_append(spark, df, table_name):
    """Acrescenta novas linhas a tabela existente (append)."""
    df.write.format("delta").mode("append").saveAsTable(table_name)


# ── Schema ─────────────────────────────────────────────


def create_schema(spark, catalog, schema):
    """Cria o schema se ele nao existir."""
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")


def table_exists(spark, table_name):
    """Verifica se a tabela existe no catalogo."""
    return spark.catalog.tableExists(table_name)
