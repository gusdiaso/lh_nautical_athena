"""Check the documentary RAG index, its drift and its warehouse isolation."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone

from pyspark.sql import SparkSession

if __package__:
    from .rag_operations import (
        DEFAULT_PROBE_QUESTION,
        STATUS_DEGRADED,
        STATUS_VIOLATED,
        IndexState,
        RetrievalProbe,
        RowCountDrift,
        append_health_report,
        build_health_report,
        count_table_rows,
        describe_index_state,
        probe_retrieval,
        probe_warehouse_isolation,
        should_fail,
        warehouse_schemas,
    )
else:
    from rag_operations import (
        DEFAULT_PROBE_QUESTION,
        STATUS_DEGRADED,
        STATUS_VIOLATED,
        IndexState,
        RetrievalProbe,
        RowCountDrift,
        append_health_report,
        build_health_report,
        count_table_rows,
        describe_index_state,
        probe_retrieval,
        probe_warehouse_isolation,
        should_fail,
        warehouse_schemas,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check the documentary RAG operation")
    parser.add_argument("--index-name", required=True)
    parser.add_argument("--endpoint-name", required=True)
    parser.add_argument("--chunks-table", required=True)
    parser.add_argument("--probe-question", default=DEFAULT_PROBE_QUESTION)
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument(
        "--isolation-schemas",
        default="bronze,silver,gold",
        help="Comma separated schemas that the RAG identity must not reach; "
        "unqualified names inherit the catalog of --chunks-table",
    )
    parser.add_argument("--report-table")
    parser.add_argument("--run-label")
    parser.add_argument(
        "--fail-on",
        choices=(STATUS_VIOLATED, STATUS_DEGRADED, "never"),
        default=STATUS_VIOLATED,
        help="Exit with an error when the verdict reaches this severity",
    )
    return parser.parse_args()


def _isolation_schemas(raw: str, chunks_table: str) -> tuple[str, ...]:
    names = [item.strip() for item in raw.split(",") if item.strip()]
    if not names:
        return ()
    return warehouse_schemas(chunks_table.split(".")[0], names)


def main() -> None:
    args = parse_args()
    if not 1 <= args.max_results <= 10:
        raise ValueError("max-results must be between 1 and 10")

    from databricks.ai_search.client import AISearchClient

    spark = SparkSession.builder.getOrCreate()
    client = AISearchClient(disable_notice=True)
    try:
        index = client.get_index(
            endpoint_name=args.endpoint_name,
            index_name=args.index_name,
        )
    except Exception as exc:  # the verdict must be reported, not raised
        index = None
        index_state = IndexState(
            args.endpoint_name, args.index_name, error=str(exc)[:500]
        )
    else:
        index_state = describe_index_state(index, args.endpoint_name, args.index_name)

    probe = (
        probe_retrieval(
            index,
            args.probe_question,
            args.max_results,
            filters={"status": "approved"},
        )
        if index is not None
        else RetrievalProbe(args.probe_question, 0, (), 0.0, error="index is unavailable")
    )
    rows = RowCountDrift(
        count_table_rows(spark.sql, args.chunks_table), index_state.indexed_row_count
    )
    isolation = probe_warehouse_isolation(
        spark.sql, _isolation_schemas(args.isolation_schemas, args.chunks_table)
    )
    report = build_health_report(index_state, rows, probe, isolation)
    print(json.dumps(report.as_dict(), ensure_ascii=False))

    if args.report_table:
        append_health_report(
            spark,
            args.report_table,
            report,
            run_id=str(uuid.uuid4()),
            run_timestamp=datetime.now(timezone.utc).isoformat(),
            run_label=args.run_label,
        )

    if should_fail(report.status, args.fail_on):
        raise SystemExit(
            f"RAG health check status is {report.status}: " + "; ".join(report.reasons)
        )


if __name__ == "__main__":
    main()
