"""Extrai as tabelas do SQL Server lh_nautical para a camada Bronze no Databricks."""

import argparse
import os
import traceback
from datetime import date, datetime

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
DEFAULT_CHECKPOINT_VALUE = os.getenv(
    "DATABRICKS_DEFAULT_CHECKPOINT_VALUE",
    "1900-01-01",
)
DEFAULT_CHECKPOINT_CANDIDATES = [
    os.getenv("DATABRICKS_CHECKPOINT_COLUMN", "data_atualizacao"),
    "updated_at",
    "created_at",
    "data_atualizacao",
    "id",
]

TABLE_LOAD_PROFILES = {
    # Tabelas de referência pequenas: recarga total simplifica a manutenção.
    "categories": {
        "mode": "full",
        "merge_keys": [],
        "checkpoint_candidates": [],
    },
    "brands": {
        "mode": "full",
        "merge_keys": [],
        "checkpoint_candidates": [],
    },
    "locations": {
        "mode": "full",
        "merge_keys": [],
        "checkpoint_candidates": [],
    },
    "attributes": {
        "mode": "full",
        "merge_keys": [],
        "checkpoint_candidates": [],
    },

    # Tabelas de movimentação/evento: append preserva o histórico de forma natural.
    "payments": {
        "mode": "append",
        "merge_keys": [],
        "checkpoint_candidates": ["updated_at", "created_at", "id"],
    },
    "order_items": {
        "mode": "append",
        "merge_keys": [],
        "checkpoint_candidates": ["updated_at", "created_at", "id"],
    },
    "purchase_order_items": {
        "mode": "append",
        "merge_keys": [],
        "checkpoint_candidates": ["updated_at", "created_at", "id"],
    },
    "goods_receipts": {
        "mode": "append",
        "merge_keys": [],
        "checkpoint_candidates": ["updated_at", "created_at", "id"],
    },
    "goods_receipt_items": {
        "mode": "append",
        "merge_keys": [],
        "checkpoint_candidates": ["updated_at", "created_at", "id"],
    },
    "return_items": {
        "mode": "append",
        "merge_keys": [],
        "checkpoint_candidates": ["updated_at", "created_at", "id"],
    },
    "stock_movements": {
        "mode": "append",
        "merge_keys": [],
        "checkpoint_candidates": ["updated_at", "created_at", "id"],
    },

    # Tabelas que sofrem atualização de estado e se beneficiam de upsert.
    "customers": {
        "mode": "merge",
        "merge_keys": ["id"],
        "checkpoint_candidates": ["updated_at", "created_at", "id"],
    },
    "suppliers": {
        "mode": "merge",
        "merge_keys": ["id"],
        "checkpoint_candidates": ["updated_at", "created_at", "id"],
    },
    "employees": {
        "mode": "merge",
        "merge_keys": ["id"],
        "checkpoint_candidates": ["updated_at", "created_at", "id"],
    },
    "addresses": {
        "mode": "merge",
        "merge_keys": ["id"],
        "checkpoint_candidates": ["updated_at", "created_at", "id"],
    },
    "products": {
        "mode": "merge",
        "merge_keys": ["id"],
        "checkpoint_candidates": ["updated_at", "created_at", "id"],
    },
    "product_variants": {
        "mode": "merge",
        "merge_keys": ["id"],
        "checkpoint_candidates": ["updated_at", "created_at", "id"],
    },
    "product_suppliers": {
        "mode": "merge",
        "merge_keys": ["product_variant_id", "supplier_id"],
        "checkpoint_candidates": ["updated_at", "created_at"],
    },
    "variant_attribute_values": {
        "mode": "merge",
        "merge_keys": ["product_variant_id", "attribute_id"],
        "checkpoint_candidates": ["updated_at", "created_at"],
    },
    "stock_levels": {
        "mode": "merge",
        "merge_keys": ["id"],
        "checkpoint_candidates": ["updated_at", "created_at", "id"],
    },
    "orders": {
        "mode": "merge",
        "merge_keys": ["id"],
        "checkpoint_candidates": ["updated_at", "created_at", "id"],
    },
    "purchase_orders": {
        "mode": "merge",
        "merge_keys": ["id"],
        "checkpoint_candidates": ["updated_at", "created_at", "id"],
    },
    "fiscal_invoices": {
        "mode": "merge",
        "merge_keys": ["id"],
        "checkpoint_candidates": ["updated_at", "created_at", "id"],
    },
    "returns": {
        "mode": "merge",
        "merge_keys": ["id"],
        "checkpoint_candidates": ["updated_at", "created_at", "id"],
    },
}


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


