"""Extrai tabelas do SQL Server para a camada Bronze (modo full)."""

import argparse
import traceback

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from pyspark.sql import functions as F

from config import (
    JDBC_URL,
    SECRET_SCOPE,
    SECRET_KEY,
    SOURCE_SCHEMA,
    DEFAULT_CATALOG,
    DEFAULT_SCHEMA,
    TABLES,
)
from utils import (
    build_spark_session,
    get_dbutils,
    save_full,
    create_schema,
)


def parse_args():
    """Le os argumentos de linha de comando."""
    import os

    parser = argparse.ArgumentParser(description="Extrai tabelas para Bronze (full).")
    parser.add_argument("--table", help="Processa apenas uma tabela.")
    parser.add_argument(
        "--catalog",
        default=os.getenv("DATABRICKS_CATALOG", DEFAULT_CATALOG),
    )
    parser.add_argument(
        "--schema",
        default=os.getenv("DATABRICKS_BRONZE_SCHEMA", DEFAULT_SCHEMA),
    )
    return parser.parse_args()


def select_tables(table_name):
    """Retorna uma unica tabela ou a lista completa."""
    if table_name:
        if table_name not in TABLES:
            raise ValueError(f"Tabela invalida: {table_name}")
        return [table_name]
    return TABLES


# ── Leitura ──────────────────────────────────────────────


def read_source_data(spark, jdbc_password, table_name):
    """Le todos os dados de uma tabela do SQL Server via JDBC."""
    return (
        spark.read.format("jdbc")
        .option("url", JDBC_URL)
        .option("dbtable", f"{SOURCE_SCHEMA}.{table_name}")
        .option("user", "student")
        .option("password", jdbc_password)
        .option("driver", "com.microsoft.sqlserver.jdbc.SQLServerDriver")
        .load()
    )


# ── Orquestracao ─────────────────────────────────────────


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    before_sleep=lambda rs: print(
        f"⏳ Tentativa {rs.attempt_number}/3 falhou, retrying in {rs.next_action.sleep}s..."
    ),
)
def extract_table(spark, table_name, jdbc_password, catalog, schema):
    """Extrai uma tabela do SQL Server para Bronze."""
    target = f"{catalog}.{schema}.{table_name}"

    df = read_source_data(spark, jdbc_password, table_name)

    df = df.withColumn("_ingested_at", F.current_timestamp())
    df = df.withColumn(
        "_source_path", F.lit(f"sqlserver://{SOURCE_SCHEMA}.{table_name}")
    )

    save_full(spark, df, target)

    print(f"✅ Tabela {table_name} salva com sucesso!")


def run_extraction(spark, table_names, jdbc_password, catalog, schema):
    """Processa cada tabela e coleta erros."""
    failed = []

    for table_name in table_names:
        try:
            extract_table(spark, table_name, jdbc_password, catalog, schema)
        except Exception as exc:
            print(f"❌ ERRO ao processar {table_name}:")
            print(traceback.format_exc())
            failed.append({"tabela": table_name, "erro": str(exc)})

    return failed


# ── Entry point ──────────────────────────────────────────


def main():
    """Orquestra o fluxo de extracao."""
    args = parse_args()

    spark = build_spark_session()
    dbutils = get_dbutils()
    jdbc_password = dbutils.secrets.get(scope=SECRET_SCOPE, key=SECRET_KEY)

    create_schema(spark, args.catalog, args.schema)

    table_names = select_tables(args.table)
    failed = run_extraction(
        spark, table_names, jdbc_password, args.catalog, args.schema
    )

    if failed:
        raise RuntimeError(f"Pipeline concluido com erros em {len(failed)} tabelas.")


if __name__ == "__main__":
    main()
