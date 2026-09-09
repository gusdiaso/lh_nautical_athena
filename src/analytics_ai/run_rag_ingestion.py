"""Run the documentation-only RAG ingestion in Databricks."""

from __future__ import annotations

import argparse
from pathlib import Path

from pyspark.sql import SparkSession

if __package__:
    from .rag_databricks import (
        VectorIndexConfig,
        synchronize_delta_sync_index,
        write_chunks_to_delta,
    )
    from .rag_documents import build_chunks, load_documents
else:
    from rag_databricks import (
        VectorIndexConfig,
        synchronize_delta_sync_index,
        write_chunks_to_delta,
    )
    from rag_documents import build_chunks, load_documents


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest approved documentation into Delta")
    parser.add_argument("--volume-path", required=True)
    parser.add_argument("--chunks-table", required=True)
    parser.add_argument("--index-name", required=True)
    parser.add_argument("--endpoint-name", required=True)
    parser.add_argument("--embedding-endpoint", required=True)
    parser.add_argument("--index-timeout-seconds", type=int, default=3600)
    parser.add_argument("--chunk-size", type=int, default=800)
    parser.add_argument("--chunk-overlap", type=int, default=80)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    documents = load_documents(Path(args.volume_path))
    chunks = build_chunks(documents, args.chunk_size, args.chunk_overlap)
    spark = SparkSession.builder.getOrCreate()
    count = write_chunks_to_delta(spark, chunks, args.chunks_table)
    print(f"Ingested {len(documents)} documents and {count} chunks with overwrite")
    synchronize_delta_sync_index(
        VectorIndexConfig(
            endpoint_name=args.endpoint_name,
            index_name=args.index_name,
            source_table_name=args.chunks_table,
            embedding_model_endpoint_name=args.embedding_endpoint,
        ),
        timeout_seconds=args.index_timeout_seconds,
    )
    print("Document ingestion and AI Search synchronization completed")


if __name__ == "__main__":
    main()
