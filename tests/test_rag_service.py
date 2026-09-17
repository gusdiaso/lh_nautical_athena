import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from src.analytics_ai.rag_service import RagService, export_interactions
from src.analytics_ai.rag_clients import WorkspaceIndex
from src.analytics_ai.rag_prompt import NO_DOCUMENTATION_RESPONSE


def completion(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def fake_clients(text="A ingestão usa documentos aprovados."):
    index = Mock()
    index.similarity_search.return_value = {"result": {"data_array": [
        ["README.md", "README.md", "RAG", "A ingestão usa documentos aprovados."]
    ]}}
    chat = Mock()
    chat.create.return_value = completion(text)
    return index, chat


class RagServiceTest(unittest.TestCase):
    def test_answer_preserves_evidence_and_uses_approved_filter(self):
        index, chat = fake_clients()
        result = RagService(lambda: (index, chat), "model").ask("Como funciona a ingestão?")
        self.assertEqual(result.status, "answer")
        self.assertTrue(result.citations_valid)
        self.assertEqual(result.retrieved[0]["document"], "README.md")
        self.assertEqual(index.similarity_search.call_args.kwargs["filters"], {"status": "approved"})
        chat.create.assert_called_once()

    def test_guard_and_invalid_questions_never_initialize_clients(self):
        factory = Mock(side_effect=AssertionError("must not initialize"))
        service = RagService(factory, "model")
        self.assertEqual(service.ask("Qual o faturamento atual?").status, "refused")
        self.assertEqual(service.ask(" ").status, "error")
        self.assertEqual(service.ask("x" * 4001).status, "error")
        factory.assert_not_called()

    def test_empty_retrieval_does_not_generate(self):
        index, chat = fake_clients()
        index.similarity_search.return_value = {"result": {"data_array": []}}
        result = RagService(lambda: (index, chat), "model").ask("Como funciona?")
        self.assertEqual(result.status, "insufficient_context")
        chat.create.assert_not_called()

    def test_model_context_refusal_is_distinguished(self):
        result = RagService(lambda: fake_clients(NO_DOCUMENTATION_RESPONSE), "model").ask("Como funciona?")
        self.assertEqual(result.status, "insufficient_context")

    def test_errors_never_export_exception_credentials(self):
        for failure in ("factory", "retrieval", "generation"):
            index, chat = fake_clients()
            factory = Mock(return_value=(index, chat))
            target = {"factory": factory, "retrieval": index.similarity_search,
                      "generation": chat.create}[failure]
            target.side_effect = RuntimeError("Authorization: Bearer sensitive-test-value")
            result = RagService(factory, "model").ask("Como funciona?")
            self.assertEqual(result.status, "error")
            self.assertNotIn("sensitive-test-value", export_interactions([result]))

    def test_feedback_export_does_not_call_model(self):
        index, chat = fake_clients()
        result = RagService(lambda: (index, chat), "model").ask("Como funciona?")
        result.feedback = "useful"
        exported = json.loads(export_interactions([result]))
        self.assertEqual(exported["interactions"][0]["feedback"], "useful")
        self.assertEqual(exported["interactions"][0]["id"], result.id)
        chat.create.assert_called_once()

    def test_demo_uses_service_without_credentials_for_refusal(self):
        from src.analytics_ai import run_rag_demo
        with patch("sys.argv", ["run_rag_demo", "--index-name", "cat.rag.idx",
                                "--endpoint-name", "endpoint", "--question",
                                "Qual o faturamento atual?"]), patch("builtins.print") as output:
            run_rag_demo.main()
        report = json.loads(output.call_args_list[1].args[0])
        self.assertEqual(report["status"], "refused")

    def test_sdk_adapter_preserves_retrieval_contract(self):
        workspace = Mock()
        workspace.vector_search_indexes.query_index.return_value.as_dict.return_value = {"result": {}}
        result = WorkspaceIndex(workspace, "cat.rag.idx").similarity_search(
            query_text="pergunta", query_type="hybrid", columns=["content"],
            filters={"status": "approved"}, num_results=5,
        )
        self.assertEqual(result, {"result": {}})
        args = workspace.vector_search_indexes.query_index.call_args.kwargs
        self.assertEqual(args["query_type"], "HYBRID")
        self.assertEqual(json.loads(args["filters_json"]), {"status": "approved"})


if __name__ == "__main__":
    unittest.main()
