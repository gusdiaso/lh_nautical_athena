"""Environment configuration for the Databricks RAG runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .rag_databricks import VectorIndexConfig


@dataclass(frozen=True)
class RagRuntimeConfig:
    """Validated names for the development RAG resources."""

    volume_path: str
    chunks_table: str
    index: VectorIndexConfig
    llm_endpoint_name: str

    @classmethod
    def from_environment(cls) -> "RagRuntimeConfig":
        catalog = os.getenv("RAG_CATALOG", "dev_lh_nautical")
        schema = os.getenv("RAG_SCHEMA", "rag")
        volume = os.getenv("RAG_VOLUME", "documents")
        chunks_table = os.getenv("RAG_CHUNKS_TABLE", f"{catalog}.{schema}.document_chunks")
        index_name = os.getenv("RAG_INDEX_NAME", f"{catalog}.{schema}.document_chunks_index")
        endpoint_name = os.getenv("RAG_VECTOR_ENDPOINT", "rag-documents-dev")
        embedding_endpoint = os.getenv("RAG_EMBEDDING_ENDPOINT", "databricks-bge-large-en")
        llm_endpoint = os.getenv("RAG_LLM_ENDPOINT", "databricks-meta-llama-3-3-70b-instruct")
        return cls(
            volume_path=f"/Volumes/{catalog}/{schema}/{volume}",
            chunks_table=chunks_table,
            index=VectorIndexConfig(
                endpoint_name=endpoint_name,
                index_name=index_name,
                source_table_name=chunks_table,
                embedding_model_endpoint_name=embedding_endpoint,
            ),
            llm_endpoint_name=llm_endpoint,
        )
