"""Databricks adapters for the documentation-only RAG.

The module keeps Databricks-only imports inside the functions that need them so
local parsing and safety tests remain independent from a workspace runtime.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Iterable

if __package__:
    from .rag_documents import Chunk
    from .rag_prompt import format_context, guard_question
else:
    from rag_documents import Chunk
    from rag_prompt import format_context, guard_question

_TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class VectorIndexConfig:
    """Configuration for a Delta Sync Vector Search index."""

    endpoint_name: str
    index_name: str
    source_table_name: str
    embedding_model_endpoint_name: str
    embedding_source_column: str = "content"
    pipeline_type: str = "TRIGGERED"


def validate_table_name(table_name: str) -> str:
    """Validate a Unity Catalog table identifier before passing it to Spark."""
    parts = table_name.split(".")
    if len(parts) != 3 or not all(_TABLE_NAME_PATTERN.fullmatch(part) for part in parts):
        raise ValueError("table_name must be a catalog.schema.table identifier")
    return table_name


def validate_schema_name(schema_name: str) -> str:
    """Validate a Unity Catalog ``catalog.schema`` identifier before SQL interpolation."""
    parts = schema_name.split(".")
    if len(parts) != 2 or not all(_TABLE_NAME_PATTERN.fullmatch(part) for part in parts):
        raise ValueError("schema_name must be a catalog.schema identifier")
    return schema_name


def chunk_rows(chunks: Iterable[Chunk]) -> list[dict[str, str]]:
    """Convert chunks to the explicit row contract used by the Delta table."""
    return [chunk.as_dict() for chunk in chunks]


CHANGE_HISTORY_RETENTION = "interval 90 days"


def write_chunks_to_delta(
    spark: Any,
    chunks: Iterable[Chunk],
    table_name: str,
    enable_change_data_feed: bool = True,
) -> int:
    """Overwrite the documentary Delta table and return the number of rows written."""
    validate_table_name(table_name)
    rows = chunk_rows(chunks)
    if not rows:
        raise ValueError("cannot write an empty chunk collection")

    from pyspark.sql.types import StringType, StructField, StructType

    field_names = tuple(rows[0])
    schema = StructType([StructField(name, StringType(), False) for name in field_names])
    dataframe = spark.createDataFrame(
        [tuple(row[name] for name in field_names) for row in rows], schema=schema
    )
    writer = (
        dataframe.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
    )
    if enable_change_data_feed:
        writer = writer.option("delta.enableChangeDataFeed", "true")
    writer.saveAsTable(table_name)
    # The Delta Sync index resumes from the change feed of its last sync. With
    # the default 7-day retention a table that goes weeks between ingestions
    # loses that history and the index can only be recreated; keep it longer.
    # Writer options do not persist table properties, so set them explicitly.
    spark.sql(
        f"ALTER TABLE {table_name} SET TBLPROPERTIES ("
        f"'delta.deletedFileRetentionDuration' = '{CHANGE_HISTORY_RETENTION}', "
        f"'delta.logRetentionDuration' = '{CHANGE_HISTORY_RETENTION}')"
    )
    return len(rows)


def create_delta_sync_index(config: VectorIndexConfig, client: Any | None = None) -> Any:
    """Create a Delta Sync index using the installed Databricks Vector Search SDK.

    Endpoint provisioning is intentionally separate: the caller must create or
    approve the endpoint before invoking this function, preventing accidental
    infrastructure creation during document ingestion.
    """
    validate_table_name(config.source_table_name)
    validate_table_name(config.index_name)
    if config.pipeline_type not in {"TRIGGERED", "CONTINUOUS"}:
        raise ValueError("pipeline_type must be TRIGGERED or CONTINUOUS")
    if not config.embedding_model_endpoint_name.strip():
        raise ValueError("embedding_model_endpoint_name cannot be empty")

    if client is None:
        try:
            from databricks.ai_search.client import AISearchClient
        except ImportError as exc:
            raise RuntimeError(
                "databricks-ai-search is required for AI Search integration"
            ) from exc
        client = AISearchClient(disable_notice=True)

    return client.create_delta_sync_index_and_wait(
        endpoint_name=config.endpoint_name,
        index_name=config.index_name,
        primary_key="chunk_id",
        source_table_name=config.source_table_name,
        pipeline_type=config.pipeline_type,
        embedding_source_column=config.embedding_source_column,
        embedding_model_endpoint_name=config.embedding_model_endpoint_name,
    )


def synchronize_delta_sync_index(
    config: VectorIndexConfig,
    client: Any | None = None,
    timeout_seconds: int = 3600,
) -> Any:
    """Create a missing index or synchronize an existing TRIGGERED index."""
    validate_table_name(config.source_table_name)
    validate_table_name(config.index_name)
    if config.pipeline_type != "TRIGGERED":
        raise ValueError("explicit synchronization requires pipeline_type TRIGGERED")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if client is None:
        try:
            from databricks.ai_search.client import AISearchClient
        except ImportError as exc:
            raise RuntimeError(
                "databricks-ai-search is required for AI Search integration"
            ) from exc
        client = AISearchClient(disable_notice=True)

    timeout = timedelta(seconds=timeout_seconds)
    try:
        if not client.index_exists(
            endpoint_name=config.endpoint_name,
            index_name=config.index_name,
        ):
            print(f"AI Search index {config.index_name} does not exist; creating it")
            index = client.create_delta_sync_index_and_wait(
                endpoint_name=config.endpoint_name,
                index_name=config.index_name,
                primary_key="chunk_id",
                source_table_name=config.source_table_name,
                pipeline_type=config.pipeline_type,
                embedding_source_column=config.embedding_source_column,
                embedding_model_endpoint_name=config.embedding_model_endpoint_name,
                verbose=True,
                timeout=timeout,
            )
            print(f"AI Search index {config.index_name} was created and is ready")
            return index

        print(f"Starting AI Search synchronization for {config.index_name}")
        index = client.get_index(
            endpoint_name=config.endpoint_name,
            index_name=config.index_name,
        )
        index.sync()
        index.wait_until_ready(
            verbose=True,
            timeout=timeout,
            wait_for_updates=True,
        )
        print(f"AI Search synchronization completed for {config.index_name}")
        return index
    except Exception as exc:
        message = f"AI Search synchronization failed for {config.index_name}: {exc}"
        print(message)
        raise RuntimeError(message) from exc


def wait_for_index(index: Any, timeout_seconds: int = 3600) -> Any:
    """Wait for an index created by the AI Search SDK to become ready."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    waiter = getattr(index, "wait_until_ready", None)
    if not callable(waiter):
        raise TypeError("index client does not provide wait_until_ready")
    return waiter(verbose=True, timeout=timedelta(seconds=timeout_seconds))


