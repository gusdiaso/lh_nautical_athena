"""Extrai as tabelas do SQL Server lh_nautical para a camada Bronze no Databricks."""

import argparse
import os
import traceback

from databricks.connect import DatabricksSession
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

TABLES = [
    "order_items",
    "payments",
    "fiscal_invoices",
    "purchase_orders",
    "purchase_order_items",
    "customers",
    "goods_receipts",
    "suppliers",
    "goods_receipt_items",
    "locations",
    "returns",
    "employees",
    "addresses",
    "return_items",
    "categories",
    "brands",
    "products",
    "product_variants",
    "attributes",
    "variant_attribute_values",
    "product_suppliers",
    "stock_levels",
    "stock_movements",
    "orders",
]

JDBC_URL = "jdbc:sqlserver://18.209.218.63:4563;databaseName=lh_nautical;encrypt=true;trustServerCertificate=true;"
SECRET_SCOPE = "lh_nautical"
SECRET_KEY = "secret_lh_nautical_bd"
SOURCE_SCHEMA = "dbo"


def parse_args():
    """Lê os argumentos de linha de comando usados pelo job do Databricks."""
    parser = argparse.ArgumentParser(description="Extrai tabelas para Bronze.")
    parser.add_argument(
        "--table",
        help="Processa apenas uma tabela da lista de origem.",
    )
    parser.add_argument(
        "--catalog",
        default=os.getenv("DATABRICKS_CATALOG", "dev_lh_nautical"),
    )
    parser.add_argument(
        "--schema",
        default=os.getenv("DATABRICKS_BRONZE_SCHEMA", "bronze"),
    )
    return parser.parse_args()


def build_spark_session():
    """Retorna uma sessão Spark do Databricks Runtime ou de uma conexão externa."""
    if os.getenv("DATABRICKS_RUNTIME_VERSION"):
        return SparkSession.builder.getOrCreate()

    profile = os.getenv("DATABRICKS_PROFILE", "lh_nautical_developers")
    cluster_id = os.getenv("DATABRICKS_CLUSTER_ID")
    use_serverless = os.getenv("DATABRICKS_USE_SERVERLESS", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    builder = DatabricksSession.builder.profile(profile)

    if cluster_id:
        builder = builder.clusterId(cluster_id)
    elif use_serverless:
        builder = builder.serverless()
    else:
        raise ValueError(
            "Set DATABRICKS_CLUSTER_ID or enable DATABRICKS_USE_SERVERLESS"
        )

    return builder.getOrCreate()


def get_dbutils():
    """Retorna dbutils do Databricks para acesso a segredos e utilitários."""
    from databricks.sdk.runtime import dbutils as runtime_dbutils

    return runtime_dbutils


def select_tables(table_name):
    """Retorna uma única tabela ou a lista completa de tabelas de origem."""
    if table_name:
        if table_name not in TABLES:
            raise ValueError(f"Tabela inválida: {table_name}")
        return [table_name]
    return TABLES


def extract_table(
    spark_session,
    source_table_name,
    jdbc_url,
    jdbc_password,
    target_catalog,
    target_schema,
):
    """Lê uma tabela do SQL Server via JDBC e grava como tabela Delta."""
    df = (
        spark_session.read.format("jdbc")
        .option("url", jdbc_url)
        .option("dbtable", f"{SOURCE_SCHEMA}.{source_table_name}")
        .option("user", "student")
        .option("password", jdbc_password)
        .option("driver", "com.microsoft.sqlserver.jdbc.SQLServerDriver")
        .load()
    )

    (
        df.withColumn("_ingested_at", F.current_timestamp())
        .withColumn(
            "_source_path",
            F.lit(f"sqlserver://{SOURCE_SCHEMA}.{source_table_name}"),
        )
        .write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(f"{target_catalog}.{target_schema}.{source_table_name}")
    )

    print(f"✅ Tabela {source_table_name} salva com sucesso na camada Bronze!")


def create_target_schema(spark_session, target_catalog, target_schema):
    """Cria o schema de destino caso ele ainda não exista."""
    spark_session.sql(f"CREATE SCHEMA IF NOT EXISTS {target_catalog}.{target_schema}")


def load_jdbc_password(dbutils):
    """Carrega a senha do SQL Server a partir dos segredos do Databricks."""
    return dbutils.secrets.get(scope=SECRET_SCOPE, key=SECRET_KEY)


def run_table_extraction(
    spark_session,
    table_names,
    jdbc_password,
    target_catalog,
    target_schema,
):
    """Processa cada tabela sequencialmente e coleta os detalhes das falhas."""
    failed_tables = []

    for table_name in table_names:
        try:
            extract_table(
                spark_session,
                table_name,
                JDBC_URL,
                jdbc_password,
                target_catalog,
                target_schema,
            )
        except Exception as exc:
            print(f"❌ ERRO ao processar a tabela {table_name}:")
            print(traceback.format_exc())
            failed_tables.append({"tabela": table_name, "erro": str(exc)})

    return failed_tables


def main():
    """Orquestra o fluxo de extração para todas as tabelas selecionadas."""
    args = parse_args()
    target_catalog = args.catalog
    target_schema = args.schema

    spark_session = build_spark_session()
    dbutils = get_dbutils()
    jdbc_password = load_jdbc_password(dbutils)

    create_target_schema(spark_session, target_catalog, target_schema)
    selected_tables = select_tables(args.table)
    failed_tables = run_table_extraction(
        spark_session,
        selected_tables,
        jdbc_password,
        target_catalog,
        target_schema,
    )

    if failed_tables:
        print(f"⚠️ Alerta: {len(failed_tables)} tabelas falharam!")
        for item in failed_tables:
            print(f"   -> Falha na tabela: {item['tabela']}")

    if failed_tables:
        raise RuntimeError(
            f"O pipeline concluiu com erros em {len(failed_tables)} tabelas."
        )


if __name__ == "__main__":
    main()
