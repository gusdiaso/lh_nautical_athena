"""Run one end-to-end documentary RAG question in Databricks."""

from __future__ import annotations

import argparse
import os

from rag_databricks import retrieve_context
from rag_prompt import build_system_prompt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an end-to-end RAG demonstration")
    parser.add_argument("--index-name", required=True)
    parser.add_argument("--endpoint-name", required=True)
    parser.add_argument("--llm-endpoint", default="databricks-meta-llama-3-3-70b-instruct")
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
    from databricks.sdk import WorkspaceClient
    from databricks.ai_search.client import VectorSearchClient
    from openai import OpenAI

    workspace = WorkspaceClient()
    token = workspace.config.token or _runtime_token()
    host = workspace.config.host or os.environ.get("DATABRICKS_HOST")
    if not token or not host:
        raise RuntimeError("Databricks workspace authentication is not available")

    vector_client = VectorSearchClient(disable_notice=True)
    index = vector_client.get_index(endpoint_name=args.endpoint_name, index_name=args.index_name)
    context = retrieve_context(index, args.question, num_results=5, filters={"status": "approved"})
    if context.startswith("Diretriz de Seguranca:"):
        print(context)
        return

    llm_client = OpenAI(api_key=token, base_url=f"{host}/serving-endpoints")
    result = llm_client.chat.completions.create(
        model=args.llm_endpoint,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": f"<DOCUMENTOS_RECUPERADOS>\n{context}\n</DOCUMENTOS_RECUPERADOS>\n\nPERGUNTA:\n{args.question}"},
        ],
        max_tokens=500,
        temperature=0.1,
    )
    answer = result.choices[0].message.content
    if not answer:
        raise RuntimeError("LLM returned an empty answer")
    print(answer)


if __name__ == "__main__":
    main()
