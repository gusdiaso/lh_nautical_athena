import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from src.analytics_ai.rag_documents import (
    build_chunks,
    load_documents,
    parse_content,
    sanitize_text,
    split_text,
)
from src.analytics_ai.rag_prompt import (
    DATA_WAREHOUSE_RESPONSE,
    build_system_prompt,
    format_context,
    guard_question,
    is_data_warehouse_query,
)
from src.analytics_ai.rag_databricks import (
    VectorIndexConfig,
    chunk_rows,
    create_delta_sync_index,
    retrieve_context,
    synchronize_delta_sync_index,
    validate_table_name,
    wait_for_index,
    write_chunks_to_delta,
)
from src.analytics_ai.rag_config import RagRuntimeConfig
from src.analytics_ai.rag_generation import generate_answer


class RagDocumentsTest(unittest.TestCase):
    def test_sanitizes_secrets_and_email_addresses(self):
        content = "api_key=super-secret-token and owner@example.com"

        sanitized = sanitize_text(content)

        self.assertNotIn("super-secret-token", sanitized)
        self.assertNotIn("owner@example.com", sanitized)
        self.assertIn("[REDACTED]", sanitized)
        self.assertIn("[EMAIL_REDACTED]", sanitized)

    def test_html_parser_excludes_non_visible_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "docs.html"
            path.write_text(
                "<html><head>private metadata</head><body><h2>Architecture</h2>Visible text"
                "<script>api_key=hidden</script><nav>Menu</nav></body></html>",
                encoding="utf-8",
            )

            content = parse_content(path)

        self.assertIn("Visible text", content)
        self.assertIn("## Architecture", content)
        self.assertNotIn("private metadata", content)
        self.assertNotIn("hidden", content)
        self.assertNotIn("Menu", content)

    def test_loader_uses_only_explicit_allowlist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "approved.md").write_text("Approved", encoding="utf-8")
            (root / "unapproved.md").write_text("Unapproved", encoding="utf-8")

            documents = load_documents(root, ["approved.md"])

        self.assertEqual([document.source_path for document in documents], ["approved.md"])

    def test_chunks_are_bounded_and_stable(self):
        text = "word " * 600
        first = build_chunks(load_documents_from_text(text), chunk_size=80, chunk_overlap=10)
        second = build_chunks(load_documents_from_text(text), chunk_size=80, chunk_overlap=10)

        self.assertTrue(first)
        self.assertEqual([chunk.chunk_id for chunk in first], [chunk.chunk_id for chunk in second])
        self.assertEqual([chunk.content for chunk in first], [chunk.content for chunk in second])
        self.assertTrue(all(len(chunk.content) <= 80 for chunk in first))
        self.assertEqual(len({chunk.chunk_id for chunk in first}), len(first))

    def test_chunks_use_their_actual_markdown_section(self):
        documents = load_documents_from_text("# Primeiro\nabc\n# Segundo\ndef")

        chunks = build_chunks(documents, chunk_size=40, chunk_overlap=2)

        self.assertEqual(chunks[0].section, "Primeiro")
        self.assertEqual(chunks[-1].section, "Segundo")
        self.assertEqual({chunk.section for chunk in chunks}, {"Primeiro", "Segundo"})
        self.assertTrue(chunks[0].content.startswith("CONTEXTO: Primeiro\n\n"))
        self.assertTrue(chunks[-1].content.startswith("CONTEXTO: Segundo\n\n"))

    def test_consecutive_markdown_headings_never_share_a_chunk(self):
        chunks = build_chunks(
            load_documents_from_text("# Primeiro\n## Segundo\nconteudo dois"),
            chunk_size=800,
            chunk_overlap=80,
        )

        self.assertEqual([chunk.section for chunk in chunks], ["Segundo"])
        self.assertNotIn("# Primeiro", chunks[0].content)
        self.assertNotIn("# Segundo", chunks[0].content)
        self.assertTrue(chunks[0].content.startswith("CONTEXTO: Primeiro > Segundo\n\n"))

    def test_structural_headings_become_child_breadcrumb_without_own_chunks(self):
        chunks = build_chunks(
            load_documents_from_text(
                "# Modelo Dimensional\n## Fatos\n### fact_stock_movements\nUma linha por movimento."
            )
        )

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].section, "fact_stock_movements")
        self.assertEqual(
            chunks[0].content,
            "CONTEXTO: Modelo Dimensional > Fatos > fact_stock_movements\n\n"
            "Uma linha por movimento.",
        )

    def test_long_markdown_section_creates_multiple_chunks_with_same_section(self):
        chunks = build_chunks(
            load_documents_from_text("# Longa\n" + "palavra " * 80),
            chunk_size=80,
            chunk_overlap=10,
        )

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.section == "Longa" for chunk in chunks))
        self.assertTrue(all(len(chunk.content) <= 80 for chunk in chunks))
        self.assertTrue(all(chunk.content.startswith("CONTEXTO: Longa\n\n") for chunk in chunks))

    def test_markdown_overlap_never_crosses_heading_boundary(self):
        chunks = build_chunks(
            load_documents_from_text(
                "# Primeiro\n" + "alpha " * 40 + "\n# Segundo\n" + "beta " * 40
            ),
            chunk_size=70,
            chunk_overlap=20,
        )

        first = [chunk for chunk in chunks if chunk.section == "Primeiro"]
        second = [chunk for chunk in chunks if chunk.section == "Segundo"]
        self.assertGreater(len(first), 1)
        self.assertGreater(len(second), 1)
        self.assertTrue(all("beta" not in chunk.content for chunk in first))
        self.assertTrue(all("alpha" not in chunk.content for chunk in second))
        self.assertTrue(all(chunk.content.startswith("CONTEXTO: Primeiro\n\n") for chunk in first))
        self.assertTrue(all(chunk.content.startswith("CONTEXTO: Segundo\n\n") for chunk in second))

    def test_markdown_chunk_ids_remain_deterministic_after_section_split(self):
        text = "# Um\n" + "alpha " * 30 + "\n# Dois\n" + "beta " * 30

        first = build_chunks(load_documents_from_text(text), chunk_size=70, chunk_overlap=20)
        second = build_chunks(load_documents_from_text(text), chunk_size=70, chunk_overlap=20)

        self.assertEqual([chunk.chunk_id for chunk in first], [chunk.chunk_id for chunk in second])

    def test_txt_and_html_keep_the_existing_global_chunking_behavior(self):
        txt = build_chunks(load_documents_from_text("plain text " * 20, "document.txt"), 60, 10)
        html = build_chunks(
            load_documents_from_text(
                "<h1>Primeiro</h1><p>alpha</p><h2>Segundo</h2><p>beta</p>",
                "document.html",
            ),
            800,
            80,
        )

        self.assertTrue(all(chunk.source_type == "txt" for chunk in txt))
        self.assertEqual(len(html), 1)
        self.assertEqual(html[0].source_type, "dbt_docs")
        self.assertIn("## Segundo", html[0].content)

    def test_rejects_invalid_chunk_configuration(self):
        with self.assertRaises(ValueError):
            split_text("content", chunk_size=10, chunk_overlap=10)

    def test_blocks_numeric_warehouse_questions(self):
        self.assertTrue(is_data_warehouse_query("Some sales_amount em 2025"))
        self.assertTrue(is_data_warehouse_query("Qual o faturamento atual?"))
        self.assertTrue(is_data_warehouse_query("Qual o faturamento?"))
        self.assertFalse(is_data_warehouse_query("Como funciona o modelo dimensional?"))
        self.assertFalse(is_data_warehouse_query("Como funciona a camada Gold?"))
        self.assertEqual(guard_question("Some sales_amount em 2025"), DATA_WAREHOUSE_RESPONSE)
        self.assertIsNone(guard_question("Qual a arquitetura do dbt?"))

    def test_context_and_prompt_preserve_citations_and_boundary(self):
        chunk = build_chunks(load_documents_from_text("# Arquitetura\nVector Search"))[0]

        context = format_context([chunk])
        prompt = build_system_prompt()

        self.assertIn("DOCUMENTO: document.md", context)
        self.assertIn("SECAO: Arquitetura", context)
        self.assertIn("DOCUMENTOS_RECUPERADOS", prompt)
        self.assertIn(DATA_WAREHOUSE_RESPONSE, prompt)

    def test_delta_adapter_validates_identifiers_and_serializes_metadata(self):
        chunk = build_chunks(load_documents_from_text("content"))[0]

        self.assertEqual(validate_table_name("catalog.schema.chunks"), "catalog.schema.chunks")
        self.assertEqual(chunk_rows([chunk])[0]["last_modified"], chunk.last_modified)
        with self.assertRaises(ValueError):
            validate_table_name("catalog.schema;drop table")

    def test_delta_adapter_writes_explicit_rows(self):
        chunk = build_chunks(load_documents_from_text("content"))[0]
        writer = Mock()
        writer.format.return_value = writer
        writer.mode.return_value = writer
        writer.option.return_value = writer
        spark = Mock()
        spark.createDataFrame.return_value.write = writer

        count = write_chunks_to_delta(spark, [chunk], "catalog.schema.chunks")

        self.assertEqual(count, 1)
        writer.saveAsTable.assert_called_once_with("catalog.schema.chunks")

    def test_vector_adapter_reports_missing_sdk(self):
        config = VectorIndexConfig("endpoint", "catalog.schema.index", "catalog.schema.chunks", "embedding")

        with self.assertRaisesRegex(RuntimeError, "databricks-ai-search"):
            create_delta_sync_index(config)

    def test_existing_delta_sync_index_is_synchronized_and_awaited(self):
        config = VectorIndexConfig("endpoint", "catalog.schema.index", "catalog.schema.chunks", "embedding")
        index = Mock()
        client = Mock()
        client.index_exists.return_value = True
        client.get_index.return_value = index

        result = synchronize_delta_sync_index(config, client=client, timeout_seconds=30)

        self.assertIs(result, index)
        client.get_index.assert_called_once_with(
            endpoint_name="endpoint", index_name="catalog.schema.index"
        )
        index.sync.assert_called_once_with()
        index.wait_until_ready.assert_called_once()
        self.assertTrue(index.wait_until_ready.call_args.kwargs["wait_for_updates"])
        self.assertEqual(
            index.wait_until_ready.call_args.kwargs["timeout"].total_seconds(), 30
        )

    def test_missing_index_is_created_without_duplicate_sync(self):
        config = VectorIndexConfig("endpoint", "catalog.schema.index", "catalog.schema.chunks", "embedding")
        index = Mock()
        client = Mock()
        client.index_exists.return_value = False
        client.create_delta_sync_index_and_wait.return_value = index

        result = synchronize_delta_sync_index(config, client=client, timeout_seconds=45)

        self.assertIs(result, index)
        client.get_index.assert_not_called()
        client.create_delta_sync_index_and_wait.assert_called_once()
        creation = client.create_delta_sync_index_and_wait.call_args.kwargs
        self.assertEqual(creation["primary_key"], "chunk_id")
        self.assertEqual(creation["pipeline_type"], "TRIGGERED")
        self.assertEqual(creation["timeout"].total_seconds(), 45)
        index.sync.assert_not_called()

    def test_remote_sync_error_fails_clearly(self):
        config = VectorIndexConfig("endpoint", "catalog.schema.index", "catalog.schema.chunks", "embedding")
        index = Mock()
        index.sync.side_effect = Exception("remote pipeline error")
        client = Mock()
        client.index_exists.return_value = True
        client.get_index.return_value = index

        with self.assertRaisesRegex(RuntimeError, "remote pipeline error"):
            synchronize_delta_sync_index(config, client=client)

        index.wait_until_ready.assert_not_called()

    def test_sync_timeout_fails_clearly(self):
        config = VectorIndexConfig("endpoint", "catalog.schema.index", "catalog.schema.chunks", "embedding")
        index = Mock()
        index.wait_until_ready.side_effect = Exception(
            "did not become online within timeout of 30s"
        )
        client = Mock()
        client.index_exists.return_value = True
        client.get_index.return_value = index

        with self.assertRaisesRegex(RuntimeError, "within timeout"):
            synchronize_delta_sync_index(config, client=client, timeout_seconds=30)

        index.sync.assert_called_once_with()

    def test_retrieval_uses_hybrid_search_and_filters(self):
        index = Mock()
        index.similarity_search.return_value = {
            "manifest": {
                "columns": [
                    {"name": "content"},
                    {"name": "source_path"},
                    {"name": "section"},
                    {"name": "file_name"},
                ]
            },
            "result": {
                "data_array": [["customer_id identifies a customer", "docs/dictionary.md", "Columns", "dictionary.md"]]
            }
        }

        context = retrieve_context(index, "What identifies a customer?", filters={"status": "approved"})

        self.assertIn("DOCUMENTO: docs/dictionary.md", context)
        self.assertIn("SECAO: Columns", context)
        arguments = index.similarity_search.call_args.kwargs
        self.assertEqual(arguments["query_type"], "hybrid")
        self.assertEqual(arguments["filters"], {"status": "approved"})

    def test_retrieval_blocks_numeric_question_before_index_call(self):
        index = Mock()

        result = retrieve_context(index, "Some sales_amount em 2025")

        self.assertEqual(result, DATA_WAREHOUSE_RESPONSE)
        index.similarity_search.assert_not_called()

    def test_wait_for_index_uses_explicit_timeout(self):
        index = Mock()

        wait_for_index(index, timeout_seconds=30)

        index.wait_until_ready.assert_called_once()
        self.assertEqual(index.wait_until_ready.call_args.kwargs["timeout"].total_seconds(), 30)

    def test_generation_uses_context_and_returns_sources(self):
        client = Mock()
        client.create.return_value.choices = [Mock(message=Mock(content="A resposta documental."))]
        chunks = build_chunks(load_documents_from_text("# Arquitetura\nVector Search"))

        result = generate_answer(client, "O que e usado para busca?", chunks, "test-model")

        self.assertEqual(result.answer, "A resposta documental.")
        self.assertEqual(result.sources, ("document.md",))
        arguments = client.create.call_args.kwargs
        self.assertEqual(arguments["model"], "test-model")
        self.assertIn("DOCUMENTOS_RECUPERADOS", arguments["messages"][1]["content"])

    def test_generation_refuses_numeric_question_without_calling_llm(self):
        client = Mock()
        chunks = build_chunks(load_documents_from_text("content"))

        result = generate_answer(client, "Qual o faturamento?", chunks, "test-model")

        self.assertTrue(result.refused)
        client.create.assert_not_called()

    def test_runtime_configuration_has_isolated_document_resources(self):
        config = RagRuntimeConfig.from_environment()

        self.assertEqual(config.volume_path, "/Volumes/dev_lh_nautical/rag/documents")
        self.assertEqual(config.chunks_table, "dev_lh_nautical.rag.document_chunks")
        self.assertEqual(config.index.embedding_model_endpoint_name, "databricks-bge-large-en")
        self.assertEqual(config.llm_endpoint_name, "databricks-meta-llama-3-3-70b-instruct")


def load_documents_from_text(text, file_name="document.md"):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / file_name
        path.write_text(text, encoding="utf-8")
        return load_documents(root, [path.name])


if __name__ == "__main__":
    unittest.main()
