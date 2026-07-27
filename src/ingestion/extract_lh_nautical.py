"""Extrai tabelas do SQL Server para a camada Bronze em modo full.

As tabelas operacionais são extraídas apenas até a data atual.
Registros futuros passam a ser ingeridos automaticamente quando suas
datas forem alcançadas em execuções posteriores do pipeline.
"""

import argparse
import traceback
from typing import List

from pyspark.sql import SparkSession, functions as F
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

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


def parse_args() -> argparse.Namespace:
    """Lê os argumentos de linha de comando.

    Returns:
        Namespace com os argumentos parseados.
    """
    import os

    parser = argparse.ArgumentParser(
        description="Extrai tabelas para Bronze em modo full."
    )
    parser.add_argument(
        "--table",
        help="Processa apenas uma tabela.",
    )
    parser.add_argument(
        "--catalog",
        default=os.getenv(
            "DATABRICKS_CATALOG",
            DEFAULT_CATALOG,
        ),
    )
    parser.add_argument(
        "--schema",
        default=os.getenv(
            "DATABRICKS_BRONZE_SCHEMA",
            DEFAULT_SCHEMA,
        ),
    )

    return parser.parse_args()


def select_tables(table_name: str) -> List[str]:
    """Retorna uma única tabela ou a lista completa.

    Args:
        table_name: Nome de uma tabela específica, ou None para todas.

    Returns:
        Lista de nomes de tabelas a serem processadas.

    Raises:
        ValueError: Se table_name não estiver na lista TABLES.
    """
    if table_name:
        if table_name not in TABLES:
            raise ValueError(f"Tabela inválida: {table_name}")

        return [table_name]

    return TABLES


# ── Consultas de origem ──────────────────────────────────────────────


def normalize_query(query: str) -> str:
    """Remove quebras e espaços excedentes de uma consulta SQL.

    Args:
        query: Consulta SQL original.

    Returns:
        Consulta SQL normalizada em uma única linha.
    """
    return " ".join(query.split())


def build_source_query(table_name: str) -> str:
    """Monta a origem JDBC aplicando o corte temporal necessário.

    Tabelas de eventos são limitadas à data atual do SQL Server.
    Tabelas filhas são filtradas pelos respectivos registros-pai.
    Tabelas cadastrais continuam sendo extraídas integralmente.

    Args:
        table_name: Nome da tabela de origem.

    Returns:
        Nome da tabela ou subconsulta SQL usada pela leitura JDBC.
    """
    current_date_sql = "cast(getdate() as date)"

    source_queries = {
        "orders": f"""
            select
                o.*
            from {SOURCE_SCHEMA}.orders as o
            where cast(o.placed_at as date) <= {current_date_sql}
        """,
        "order_items": f"""
            select
                oi.*
            from {SOURCE_SCHEMA}.order_items as oi
            where exists (
                select 1
                from {SOURCE_SCHEMA}.orders as o
                where o.id = oi.order_id
                    and cast(o.placed_at as date) <= {current_date_sql}
            )
        """,
        "payments": f"""
            select
                p.*
            from {SOURCE_SCHEMA}.payments as p
            where exists (
                select 1
                from {SOURCE_SCHEMA}.orders as o
                where o.id = p.order_id
                    and cast(o.placed_at as date) <= {current_date_sql}
            )
                and (
                    p.paid_at is null
                    or cast(p.paid_at as date) <= {current_date_sql}
                )
        """,
        "fiscal_invoices": f"""
            select
                fi.*
            from {SOURCE_SCHEMA}.fiscal_invoices as fi
            where cast(fi.issued_at as date) <= {current_date_sql}
                and exists (
                    select 1
                    from {SOURCE_SCHEMA}.orders as o
                    where o.id = fi.order_id
                        and cast(o.placed_at as date) <= {current_date_sql}
                )
        """,
        "returns": f"""
            select
                r.*
            from {SOURCE_SCHEMA}.returns as r
            where cast(r.created_at as date) <= {current_date_sql}
                and exists (
                    select 1
                    from {SOURCE_SCHEMA}.orders as o
                    where o.id = r.order_id
                        and cast(o.placed_at as date) <= {current_date_sql}
                )
        """,
        "return_items": f"""
            select
                ri.*
            from {SOURCE_SCHEMA}.return_items as ri
            where exists (
                select 1
                from {SOURCE_SCHEMA}.returns as r
                inner join {SOURCE_SCHEMA}.orders as o
                    on o.id = r.order_id
                inner join {SOURCE_SCHEMA}.order_items as oi
                    on oi.id = ri.order_item_id
                    and oi.order_id = o.id
                where r.id = ri.return_id
                    and cast(r.created_at as date) <= {current_date_sql}
                    and cast(o.placed_at as date) <= {current_date_sql}
            )
        """,
        "purchase_orders": f"""
            select
                po.*
            from {SOURCE_SCHEMA}.purchase_orders as po
            where cast(po.placed_at as date) <= {current_date_sql}
        """,
        "purchase_order_items": f"""
            select
                poi.*
            from {SOURCE_SCHEMA}.purchase_order_items as poi
            where exists (
                select 1
                from {SOURCE_SCHEMA}.purchase_orders as po
                where po.id = poi.purchase_order_id
                    and cast(po.placed_at as date) <= {current_date_sql}
            )
        """,
        "goods_receipts": f"""
            select
                gr.*
            from {SOURCE_SCHEMA}.goods_receipts as gr
            where cast(gr.received_at as date) <= {current_date_sql}
                and exists (
                    select 1
                    from {SOURCE_SCHEMA}.purchase_orders as po
                    where po.id = gr.purchase_order_id
                        and cast(po.placed_at as date) <= {current_date_sql}
                )
        """,
        "goods_receipt_items": f"""
            select
                gri.*
            from {SOURCE_SCHEMA}.goods_receipt_items as gri
            where exists (
                select 1
                from {SOURCE_SCHEMA}.goods_receipts as gr
                inner join {SOURCE_SCHEMA}.purchase_orders as po
                    on po.id = gr.purchase_order_id
                inner join {SOURCE_SCHEMA}.purchase_order_items as poi
                    on poi.id = gri.purchase_order_item_id
                    and poi.purchase_order_id = po.id
                where gr.id = gri.goods_receipt_id
                    and cast(gr.received_at as date) <= {current_date_sql}
                    and cast(po.placed_at as date) <= {current_date_sql}
            )
        """,
        "stock_movements": f"""
            select
                sm.*
            from {SOURCE_SCHEMA}.stock_movements as sm
            where cast(sm.occurred_at as date) <= {current_date_sql}
        """,
    }

    query = source_queries.get(table_name)

    if query is None:
        return f"{SOURCE_SCHEMA}.{table_name}"

    normalized_query = normalize_query(query)

    return f"({normalized_query}) as filtered_{table_name}"


