import json
import unittest
from unittest.mock import MagicMock

from src.analytics_ai.rag_documents import Chunk
from src.analytics_ai.rag_evaluation import ExpectedSource
from src.analytics_ai.rag_groundedness import (
    build_judge_messages,
    evaluate_groundedness,
    validate_judge_output,
)


def _chunk(
    section="Objetivo",
    content="A staging padroniza nomes e tipos.",
    source_path="docs/staging.md",
):
    return Chunk(
        "id-1", source_path, source_path.rsplit("/", 1)[-1], "markdown", section,
        content, "hash", "2026-01-01", "approved",
    )


def _client(payload=None, exception=None):
    client = MagicMock()
    if exception:
        client.create.side_effect = exception
    else:
        response = MagicMock()
        response.choices[0].message.content = json.dumps(payload, ensure_ascii=False)
        client.create.return_value = response
    return client


class RagGroundednessTest(unittest.TestCase):
    def _evaluate(self, payload, answer="A staging padroniza nomes e tipos."):
        return evaluate_groundedness(
            _client(payload), "Qual o objetivo?", answer,
            [_chunk()], [ExpectedSource("docs/staging.md", "Objetivo")], "endpoint",
        )

    def test_fully_supported_answer(self):
        result = self._evaluate({
            "claims": [{"claim_id": "claim_1", "verdict": "supported",
                        "evidence_ids": ["evidence_1"]}],
        })
        self.assertEqual(result.status, "completed")
        self.assertTrue(result.grounded)
        self.assertEqual(result.supported_claims, 1)
        self.assertEqual(result.structured_output["output_normalization"], "none")

    def test_single_trailing_brace_is_repaired_and_audited(self):
        valid = json.dumps({
            "claims": [{"claim_id": "claim_1", "verdict": "supported",
                        "evidence_ids": ["evidence_1"]}],
        })
        raw = valid + "}"
        client = MagicMock()
        response = MagicMock()
        response.choices[0].message.content = raw
        client.create.return_value = response

        result = evaluate_groundedness(
            client, "q", "A staging padroniza nomes e tipos.", [_chunk()], [], "endpoint"
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.raw_output, raw)
        self.assertEqual(
            result.structured_output["output_normalization"],
            "removed_single_trailing_closing_brace",
        )

    def test_non_exact_extra_data_suffixes_are_rejected(self):
        valid = json.dumps({
            "claims": [{"claim_id": "claim_1", "verdict": "unsupported",
                        "evidence_ids": []}],
        })
        suffixes = ("}}", " trailing text", ' {"claims": []}')
        for suffix in suffixes:
            with self.subTest(suffix=suffix):
                client = MagicMock()
                response = MagicMock()
                response.choices[0].message.content = valid + suffix
                client.create.return_value = response
                result = evaluate_groundedness(client, "q", "claim", [_chunk()], [], "endpoint")
                self.assertEqual(result.status, "invalid_output")
                self.assertEqual(result.raw_output, valid + suffix)

    def test_unsupported_claim(self):
        result = self._evaluate({
            "claims": [{"claim_id": "claim_1", "verdict": "unsupported", "evidence_ids": []}],
        }, "A carga ocorre a cada minuto.")
        self.assertFalse(result.grounded)
        self.assertEqual(result.unsupported_claims, 1)

    def test_contradicted_claim(self):
        result = self._evaluate({
            "claims": [{"claim_id": "claim_1", "verdict": "contradicted",
                        "evidence_ids": ["evidence_1"]}],
        }, "A staging preserva nomes.")
        self.assertEqual(result.contradicted_claims, 1)

    def test_multiple_claims_score_and_grounded_are_calculated(self):
        result = self._evaluate({
            "claims": [
                {"claim_id": "claim_1", "verdict": "supported",
                 "evidence_ids": ["evidence_1"]},
                {"claim_id": "claim_2", "verdict": "unsupported", "evidence_ids": []},
            ],
        }, "Padroniza nomes. Executa a cada minuto.")
        self.assertEqual((result.supported_claims, result.unsupported_claims), (1, 1))
        self.assertEqual(result.groundedness_score, 0.5)

    def test_invalid_or_incomplete_json_is_auditable(self):
        for raw in ("not-json", json.dumps({"claims": []})):
            client = MagicMock()
            response = MagicMock()
            response.choices[0].message.content = raw
            client.create.return_value = response
            result = evaluate_groundedness(client, "q", "a", [_chunk()], [], "endpoint")
            self.assertEqual(result.status, "invalid_output")
            self.assertIsNone(result.grounded)

    def test_timeout_and_endpoint_error_are_not_grounded(self):
        for exception, status in ((TimeoutError("late"), "timeout"), (RuntimeError("down"), "endpoint_error")):
            result = evaluate_groundedness(
                _client(exception=exception), "q", "a", [_chunk()], [], "endpoint"
            )
            self.assertEqual(result.status, status)
            self.assertIsNone(result.grounded)

    def test_unknown_duplicate_or_missing_evidence_id_is_rejected(self):
        raw = json.dumps({
            "claims": [{"claim_id": "claim_1", "verdict": "supported",
                        "evidence_ids": ["evidence_99"]}],
        })
        with self.assertRaisesRegex(ValueError, "unknown evidence_id"):
            validate_judge_output(raw, "x", [_chunk()])
        duplicate = json.dumps({
            "claims": [{"claim_id": "claim_1", "verdict": "supported",
                        "evidence_ids": ["evidence_1", "evidence_1"]}],
        })
        with self.assertRaisesRegex(ValueError, "contains duplicates"):
            validate_judge_output(duplicate, "x", [_chunk()])
        missing = json.dumps({
            "claims": [{"claim_id": "claim_1", "verdict": "supported", "evidence_ids": []}],
        })
        with self.assertRaisesRegex(ValueError, "requires evidence"):
            validate_judge_output(missing, "x", [_chunk()])

    def test_unknown_claim_id_cannot_introduce_a_claim_from_context(self):
        raw = json.dumps({
            "claims": [{"claim_id": "claim_99", "verdict": "supported",
                        "evidence_ids": ["evidence_1"]}],
        })
        with self.assertRaisesRegex(ValueError, "claim_id is unknown"):
            validate_judge_output(raw, "A staging padroniza os dados.", [_chunk()])

    def test_rag_008_and_rag_019_use_valid_evidence_ids_without_markdown_copy(self):
        for answer, verdict in (
            ("Os testes validam relacionamentos.", "supported"),
            ("A cotação PTAX é proveniente do SQL Server.", "contradicted"),
        ):
            result = self._evaluate({
                "claims": [{"claim_id": "claim_1", "verdict": verdict,
                            "evidence_ids": ["evidence_1"]}],
            }, answer)
            self.assertEqual(result.status, "completed")
            self.assertEqual(result.claims[0].evidence[0].evidence_id, "evidence_1")
            self.assertIn("evidence_catalog", result.structured_output)

    def test_all_claim_ids_are_required_once(self):
        answer = "Primeiro fato. Segundo fato."
        base = {
            "verdict": "unsupported",
            "evidence_ids": [],
        }
        missing = json.dumps({
            "claims": [{"claim_id": "claim_1", **base}],
        })
        duplicate = json.dumps({
            "claims": [{"claim_id": "claim_1", **base}, {"claim_id": "claim_1", **base}],
        })
        with self.assertRaisesRegex(ValueError, "did not evaluate all claim IDs"):
            validate_judge_output(missing, answer, [_chunk()])
        with self.assertRaisesRegex(ValueError, "claim_id is duplicated"):
            validate_judge_output(duplicate, answer, [_chunk()])

    def test_rag_003_mixed_supported_fact_and_inference_is_unsupported(self):
        answer = (
            "A dimensão não é explicitamente mencionada nos documentos, mas inferida e pode "
            "ser ligada ao estoque via uma chave estrangeira."
        )
        result = self._evaluate({
            "claims": [{"claim_id": "claim_1", "verdict": "unsupported", "evidence_ids": []}],
        }, answer)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.unsupported_claims, 1)
        self.assertFalse(result.grounded)

    def test_prompt_contains_only_allowed_user_input(self):
        messages = build_judge_messages(
            "q", "a", [_chunk()], [ExpectedSource("docs/staging.md", "Objetivo")]
        )
        payload = json.loads(messages[1]["content"])
        self.assertEqual(set(payload), {"question", "claims", "evidence_candidates", "citations"})
        self.assertEqual(payload["claims"], [{"id": "claim_1", "text": "a"}])
        self.assertEqual(
            set(payload["evidence_candidates"][0]),
            {"evidence_id", "document", "section", "content"},
        )
        self.assertIn("Nao use conhecimento externo", messages[0]["content"])


if __name__ == "__main__":
    unittest.main()
