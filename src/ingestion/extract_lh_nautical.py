import os
import traceback
import argparse

from databricks.connect import DatabricksSession
from pyspark.sql import functions as F
from pyspark.sql import SparkSession

# 24 tabelas do SQL Server que serão extraídas para a camada Bronze
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

# Conexão JDBC com o SQL Server de origem (ERP lh_nautical)
JDBC_URL = "jdbc:sqlserver://18.209.218.63:4563;databaseName=lh_nautical;encrypt=true;trustServerCertificate=true;"


def parse_args():
    """Lê argumentos da CLI passados pelo .yml do job: --table(opcional), --catalog e --schema."""
    parser = argparse.ArgumentParser(description="Extract tables into Bronze")
    parser.add_argument("--table", help="Process only one table from the source list")
    parser.add_argument(
        "--catalog", default=os.getenv("DATABRICKS_CATALOG", "dev_lh_nautical")
    )
    parser.add_argument(
        "--schema", default=os.getenv("DATABRICKS_BRONZE_SCHEMA", "bronze")
    )
    return parser.parse_args()


def build_spark_session():
    """Retorna uma SparkSession — dentro do Databricks Runtime ou via DatabricksSession externo."""
    # Dentro do Databricks Runtime, usa a sessão Spark existente
    if os.getenv("DATABRICKS_RUNTIME_VERSION"):
        return SparkSession.builder.getOrCreate()

    # Fora do Databricks (ex: dev local), conecta via DatabricksSession
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
    """Retorna o objeto dbutils do Databricks para acesso a secrets e utilitários."""
    from databricks.sdk.runtime import dbutils as runtime_dbutils

    return runtime_dbutils


def select_tables(table_name):
    """Retorna lista com a tabela específica ou todas as 24 se --table não foi passado."""
    if table_name:
        if table_name not in TABLES:
            raise ValueError(f"Tabela inválida: {table_name}")
        return [table_name]
    return TABLES


def extract_table(spark, tabela, jdbc_url, senha, catalog, bronze_schema):
    """Lê uma tabela do SQL Server via JDBC e salva como Delta na camada Bronze."""
    # Leitura full da tabela no SQL Server via JDBC
    df = (
        spark.read.format("jdbc")
        .option("url", jdbc_url)
        .option("dbtable", f"dbo.{tabela}")
        .option("user", "student")
        .option("password", senha)
        .option("driver", "com.microsoft.sqlserver.jdbc.SQLServerDriver")
        .load()
    )

    # Adiciona metadados de ingestão e salva como tabela Delta na Bronze
    (
        df.withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_path", F.lit(f"sqlserver://dbo.{tabela}"))
        .write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(f"{catalog}.{bronze_schema}.{tabela}")
    )

    print(f"✅ Tabela {tabela} salva com sucesso na camada Bronze!")


def main():
    """Orquestra a extração: inicializa Spark, descobre tabelas e executa extract_table para cada uma."""
    args = parse_args()
    catalog = args.catalog
    bronze_schema = args.schema

    # Inicializa sessão Spark e obtém secrets do Databricks
    spark = build_spark_session()
    dbutils = get_dbutils()
    senha = dbutils.secrets.get(scope="lh_nautical", key="secret_lh_nautical_bd")

    # Garante que o schema de destino existe no Unity Catalog
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{bronze_schema}")

    tabelas = select_tables(args.table)
    tabelas_sucesso = []
    tabelas_erro = []

    # Processa cada tabela sequencialmente, registrando sucessos e erros
    for tabela in tabelas:
        try:
            extract_table(spark, tabela, JDBC_URL, senha, catalog, bronze_schema)
            tabelas_sucesso.append(tabela)
        except Exception as e:
            print(f"❌ ERRO ao processar a tabela {tabela}:")
            print(traceback.format_exc())
            tabelas_erro.append({"tabela": tabela, "erro": str(e)})

    # Resumo final: falha parcial não interrompe as demais tabelas
    if tabelas_erro:
        print(f"⚠️ Alerta: {len(tabelas_erro)} tabelas falharam!")
        for item in tabelas_erro:
            print(f"   -> Falha na tabela: {item['tabela']}")

    # Só levanta exceção no final, após todas as tentativas
    if tabelas_erro:
        raise RuntimeError(
            f"O pipeline concluiu com erros em {len(tabelas_erro)} tabelas."
        )


if __name__ == "__main__":
    main()
