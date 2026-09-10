"""Operational health checks and warehouse-isolation probes for the documentary RAG.

Every Databricks interaction arrives as an injected index object or SQL executor,
so the classification rules stay testable without a workspace. The module never
reads warehouse rows: the isolation probes only try to *list* warehouse schemas,
which is exactly the privilege the RAG identity must not have.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Mapping, Sequence

if __package__:
    from .rag_databricks import retrieve_chunks, validate_schema_name, validate_table_name
    from .rag_prompt import guard_question
else:
    from rag_databricks import retrieve_chunks, validate_schema_name, validate_table_name
    from rag_prompt import guard_question

WAREHOUSE_SCHEMAS: tuple[str, ...] = ("bronze", "silver", "gold")
DEFAULT_PROBE_QUESTION = "Como funciona o processo de ingestao e transformacao do projeto?"

STATUS_HEALTHY = "healthy"
STATUS_DEGRADED = "degraded"
STATUS_VIOLATED = "violated"

HEALTH_REPORT_COLUMNS: tuple[str, ...] = (
    "run_id",
    "run_timestamp",
    "run_label",
    "status",
    "reasons_json",
    "endpoint_name",
    "index_name",
    "index_ready",
    "index_detailed_state",
    "index_error",
    "indexed_row_count",
    "source_table",
    "pipeline_type",
    "table_rows",
    "row_count_drift",
    "probe_question",
    "probe_chunk_count",
    "probe_latency_seconds",
    "probe_refused",
    "probe_error",
    "probe_sources_json",
    "isolation_probes_json",
    "isolation_violations",
    "isolation_inconclusive",
)

# Unity Catalog reports a missing privilege with several phrasings depending on the
# surface that raised it. Anything outside this vocabulary is treated as
# inconclusive instead of silently counting as proof of isolation.
_PERMISSION_DENIED_PATTERN = re.compile(
    r"permission|privileg|unauthoriz|access denied|not authorized|forbidden|403",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class IndexState:
    """Observed state of a Delta Sync index."""

    endpoint_name: str
    index_name: str
    ready: bool | None = None
    detailed_state: str | None = None
    indexed_row_count: int | None = None
    source_table: str | None = None
    pipeline_type: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class RowCountDrift:
    """Comparison between the documentary Delta table and the index."""

    table_rows: int | None
    indexed_rows: int | None

    @property
    def drift(self) -> int | None:
        if self.table_rows is None or self.indexed_rows is None:
            return None
        return self.table_rows - self.indexed_rows

    @property
    def aligned(self) -> bool | None:
        drift = self.drift
        return None if drift is None else drift == 0


@dataclass(frozen=True)
class RetrievalProbe:
    """Result of one documentary smoke question against the live index."""

    question: str
    chunk_count: int
    sources: tuple[tuple[str, str], ...]
    latency_seconds: float
    refused: bool = False
    error: str | None = None


@dataclass(frozen=True)
class IsolationProbe:
    """Outcome of a single warehouse-isolation statement.

    ``blocked`` is ``True`` when the statement was denied, ``False`` when it
    succeeded (the identity still reaches the warehouse) and ``None`` when the
    failure was not a permission error and therefore proves nothing.
    """

    schema: str
    statement: str
    blocked: bool | None
    error: str | None = None


@dataclass(frozen=True)
class HealthReport:
    """Aggregated operational verdict for the documentary RAG."""

    index: IndexState
    rows: RowCountDrift
    probe: RetrievalProbe
    isolation: tuple[IsolationProbe, ...]
    status: str
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reasons": list(self.reasons),
            "index": {
                "endpoint_name": self.index.endpoint_name,
                "index_name": self.index.index_name,
                "ready": self.index.ready,
                "detailed_state": self.index.detailed_state,
                "indexed_row_count": self.index.indexed_row_count,
                "source_table": self.index.source_table,
                "pipeline_type": self.index.pipeline_type,
                "error": self.index.error,
            },
            "rows": {
                "table_rows": self.rows.table_rows,
                "indexed_rows": self.rows.indexed_rows,
                "drift": self.rows.drift,
                "aligned": self.rows.aligned,
            },
            "probe": {
                "question": self.probe.question,
                "chunk_count": self.probe.chunk_count,
                "sources": [
                    {"document": document, "section": section}
                    for document, section in self.probe.sources
                ],
                "latency_seconds": self.probe.latency_seconds,
                "refused": self.probe.refused,
                "error": self.probe.error,
            },
            "isolation": [
                {
                    "schema": probe.schema,
                    "statement": probe.statement,
                    "blocked": probe.blocked,
                    "error": probe.error,
                }
                for probe in self.isolation
            ],
        }


def _nested(value: Any, *keys: str) -> Any:
    """Read a nested key path from an SDK description without assuming its shape."""
    current = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _as_text(value: Any) -> str | None:
    return str(value) if isinstance(value, (str, int, float)) and str(value).strip() else None


def _error_text(exc: Exception) -> str:
    return str(exc)[:500] or exc.__class__.__name__


def describe_index_state(index: Any, endpoint_name: str, index_name: str) -> IndexState:
    """Read the index description and keep failures inside the report."""
    describe = getattr(index, "describe", None)
    if not callable(describe):
        return IndexState(
            endpoint_name, index_name, error="index client does not provide describe"
        )
    try:
        description = describe()
    except Exception as exc:  # a health check must report, not crash
        return IndexState(endpoint_name, index_name, error=_error_text(exc))

    return IndexState(
        endpoint_name=endpoint_name,
        index_name=index_name,
        ready=_as_bool(_nested(description, "status", "ready")),
        detailed_state=_as_text(_nested(description, "status", "detailed_state")),
        indexed_row_count=_as_int(_nested(description, "status", "indexed_row_count")),
        source_table=_as_text(
            _nested(description, "delta_sync_index_spec", "source_table")
        ),
        pipeline_type=_as_text(
            _nested(description, "delta_sync_index_spec", "pipeline_type")
        ),
    )


def count_table_rows(sql_executor: Callable[[str], Any], table_name: str) -> int | None:
    """Count the rows of the documentary Delta table, or return ``None`` on failure."""
    validate_table_name(table_name)
    try:
        result = sql_executor(f"SELECT COUNT(*) AS chunk_rows FROM {table_name}")
        rows = result.collect()
    except Exception:
        return None
    if not rows:
        return None
    first = rows[0]
    try:
        return _as_int(first[0])
    except (IndexError, KeyError, TypeError):
        return None


def probe_retrieval(
    index: Any,
    question: str = DEFAULT_PROBE_QUESTION,
    num_results: int = 5,
    filters: dict[str, str] | None = None,
    clock: Callable[[], float] = perf_counter,
) -> RetrievalProbe:
    """Run one documentary question end-to-end through retrieval and time it.

    The probe also exercises the serving path of the index, so a successful
    probe is the liveness signal for the endpoint behind it.
    """
    started = clock()
    if guard_question(question):
        return RetrievalProbe(question, 0, (), clock() - started, refused=True)
    try:
        chunks = retrieve_chunks(index, question, num_results, filters)
    except Exception as exc:
        return RetrievalProbe(question, 0, (), clock() - started, error=_error_text(exc))
    sources = tuple(
        dict.fromkeys((chunk.source_path, chunk.section) for chunk in chunks)
    )
    return RetrievalProbe(question, len(chunks), sources, clock() - started)


def probe_warehouse_isolation(
    sql_executor: Callable[[str], Any],
    schemas: Sequence[str] = (),
) -> tuple[IsolationProbe, ...]:
    """Confirm that the current identity cannot reach the warehouse schemas.

    ``SHOW TABLES IN`` requires ``USE SCHEMA``, the privilege that gates every
    ``SELECT`` underneath it, and it never returns warehouse rows. A statement
    that succeeds means the identity still has a path into the warehouse.
    """
    probes: list[IsolationProbe] = []
    for schema in schemas:
        validate_schema_name(schema)
        statement = f"SHOW TABLES IN {schema}"
        try:
            result = sql_executor(statement)
            collect = getattr(result, "collect", None)
            if callable(collect):
                # Force lazy evaluation so the privilege is really exercised.
                collect()
        except Exception as exc:
            message = _error_text(exc)
            blocked = True if _PERMISSION_DENIED_PATTERN.search(message) else None
            probes.append(IsolationProbe(schema, statement, blocked, message))
        else:
            probes.append(IsolationProbe(schema, statement, False))
    return tuple(probes)


def warehouse_schemas(catalog: str, schemas: Sequence[str] = WAREHOUSE_SCHEMAS) -> tuple[str, ...]:
    """Qualify the warehouse schema names with the catalog that holds them."""
    return tuple(
        schema if "." in schema else f"{catalog}.{schema}" for schema in schemas
    )


def build_health_report(
    index: IndexState,
    rows: RowCountDrift,
    probe: RetrievalProbe,
    isolation: Sequence[IsolationProbe] = (),
) -> HealthReport:
    """Classify the observed signals into a single actionable verdict."""
    reasons: list[str] = []

    violations = [item.schema for item in isolation if item.blocked is False]
    inconclusive = [item.schema for item in isolation if item.blocked is None]
    if violations:
        reasons.append(
            "warehouse isolation is broken for " + ", ".join(violations)
        )
    if inconclusive:
        reasons.append(
            "warehouse isolation is inconclusive for " + ", ".join(inconclusive)
        )
    if not isolation:
        reasons.append("warehouse isolation was not probed")

    if index.error:
        reasons.append(f"index description failed: {index.error}")
    elif index.ready is False:
        reasons.append(f"index is not ready ({index.detailed_state or 'unknown state'})")
    elif index.ready is None:
        reasons.append("index readiness is unknown")

    if rows.aligned is False:
        reasons.append(
            f"row count drift of {rows.drift} between {index.index_name} and its source table"
        )
    elif rows.aligned is None:
        reasons.append("table and index row counts could not be compared")

    if probe.error:
        reasons.append(f"retrieval probe failed: {probe.error}")
    elif probe.refused:
        reasons.append("retrieval probe question was refused by the guardrail")
    elif probe.chunk_count == 0:
        reasons.append("retrieval probe returned no chunks")

    if violations:
        status = STATUS_VIOLATED
    elif reasons:
        status = STATUS_DEGRADED
    else:
        status = STATUS_HEALTHY
    return HealthReport(index, rows, probe, tuple(isolation), status, tuple(reasons))


def should_fail(status: str, fail_on: str) -> bool:
    """Decide whether a verdict must break the job for the configured severity."""
    if fail_on not in {STATUS_VIOLATED, STATUS_DEGRADED, "never"}:
        raise ValueError("fail_on must be violated, degraded or never")
    if fail_on == "never" or status == STATUS_HEALTHY:
        return False
    return fail_on == STATUS_DEGRADED or status == STATUS_VIOLATED


def health_report_row(
    report: HealthReport,
    run_id: str,
    run_timestamp: str,
    run_label: str | None = None,
) -> dict[str, Any]:
    """Flatten one health report into the append-only report contract."""
    payload = report.as_dict()
    return {
        "run_id": run_id,
        "run_timestamp": run_timestamp,
        "run_label": run_label,
        "status": report.status,
        "reasons_json": json.dumps(list(report.reasons), ensure_ascii=False),
        "endpoint_name": report.index.endpoint_name,
        "index_name": report.index.index_name,
        "index_ready": report.index.ready,
        "index_detailed_state": report.index.detailed_state,
        "index_error": report.index.error,
        "indexed_row_count": report.index.indexed_row_count,
        "source_table": report.index.source_table,
        "pipeline_type": report.index.pipeline_type,
        "table_rows": report.rows.table_rows,
        "row_count_drift": report.rows.drift,
        "probe_question": report.probe.question,
        "probe_chunk_count": report.probe.chunk_count,
        "probe_latency_seconds": report.probe.latency_seconds,
        "probe_refused": report.probe.refused,
        "probe_error": report.probe.error,
        "probe_sources_json": json.dumps(payload["probe"]["sources"], ensure_ascii=False),
        "isolation_probes_json": json.dumps(payload["isolation"], ensure_ascii=False),
        "isolation_violations": sum(
            1 for item in report.isolation if item.blocked is False
        ),
        "isolation_inconclusive": sum(
            1 for item in report.isolation if item.blocked is None
        ),
    }


def append_health_report(
    spark: Any,
    table_name: str,
    report: HealthReport,
    run_id: str,
    run_timestamp: str,
    run_label: str | None = None,
) -> int:
    """Append one health row while evolving the Delta schema, never overwriting history."""
    validate_table_name(table_name)
    row = health_report_row(report, run_id, run_timestamp, run_label)

    from pyspark.sql.types import (
        BooleanType,
        DoubleType,
        LongType,
        StringType,
        StructField,
        StructType,
    )

    long_columns = {
        "indexed_row_count",
        "table_rows",
        "row_count_drift",
        "probe_chunk_count",
        "isolation_violations",
        "isolation_inconclusive",
    }
    boolean_columns = {"index_ready", "probe_refused"}
    schema = StructType([
        StructField(
            column,
            LongType()
            if column in long_columns
            else (
                DoubleType()
                if column == "probe_latency_seconds"
                else (BooleanType() if column in boolean_columns else StringType())
            ),
            True,
        )
        for column in HEALTH_REPORT_COLUMNS
    ])
    dataframe = spark.createDataFrame(
        [tuple(row[column] for column in HEALTH_REPORT_COLUMNS)], schema=schema
    )
    (
        dataframe.select(*HEALTH_REPORT_COLUMNS)
        .write.format("delta")
        .mode("append")
        .option("mergeSchema", "true")
        .saveAsTable(table_name)
    )
    return 1
