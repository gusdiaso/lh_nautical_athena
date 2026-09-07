import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.analytics_ai.rag_evaluation import (
    DatasetValidationError,
    EvaluationObservation,
    ExpectedSource,
    coverage_report,
    evaluate_cases,
    load_golden_dataset,
    select_suite,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = REPOSITORY_ROOT / "evaluation" / "rag_golden_dataset.jsonl"


class RagEvaluationDatasetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_golden_dataset(DATASET_PATH, REPOSITORY_ROOT)

    def test_dataset_schema_sources_sections_and_composition_are_valid(self):
        self.assertEqual(len(self.cases), 30)
        self.assertEqual(len({case.id for case in self.cases}), 30)

    def test_suite_selection_has_ten_smoke_and_all_full_cases(self):
        self.assertEqual(len(select_suite(self.cases, "smoke")), 10)
        self.assertEqual(len(select_suite(self.cases, "full")), 30)

    def test_behavior_composition_matches_initial_plan(self):
        behaviors = {behavior: sum(case.expected_behavior == behavior for case in self.cases) for behavior in {
            "answer", "insufficient_context", "refuse_warehouse_data", "refuse_adversarial"
        }}
        self.assertEqual(behaviors, {
            "answer": 24,
            "insufficient_context": 3,
            "refuse_warehouse_data": 2,
            "refuse_adversarial": 1,
        })

    def test_primary_category_composition_matches_requested_mix(self):
        expected = {
            "technical_focused": 12,
            "troubleshooting": 6,
            "synthesis": 6,
            "insufficient_context": 3,
            "warehouse_refusal": 2,
            "adversarial": 1,
        }
        self.assertEqual(
            {category: sum(case.category == category for case in self.cases) for category in expected},
            expected,
        )

    def test_answer_cases_have_atomic_facts_and_expected_sources(self):
        for case in self.cases:
            if case.expected_behavior == "answer":
                self.assertTrue(case.expected_facts, case.id)
                self.assertTrue(case.expected_sources, case.id)
                self.assertTrue(all(len(fact) <= 180 for fact in case.expected_facts), case.id)

    def test_coverage_report_exposes_requested_dimensions(self):
        report = coverage_report(self.cases, REPOSITORY_ROOT)
        self.assertEqual(report["total_cases"], 30)
        self.assertEqual(report["by_suite"], {"full": 30, "smoke": 10})
        self.assertIn("single_document", report["by_scope"])
        self.assertIn("multi_document", report["by_scope"])
        self.assertIn("documents_used", report)
        self.assertIn("allowlist_documents_not_covered", report)

    def test_invalid_json_is_reported_with_line_number(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.jsonl"
            path.write_text("{not-json}\n", encoding="utf-8")
            with self.assertRaisesRegex(DatasetValidationError, "line 1: invalid JSON"):
                load_golden_dataset(path, REPOSITORY_ROOT, expected_count=0)

    def test_duplicate_id_and_question_are_rejected(self):
        first = json.loads(DATASET_PATH.read_text(encoding="utf-8").splitlines()[0])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicates.jsonl"
            line = json.dumps(first, ensure_ascii=False)
            path.write_text(f"{line}\n{line}\n", encoding="utf-8")
            with self.assertRaises(DatasetValidationError) as context:
                load_golden_dataset(path, REPOSITORY_ROOT, expected_count=2)
        message = str(context.exception)
        self.assertIn("duplicate IDs", message)
        self.assertIn("exact duplicate questions", message)

    def test_source_outside_allowlist_is_rejected(self):
        first = json.loads(DATASET_PATH.read_text(encoding="utf-8").splitlines()[0])
        first["expectations"]["expected_sources"][0]["path"] = "docs/rag_mvp.md"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outside.jsonl"
            path.write_text(json.dumps(first, ensure_ascii=False) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(DatasetValidationError, "outside the RAG allowlist"):
                load_golden_dataset(path, REPOSITORY_ROOT, expected_count=1)

    def test_missing_required_field_is_rejected(self):
        first = json.loads(DATASET_PATH.read_text(encoding="utf-8").splitlines()[0])
        del first["expectations"]["forbidden_claims"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.jsonl"
            path.write_text(json.dumps(first, ensure_ascii=False) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(DatasetValidationError, "missing required fields"):
                load_golden_dataset(path, REPOSITORY_ROOT, expected_count=1)

    def test_unknown_section_is_rejected(self):
        first = json.loads(DATASET_PATH.read_text(encoding="utf-8").splitlines()[0])
        first["expectations"]["expected_sources"][0]["section"] = "Secao inexistente"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "section.jsonl"
            path.write_text(json.dumps(first, ensure_ascii=False) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(DatasetValidationError, "does not exist"):
                load_golden_dataset(path, REPOSITORY_ROOT, expected_count=1)

    def test_editorial_section_is_valid_even_when_chunk_metadata_mismatches(self):
        with patch(
            "src.analytics_ai.rag_evaluation._generated_document_sections",
            return_value={},
        ):
            report = coverage_report(self.cases, REPOSITORY_ROOT)
        self.assertIn({
            "case_id": "rag_001",
            "path": "docs/staging.md",
            "expected_editorial_section": "Objetivo",
            "diagnostic": "section_metadata_mismatch",
        }, report["section_metadata_mismatch"])

    def test_corrected_corpus_has_no_section_metadata_mismatches(self):
        report = coverage_report(self.cases, REPOSITORY_ROOT)

        self.assertEqual(report["section_metadata_mismatch"], [])

    def test_section_without_sanitized_textual_evidence_is_rejected(self):
        first = json.loads(DATASET_PATH.read_text(encoding="utf-8").splitlines()[0])
        first["expectations"]["expected_sources"][0] = {
            "path": "docs/orquestracao_transform.md",
            "section": "Jobs e Tasks",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty-editorial-section.jsonl"
            path.write_text(json.dumps(first, ensure_ascii=False) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(DatasetValidationError, "has no textual evidence"):
                load_golden_dataset(path, REPOSITORY_ROOT, expected_count=1)

    def test_evaluator_separates_retrieval_from_semantic_generation_review(self):
        answer_case = self.cases[0]
        expected = answer_case.expected_sources

        summary = evaluate_cases(
            [answer_case],
            lambda case: EvaluationObservation(
                behavior="answer",
                answer="Resposta que ainda precisa de revisão semântica.",
                retrieved_sources=expected,
                cited_sources=expected,
                latency_seconds=0.25,
            ),
        )

        result = summary.results[0]
        self.assertTrue(result.retrieval_passed)
        self.assertEqual(result.generation_review, "human_or_llm_judge_required")
        self.assertTrue(all(value is None for value in result.fact_coverage.values()))
        self.assertIsNone(result.passed)
        self.assertEqual(summary.needs_review, 1)

    def test_evaluator_detects_missing_retrieval_source(self):
        case = next(case for case in self.cases if case.scope == "multi_document")
        summary = evaluate_cases(
            [case],
            lambda _: EvaluationObservation("answer", "Resposta", (), (), 0.1),
        )
        self.assertFalse(summary.results[0].retrieval_passed)
        self.assertFalse(summary.results[0].passed)

    def test_evaluator_scores_refusal_behavior_deterministically(self):
        case = next(case for case in self.cases if case.expected_behavior == "refuse_warehouse_data")
        summary = evaluate_cases(
            [case],
            lambda _: EvaluationObservation("refuse_warehouse_data", "Recusa", latency_seconds=0.1),
        )
        self.assertTrue(summary.results[0].refusal_passed)
        self.assertTrue(summary.results[0].passed)


if __name__ == "__main__":
    unittest.main()
