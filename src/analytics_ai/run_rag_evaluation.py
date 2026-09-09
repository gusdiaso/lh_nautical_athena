"""Run a Golden Dataset suite in one Databricks job and append its report."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path
from time import perf_counter

from pyspark.sql import SparkSession

if __package__:
    from .rag_databricks import retrieve_chunks
    from .rag_evaluation import (
        EvaluationObservation,
        ExpectedSource,
        append_remote_results,
        load_golden_dataset,
        parse_citations,
        run_remote_evaluation,
    )
    from .rag_generation import generate_answer
    from .rag_prompt import guard_question
else:
    from rag_databricks import retrieve_chunks
    from rag_evaluation import (
        EvaluationObservation,
        ExpectedSource,
        append_remote_results,
        load_golden_dataset,
        parse_citations,
        run_remote_evaluation,
    )
    from rag_generation import generate_answer
    from rag_prompt import guard_question


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the documentary RAG")
    parser.add_argument("--suite", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--index-name", required=True)
    parser.add_argument("--endpoint-name", required=True)
    parser.add_argument("--report-table", required=True)
    parser.add_argument(
        "--question-endpoint",
        default="databricks-meta-llama-3-3-70b-instruct",
    )
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--run-label")
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Explicit local or Workspace path to rag_golden_dataset.jsonl",
    )
    return parser.parse_args()


def _runtime_token() -> str | None:
    token = os.environ.get("DATABRICKS_TOKEN")
    if token:
        return token
    try:
        from databricks.sdk.runtime import dbutils

        return dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
    except (ImportError, AttributeError, KeyError, RuntimeError):
        return None


def main() -> None:
    args = parse_args()
    if not 1 <= args.max_results <= 10:
        raise ValueError("max-results must be between 1 and 10")

    from databricks.ai_search.client import AISearchClient
    from databricks.sdk import WorkspaceClient
    from openai import OpenAI

    workspace = WorkspaceClient()
    token = workspace.config.token or _runtime_token()
    host = workspace.config.host or os.environ.get("DATABRICKS_HOST")
    if not token or not host:
        raise RuntimeError("Databricks workspace authentication is not available")

    vector_client = AISearchClient(disable_notice=True)
    index = vector_client.get_index(
        endpoint_name=args.endpoint_name,
        index_name=args.index_name,
    )
    chat = OpenAI(api_key=token, base_url=f"{host}/serving-endpoints").chat.completions
    repository_root = args.dataset.resolve().parents[1]
    cases = load_golden_dataset(args.dataset, repository_root)

    def execute(case):
        started = perf_counter()
        chunks = [] if guard_question(case.question) else retrieve_chunks(
            index, case.question, num_results=args.max_results, filters={"status": "approved"}
        )
        generated = generate_answer(chat, case.question, chunks, args.question_endpoint)
        sources = tuple(ExpectedSource(chunk.source_path, chunk.section) for chunk in chunks)
        return EvaluationObservation(
            behavior="unclassified",
            answer=generated.answer,
            retrieved_sources=tuple(dict.fromkeys(sources)),
            cited_sources=parse_citations(generated.answer),
            latency_seconds=perf_counter() - started,
        )

    summary = run_remote_evaluation(
        cases=cases,
        suite=args.suite,
        executor=execute,
        run_id=str(uuid.uuid4()),
        run_label=args.run_label,
    )
    spark = SparkSession.builder.getOrCreate()
    append_remote_results(spark, args.report_table, summary.results)
    print(json.dumps({
        "total": summary.total,
        "passed": summary.passed,
        "failed": summary.failed,
        "needs_review": summary.needs_review,
        "deterministic_pass_rate": summary.deterministic_pass_rate,
        "mean_latency_seconds": summary.mean_latency_seconds,
        "failed_ids": summary.failed_ids,
        "needs_review_ids": summary.needs_review_ids,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