def retrieve_context(
    index: Any,
    question: str,
    num_results: int = 4,
    filters: dict[str, str] | None = None,
) -> str:
    """Run hybrid retrieval and return a citable context string.

    Numeric warehouse questions are blocked before the index is called. The
    index must return Vector Search's ``result.data_array`` using the requested
    column order: ``source_path``, ``file_name``, ``section`` and ``content``.
    """
    refusal = guard_question(question)
    if refusal:
        return refusal
    return format_context(retrieve_chunks(index, question, num_results, filters))


def retrieve_chunks(
    index: Any,
    question: str,
    num_results: int = 4,
    filters: dict[str, str] | None = None,
) -> list[Chunk]:
    """Run hybrid retrieval and preserve chunk metadata for evaluation/generation."""
    if guard_question(question):
        return []
    if not question.strip():
        raise ValueError("question cannot be empty")
    if not 1 <= num_results <= 10:
        raise ValueError("num_results must be between 1 and 10")

    search_arguments: dict[str, Any] = {
        "query_text": question,
        "columns": ["source_path", "file_name", "section", "content"],
        "num_results": num_results,
        "query_type": "hybrid",
    }
    if filters:
        search_arguments["filters"] = filters
    response = index.similarity_search(**search_arguments)
    rows = response.get("result", {}).get("data_array", [])
    if not isinstance(rows, list):
        raise ValueError("Vector Search response has an invalid data_array")

    manifest = response.get("manifest", {})
    manifest_columns = manifest.get("columns", []) if isinstance(manifest, dict) else []
    column_names = [
        column.get("name")
        for column in manifest_columns
        if isinstance(column, dict) and isinstance(column.get("name"), str)
    ]
    if not column_names:
        column_names = search_arguments["columns"]
    column_positions = {name: position for position, name in enumerate(column_names)}
    required_columns = {"source_path", "file_name", "section", "content"}
    if not required_columns.issubset(column_positions):
        raise ValueError("Vector Search response is missing citation columns")

    chunks: list[Chunk] = []
    for position, row in enumerate(rows):
        if not isinstance(row, list) or len(row) < len(column_names):
            continue
        chunks.append(
            Chunk(
                chunk_id=f"retrieved-{position}",
                source_path=str(row[column_positions["source_path"]]),
                file_name=str(row[column_positions["file_name"]]),
                source_type="retrieved",
                section=str(row[column_positions["section"]]),
                content=str(row[column_positions["content"]]),
                content_hash="retrieved",
                last_modified="retrieved",
                status="approved",
            )
        )
    return chunks
