import argparse
from pyspark.sql import SparkSession

parser = argparse.ArgumentParser()
parser.add_argument("--catalog", default="dev_lh_nautical")
args = parser.parse_args()

spark = SparkSession.builder.getOrCreate()
catalog = args.catalog

mask_tables = {
    "customers": ["tax_id", "email", "phone"],
    "employees": ["cpf", "email"],
    "suppliers": ["tax_id", "email", "phone"],
}

mask_funcs = {
    "tax_id": "mask_full",
    "email": "mask_email",
    "phone": "mask_phone",
    "cpf": "mask_cpf",
}

for table, columns in mask_tables.items():
    for col in columns:
        stmt = f"ALTER TABLE {catalog}.bronze.{table} ALTER COLUMN {col} SET MASK {catalog}.gold.{mask_funcs[col]}"
        print(f"Executing: {stmt}")
        spark.sql(stmt)
        print("  Done.")
