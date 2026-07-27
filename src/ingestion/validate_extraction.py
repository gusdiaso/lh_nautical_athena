import argparse
import os
import sys

_ingestion_dir = os.path.join(os.getcwd(), "src", "ingestion")
if _ingestion_dir not in sys.path:
    sys.path.insert(0, _ingestion_dir)

from config import TABLES, DEFAULT_CATALOG, DEFAULT_SCHEMA
from utils import build_spark_session, table_exists

from pyspark.sql import SparkSession


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    return parser.parse_args()


def validate_table(
    spark: SparkSession, catalog: str, schema: str, table: str
) -> int:
    full_name = f"{catalog}.{schema}.{table}"
    if not table_exists(spark, full_name):
        print(f"FAIL  {full_name} — table not found")
        return 1

    count = spark.table(full_name).count()
    if count == 0:
        print(f"FAIL  {full_name} — table is empty")
        return 1

    print(f"OK    {full_name} — {count:,} rows")
    return 0


def main() -> None:
    args = parse_args()
    spark = build_spark_session()

    tables = TABLES + ["exchange_rates"]
    errors = 0

    print(f"Validating {args.catalog}.{args.schema}...\n")

    for table in tables:
        errors += validate_table(spark, args.catalog, args.schema, table)

    print(f"\n{len(tables) - errors}/{len(tables)} tables OK")

    if errors:
        print(f"FAILED — {errors} table(s) with issues")
        sys.exit(1)

    print("All tables validated successfully")


if __name__ == "__main__":
    main()
