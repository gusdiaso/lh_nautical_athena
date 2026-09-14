"""Run one end-to-end documentary RAG question in Databricks."""

from __future__ import annotations

import argparse
import json
import os

if __package__:
    from .rag_databricks import retrieve_chunks
    from .rag_endpoint import RateLimitedChatClient
    from .rag_generation import check_citations, generate_answer
else:
    from rag_databricks import retrieve_chunks
    from rag_endpoint import RateLimitedChatClient
    from rag_generation import check_citations, generate_answer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an end-to-end RAG demonstration")
    parser.add_argument("--index-name", required=True)
    parser.add_argument("--endpoint-name", required=True)
    parser.add_argument("--llm-endpoint", default="databricks-meta-llama-3-3-70b-instruct")
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--request-interval-seconds", type=float, default=2.0)
    parser.add_argument(
        "--question",
        default="Como funciona o processo de ingestao e transformacao do projeto?",
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
    if args.request_interval_seconds < 0:
        raise ValueError("request-interval-seconds must be non-negative")

    from databricks.sdk import WorkspaceClient
    from databricks.ai_search.client import AISearchClient
    from openai import OpenAI

    workspace = WorkspaceClient()
    token = workspace.config.token or _runtime_token()
    host = workspace.config.host or os.environ.get("DATABRICKS_HOST")
    if not token or not host:
        raise RuntimeError("Databricks workspace authentication is not available")

    vector_client = AISearchClient(disable_notice=True)
    index = vector_client.get_index(endpoint_name=args.endpoint_name, index_name=args.index_name)
    chunks = retrieve_chunks(
        index, args.question, num_results=args.max_results, filters={"status": "approved"}
    )
    chat = RateLimitedChatClient(
        OpenAI(api_key=token, base_url=f"{host}/serving-endpoints").chat.completions,
        request_interval_seconds=args.request_interval_seconds,
    )
    generated = generate_answer(chat, args.question, chunks, args.llm_endpoint)
    citations = check_citations(generated.answer, chunks)

    print(generated.answer)
    print(json.dumps({
        "question": args.question,
        "refused": generated.refused,
        "retrieved_chunks": len(chunks),
        "sources": list(generated.sources),
        "citations": [
            {"document": document, "section": section}
            for document, section in citations.cited
        ],
        "citations_valid": citations.valid,
        "citations_not_retrieved": [
            {"document": document, "section": section}
            for document, section in citations.not_retrieved
        ],
    }, ensure_ascii=False))

    if not generated.refused and not citations.valid:
        print(
            "AVISO: a resposta tecnica nao apresentou citacoes verificaveis nos "
            "trechos recuperados; trate a saida como nao auditavel."
        )


if __name__ == "__main__":
    main()