# ── Leitura ──────────────────────────────────────────────────────────


def read_source_data(
    spark: SparkSession,
    jdbc_password: str,
    table_name: str,
):
    """Lê os dados de uma tabela do SQL Server via JDBC.

    Para tabelas operacionais, o filtro temporal é executado diretamente
    no SQL Server. Tabelas cadastrais são lidas integralmente.

    Args:
        spark: SparkSession ativa.
        jdbc_password: Senha JDBC para autenticação.
        table_name: Nome da tabela de origem.

    Returns:
        DataFrame com os dados disponíveis da tabela.
    """
    source_query = build_source_query(table_name)

    print(f"Consulta JDBC para {table_name}:")
    print(source_query)

    return (
        spark.read.format("jdbc")
        .option("url", JDBC_URL)
        .option("dbtable", source_query)
        .option("user", "student")
        .option("password", jdbc_password)
        .option(
            "driver",
            "com.microsoft.sqlserver.jdbc.SQLServerDriver",
        )
        .load()
    )


# ── Orquestração ─────────────────────────────────────────────────────


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(
        multiplier=1,
        min=2,
        max=10,
    ),
    retry=retry_if_exception_type(Exception),
    before_sleep=lambda retry_state: print(
        f"Tentativa {retry_state.attempt_number}/3 falhou. "
        f"Nova tentativa em "
        f"{retry_state.next_action.sleep}s..."
    ),
    reraise=True,
)
def extract_table(
    spark: SparkSession,
    table_name: str,
    jdbc_password: str,
    catalog: str,
    schema: str,
) -> None:
    """Extrai uma tabela do SQL Server para Bronze.

    Args:
        spark: SparkSession ativa.
        table_name: Nome da tabela a ser extraída.
        jdbc_password: Senha JDBC para autenticação.
        catalog: Nome do catálogo de destino.
        schema: Nome do schema de destino.
    """
    target = f"{catalog}.{schema}.{table_name}"

    print(f"\n{'=' * 80}")
    print(f"Iniciando extração da tabela: {table_name}")
    print(f"Destino: {target}")
    print(f"{'=' * 80}")

    df = read_source_data(
        spark=spark,
        jdbc_password=jdbc_password,
        table_name=table_name,
    )

    df = (
        df.withColumn(
            "_ingested_at",
            F.current_timestamp(),
        )
        .withColumn(
            "_source_path",
            F.lit(
                f"sqlserver://{SOURCE_SCHEMA}.{table_name}"
            ),
        )
    )

    save_full(
        spark=spark,
        df=df,
        table_name=target,
    )

    print(f"Tabela {table_name} salva com sucesso!")


def run_extraction(
    spark: SparkSession,
    table_names: List[str],
    jdbc_password: str,
    catalog: str,
    schema: str,
) -> None:
    """Processa as tabelas e preserva a exceção original.

    Args:
        spark: SparkSession ativa.
        table_names: Lista de nomes de tabelas a extrair.
        jdbc_password: Senha JDBC para autenticação.
        catalog: Nome do catálogo de destino.
        schema: Nome do schema de destino.
    """
    for table_name in table_names:
        try:
            extract_table(
                spark=spark,
                table_name=table_name,
                jdbc_password=jdbc_password,
                catalog=catalog,
                schema=schema,
            )
        except Exception:
            print(f"\n{'=' * 80}")
            print(
                f"ERRO AO PROCESSAR A TABELA: "
                f"{table_name}"
            )
            print(f"{'=' * 80}")

            traceback.print_exc()

            print(f"{'=' * 80}\n")

            raise


# ── Entry point ──────────────────────────────────────────────────────


def main() -> None:
    """Orquestra o fluxo de extração."""
    args = parse_args()

    spark = build_spark_session()
    dbutils = get_dbutils()

    jdbc_password = dbutils.secrets.get(
        scope=SECRET_SCOPE,
        key=SECRET_KEY,
    )

    create_schema(
        spark=spark,
        catalog=args.catalog,
        schema=args.schema,
    )

    table_names = select_tables(args.table)

    run_extraction(
        spark=spark,
        table_names=table_names,
        jdbc_password=jdbc_password,
        catalog=args.catalog,
        schema=args.schema,
    )

    print("Pipeline de extração concluído com sucesso!")


if __name__ == "__main__":
    main()
