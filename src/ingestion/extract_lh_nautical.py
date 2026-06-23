import os
import traceback
import argparse

from databricks.connect import DatabricksSession
from pyspark.sql import functions as F
from pyspark.sql import SparkSession

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


def parse_args():
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
    from databricks.sdk.runtime import dbutils as runtime_dbutils

    return runtime_dbutils


def select_tables(table_name):
    if table_name:
        if table_name not in TABLES:
            raise ValueError(f"Tabela inválida: {table_name}")
        return [table_name]

    return TABLES


args = parse_args()
profile = os.getenv("DATABRICKS_PROFILE", "lh_nautical_developers")
cluster_id = os.getenv("DATABRICKS_CLUSTER_ID")
use_serverless = os.getenv("DATABRICKS_USE_SERVERLESS", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

catalog = args.catalog
bronze_schema = args.schema

spark = build_spark_session()
dbutils = get_dbutils()

senha = dbutils.secrets.get(scope="lh_nautical", key="secret_lh_nautical_bd")

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{bronze_schema}")

jdbc_url = "jdbc:sqlserver://18.209.218.63:4563;databaseName=lh_nautical;encrypt=true;trustServerCertificate=true;"

tabelas = select_tables(args.table)

tabelas_sucesso = []
tabelas_erro = []

for tabela in tabelas:
    try:
        print(f"🔄 Iniciando extração da tabela: dbo.{tabela}")

        df = (
            spark.read.format("jdbc")
            .option("url", jdbc_url)
            .option("dbtable", f"dbo.{tabela}")
            .option("user", "student")
            .option("password", senha)
            .option("driver", "com.microsoft.sqlserver.jdbc.SQLServerDriver")
            .load()
        )

        df_bronze = df.withColumn("_ingested_at", F.current_timestamp()).withColumn(
            "_source_path", F.lit(f"sqlserver://dbo.{tabela}")
        )

        df_bronze.write.format("delta").mode("overwrite").option(
            "overwriteSchema", "true"
        ).saveAsTable(f"{catalog}.{bronze_schema}.{tabela}")

        print(f"✅ Tabela {tabela} salva com sucesso na camada Bronze!")
        tabelas_sucesso.append(tabela)

    except Exception as e:
        print(f"❌ ERRO ao processar a tabela {tabela}:")
        print(traceback.format_exc())
        tabelas_erro.append({"tabela": tabela, "erro": str(e)})

print("\n" + "=" * 40)
print("📊 RESUMO DA EXECUÇÃO DO PIPELINE")
print(
    f"Total de tabelas processadas com sucesso: {len(tabelas_sucesso)}/{len(tabelas)}"
)
if tabelas_erro:
    print(f"⚠️ Alerta: {len(tabelas_erro)} tabelas falharam!")
    for item in tabelas_erro:
        print(f"   -> Falha na tabela: {item['tabela']}")
print("=" * 40)

if len(tabelas_erro) > 0:
    raise RuntimeError(f"O pipeline concluiu com erros em {len(tabelas_erro)} tabelas.")


#############################################################################################
#### ADD FUNÇÃO DE EXTRAIR TABELA E CRIA A FUNÇÃO MAIN PARA SER EXECUTADA, O QUE ACHAM? #####
#############################################################################################


# import os
# import traceback
# import argparse

# from databricks.connect import DatabricksSession
# from pyspark.sql import functions as F
# from pyspark.sql import SparkSession

# TABLES = [
#     "order_items", "payments", "fiscal_invoices", "purchase_orders",
#     "purchase_order_items", "customers", "goods_receipts", "suppliers",
#     "goods_receipt_items", "locations", "returns", "employees", "addresses",
#     "return_items", "categories", "brands", "products", "product_variants",
#     "attributes", "variant_attribute_values", "product_suppliers",
#     "stock_levels", "stock_movements", "orders",
# ]

# JDBC_URL = "jdbc:sqlserver://18.209.218.63:4563;databaseName=lh_nautical;encrypt=true;trustServerCertificate=true;"


# def parse_args():
#     parser = argparse.ArgumentParser(description="Extract tables into Bronze")
#     parser.add_argument("--table", help="Process only one table from the source list")
#     parser.add_argument("--catalog", default=os.getenv("DATABRICKS_CATALOG", "dev_lh_nautical"))
#     parser.add_argument("--schema", default=os.getenv("DATABRICKS_BRONZE_SCHEMA", "bronze"))
#     return parser.parse_args()


# def build_spark_session():
#     if os.getenv("DATABRICKS_RUNTIME_VERSION"):
#         return SparkSession.builder.getOrCreate()

#     profile = os.getenv("DATABRICKS_PROFILE", "lh_nautical_developers")
#     cluster_id = os.getenv("DATABRICKS_CLUSTER_ID")
#     use_serverless = os.getenv("DATABRICKS_USE_SERVERLESS", "true").lower() in {"1", "true", "yes", "on"}

#     builder = DatabricksSession.builder.profile(profile)

#     if cluster_id:
#         builder = builder.clusterId(cluster_id)
#     elif use_serverless:
#         builder = builder.serverless()
#     else:
#         raise ValueError("Set DATABRICKS_CLUSTER_ID or enable DATABRICKS_USE_SERVERLESS")

#     return builder.getOrCreate()


# def get_dbutils():
#     from databricks.sdk.runtime import dbutils as runtime_dbutils
#     return runtime_dbutils


# def select_tables(table_name):
#     if table_name:
#         if table_name not in TABLES:
#             raise ValueError(f"Tabela inválida: {table_name}")
#         return [table_name]
#     return TABLES


# def extract_table(spark, tabela, jdbc_url, senha, catalog, bronze_schema):
#     print(f"🔄 Iniciando extração da tabela: dbo.{tabela}")

#     df = (
#         spark.read.format("jdbc")
#         .option("url", jdbc_url)
#         .option("dbtable", f"dbo.{tabela}")
#         .option("user", "student")
#         .option("password", senha)
#         .option("driver", "com.microsoft.sqlserver.jdbc.SQLServerDriver")
#         .load()
#     )

#     (
#         df.withColumn("_ingested_at", F.current_timestamp())
#           .withColumn("_source_path", F.lit(f"sqlserver://dbo.{tabela}"))
#           .write.format("delta")
#           .mode("overwrite")
#           .option("overwriteSchema", "true")
#           .saveAsTable(f"{catalog}.{bronze_schema}.{tabela}")
#     )

#     print(f"✅ Tabela {tabela} salva com sucesso na camada Bronze!")


# def main():
#     args = parse_args()
#     catalog = args.catalog
#     bronze_schema = args.schema

#     spark = build_spark_session()
#     dbutils = get_dbutils()
#     senha = dbutils.secrets.get(scope="lh_nautical", key="secret_lh_nautical_bd")

#     spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{bronze_schema}")

#     tabelas = select_tables(args.table)
#     tabelas_sucesso = []
#     tabelas_erro = []

#     for tabela in tabelas:
#         try:
#             extract_table(spark, tabela, JDBC_URL, senha, catalog, bronze_schema)
#             tabelas_sucesso.append(tabela)
#         except Exception as e:
#             print(f"❌ ERRO ao processar a tabela {tabela}:")
#             print(traceback.format_exc())
#             tabelas_erro.append({"tabela": tabela, "erro": str(e)})

#     print("\n" + "=" * 40)
#     print("📊 RESUMO DA EXECUÇÃO DO PIPELINE")
#     print(f"Total de tabelas processadas com sucesso: {len(tabelas_sucesso)}/{len(tabelas)}")
#     if tabelas_erro:
#         print(f"⚠️ Alerta: {len(tabelas_erro)} tabelas falharam!")
#         for item in tabelas_erro:
#             print(f"   -> Falha na tabela: {item['tabela']}")
#     print("=" * 40)

#     if tabelas_erro:
#         raise RuntimeError(f"O pipeline concluiu com erros em {len(tabelas_erro)} tabelas.")


# if __name__ == "__main__":
#     main()