def get_source_columns(spark_session, jdbc_url, jdbc_password, source_table_name):
    """Lê apenas o schema da tabela de origem para decidir a coluna de checkpoint."""
    source_schema_query = f"(SELECT TOP 0 * FROM {SOURCE_SCHEMA}.{source_table_name}) AS src"
    source_df = (
        spark_session.read.format("jdbc")
        .option("url", jdbc_url)
        .option("dbtable", source_schema_query)
        .option("user", "student")
        .option("password", jdbc_password)
        .option("driver", "com.microsoft.sqlserver.jdbc.SQLServerDriver")
        .load()
    )
    return source_df.columns


def _deduplicate_preserving_order(values):
    """Remove duplicidades sem alterar a prioridade original da lista."""
    unique_values = []
    for value in values:
        if value and value not in unique_values:
            unique_values.append(value)
    return unique_values


def resolve_merge_keys(source_columns, configured_keys=None):
    """Escolhe a chave de merge com base no perfil da tabela e nas colunas reais."""
    if configured_keys:
        merge_keys = [column for column in configured_keys if column in source_columns]
        if merge_keys:
            return merge_keys

    if "id" in source_columns:
        return ["id"]

    foreign_key_columns = [column for column in source_columns if column.endswith("_id")]
    if len(foreign_key_columns) >= 2:
        return foreign_key_columns

    if len(foreign_key_columns) == 1:
        return foreign_key_columns

    return []


def resolve_checkpoint_column(source_columns, configured_candidates=None):
    """Escolhe a coluna de checkpoint disponível na tabela de origem."""
    candidate_columns = _deduplicate_preserving_order(
        (configured_candidates or []) + DEFAULT_CHECKPOINT_CANDIDATES
    )

    for column_name in candidate_columns:
        if column_name in source_columns:
            return column_name

    return None


def resolve_load_profile(source_table_name, source_columns):
    """Define a estratégia de carga mais adequada para a tabela analisada."""
    table_profile = TABLE_LOAD_PROFILES.get(source_table_name, {})
    load_mode = table_profile.get("mode", "full")

    if load_mode == "full":
        return {
            "mode": "full",
            "checkpoint_column": None,
            "merge_keys": [],
        }

    checkpoint_column = resolve_checkpoint_column(
        source_columns,
        table_profile.get("checkpoint_candidates"),
    )
    merge_keys = resolve_merge_keys(source_columns, table_profile.get("merge_keys"))

    if load_mode == "merge" and not merge_keys:
        return {
            "mode": "full",
            "checkpoint_column": None,
            "merge_keys": [],
        }

    return {
        "mode": load_mode,
        "checkpoint_column": checkpoint_column,
        "merge_keys": merge_keys,
    }


def _format_checkpoint_for_sql(checkpoint_value):
    """Converte o checkpoint em um literal SQL seguro para o filtro JDBC."""
    if checkpoint_value is None:
        checkpoint_value = DEFAULT_CHECKPOINT_VALUE

    if isinstance(checkpoint_value, (date, datetime)):
        checkpoint_value = checkpoint_value.isoformat(sep=" ")

    if isinstance(checkpoint_value, str):
        return f"'{checkpoint_value}'"

    return str(checkpoint_value)


def get_destination_checkpoint(
    spark_session,
    target_catalog,
    target_schema,
    source_table_name,
    checkpoint_column,
):
    """Busca o maior valor da coluna de controle já gravado na tabela de destino."""
    target_table = f"{target_catalog}.{target_schema}.{source_table_name}"

    try:
        checkpoint_row = spark_session.sql(
            f"""
            SELECT MAX({checkpoint_column}) AS checkpoint_value
            FROM {target_table}
            """
        ).collect()[0]
        checkpoint_value = checkpoint_row["checkpoint_value"]
    except Exception:
        checkpoint_value = None

    if checkpoint_value is None:
        # Cold start: quando a tabela ainda não existe ou está vazia, usamos um valor mínimo.
        checkpoint_value = DEFAULT_CHECKPOINT_VALUE

    return checkpoint_value


