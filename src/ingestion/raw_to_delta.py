import os
import traceback

from databricks.connect import DatabricksSession
from pyspark.sql import functions as F

profile = os.getenv("DATABRICKS_PROFILE", "lh-nautical-dev")
cluster_id = os.getenv("DATABRICKS_CLUSTER_ID")
use_serverless = os.getenv("DATABRICKS_USE_SERVERLESS", "true").lower() in {"1", "true", "yes", "on"}

catalog = os.getenv("DATABRICKS_CATALOG", "workspace")
bronze_schema = os.getenv("DATABRICKS_BRONZE_SCHEMA", "bronze")
silver_schema = os.getenv("DATABRICKS_SILVER_SCHEMA", "silver")

builder = DatabricksSession.builder.profile(profile)

if cluster_id:
    builder = builder.clusterId(cluster_id)
elif use_serverless:
    builder = builder.serverless()
else:
    raise ValueError("Set DATABRICKS_CLUSTER_ID or enable DATABRICKS_USE_SERVERLESS")

spark = builder.getOrCreate()

tabelas = [
    "order_items", "payments", "fiscal_invoices", "purchase_orders",
    "purchase_order_items", "customers", "goods_receipts", "suppliers",
    "goods_receipt_items", "locations", "returns", "employees",
    "addresses", "return_items", "categories", "brands", "products",
    "product_variants", "attributes", "variant_attribute_values",
    "product_suppliers", "stock_levels", "stock_movements", "orders"
]

try:
    bronze_count = spark.sql(f"SHOW TABLES IN {catalog}.{bronze_schema}").count()
except Exception as exc:
    raise RuntimeError(
        f"A camada de origem {catalog}.{bronze_schema} não existe ou ainda não foi criada. "
        f"Rode primeiro o ch2_extract_raw.py para materializar a bronze."
    ) from exc

if bronze_count == 0:
    raise RuntimeError(
        f"A camada de origem {catalog}.{bronze_schema} existe, mas está vazia. "
        f"Rode primeiro o ch2_extract_raw.py para carregar as tabelas bronze."
    )

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{silver_schema}")

tabelas_sucesso = []
tabelas_erro = []

for tabela in tabelas:
    try:
        print(f"Transformando {catalog}.{bronze_schema}.{tabela} para Delta em {catalog}.{silver_schema}.{tabela}")

        df = spark.read.table(f"{catalog}.{bronze_schema}.{tabela}")

        df_delta = df.withColumn("_transformed_at", F.current_timestamp())

        df_delta.write \
            .format("delta") \
            .mode("overwrite") \
            .option("overwriteSchema", "true") \
            .saveAsTable(f"{catalog}.{silver_schema}.{tabela}")

        print(f"OK: {tabela}")
        tabelas_sucesso.append(tabela)

    except Exception as e:
        print(f"ERRO em {tabela}")
        print(traceback.format_exc())
        tabelas_erro.append({"tabela": tabela, "erro": str(e)})

print("\nRESUMO")
print(f"Sucesso: {len(tabelas_sucesso)}/{len(tabelas)}")

if tabelas_erro:
    print(f"Falhas: {len(tabelas_erro)}")
    for item in tabelas_erro:
        print(f" - {item['tabela']}")

if tabelas_erro:
    raise RuntimeError(f"Pipeline concluiu com erros em {len(tabelas_erro)} tabelas.")