def get_target_table_name(target_catalog, target_schema, source_table_name):
    """Monta o nome totalmente qualificado da tabela de destino."""
    return f"{target_catalog}.{target_schema}.{source_table_name}"


def target_table_exists(spark_session, target_table_name):
    """Verifica se a tabela de destino já foi criada."""
    return spark_session.catalog.tableExists(target_table_name)


def build_source_query(source_table_name, checkpoint_column=None, checkpoint_literal=None):
    """Monta a query JDBC com filtro incremental apenas quando necessário."""
    if checkpoint_column and checkpoint_literal is not None:
        return (
            f"(SELECT * FROM {SOURCE_SCHEMA}.{source_table_name} "
            f"WHERE {checkpoint_column} > {checkpoint_literal}) AS src"
        )

    return f"{SOURCE_SCHEMA}.{source_table_name}"


def save_dataframe(
    spark_session,
    df,
    source_table_name,
    target_table_name,
    load_mode,
    merge_keys,
):
    """Grava o dataframe de acordo com a estratégia definida para a tabela."""
    if load_mode == "full" or not target_table_exists(spark_session, target_table_name):
        (
            df.write.format("delta")
            .mode("overwrite")
            .option("overwriteSchema", "true")
            .saveAsTable(target_table_name)
        )
        return

    if load_mode == "append":
        df.write.format("delta").mode("append").saveAsTable(target_table_name)
        return

    temp_view_name = f"tmp_{source_table_name}_incremental"
    df.createOrReplaceTempView(temp_view_name)

    target_columns = spark_session.table(target_table_name).columns
    source_columns = df.columns
    merge_columns = [column for column in source_columns if column in target_columns]
    merge_update_columns = [
        column for column in merge_columns if column not in merge_keys
    ] or merge_columns

    merge_condition = " AND ".join(
        [f"target.`{key}` = source.`{key}`" for key in merge_keys]
    )

    update_clause = ", ".join(
        [f"target.`{column}` = source.`{column}`" for column in merge_update_columns]
    )
    insert_columns = ", ".join([f"`{column}`" for column in merge_columns])
    insert_values = ", ".join([f"source.`{column}`" for column in merge_columns])

    spark_session.sql(
        f"""
        MERGE INTO {target_table_name} AS target
        USING {temp_view_name} AS source
        ON {merge_condition}
        WHEN MATCHED THEN UPDATE SET {update_clause}
        WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})
        """
    )


def extract_table(
    spark_session,
    source_table_name,
    jdbc_url,
    jdbc_password,
    target_catalog,
    target_schema,
):
    """Lê uma tabela do SQL Server via JDBC e grava como tabela Delta."""
    target_table_name = get_target_table_name(
        target_catalog,
        target_schema,
        source_table_name,
    )

    # Etapa 1: identifica o perfil de carga mais adequado para a tabela.
    source_columns = get_source_columns(
        spark_session,
        jdbc_url,
        jdbc_password,
        source_table_name,
    )
    load_profile = resolve_load_profile(source_table_name, source_columns)

    checkpoint_literal = None
    if load_profile["checkpoint_column"]:
        # Etapa 2: identifica o checkpoint já processado na tabela de destino.
        checkpoint_value = get_destination_checkpoint(
            spark_session,
            target_catalog,
            target_schema,
            source_table_name,
            load_profile["checkpoint_column"],
        )
        checkpoint_literal = _format_checkpoint_for_sql(checkpoint_value)

    # Etapa 3: filtra a origem no próprio JDBC quando a tabela tem checkpoint incremental.
    source_query = build_source_query(
        source_table_name,
        load_profile["checkpoint_column"],
        checkpoint_literal,
    )

    df = (
        spark_session.read.format("jdbc")
        .option("url", jdbc_url)
        .option("dbtable", source_query)
        .option("user", "student")
        .option("password", jdbc_password)
        .option("driver", "com.microsoft.sqlserver.jdbc.SQLServerDriver")
        .load()
    )

    df = (
        df.withColumn("_ingested_at", F.current_timestamp())
        .withColumn(
            "_source_path",
            F.lit(f"sqlserver://{SOURCE_SCHEMA}.{source_table_name}"),
        )
    )

    # Etapa 4: aplica a estratégia correta por tabela, evitando overwrite genérico.
    save_dataframe(
        spark_session,
        df,
        source_table_name,
        target_table_name,
        load_profile["mode"],
        load_profile["merge_keys"],
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
