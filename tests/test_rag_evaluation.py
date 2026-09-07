import json
import tempfile
import unittest
import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.analytics_ai.rag_evaluation import (
    DatasetValidationError,
    EvaluationObservation,
    ExpectedSource,
    append_remote_results,
    classify_remote_result,
    coverage_report,
    evaluate_cases,
    load_golden_dataset,
    parse_citations,
    run_remote_evaluation,
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


class RemoteRagEvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_golden_dataset(DATASET_PATH, REPOSITORY_ROOT)

    @staticmethod
    def _now():
        return datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)

    def test_smoke_and_full_selection_execute_inside_one_runner(self):
        calls = []

        def executor(case):
            calls.append(case.id)
            return EvaluationObservation("answer", "resposta")

        smoke = run_remote_evaluation(
            self.cases, "smoke", executor, "run-smoke", now=self._now
        )
        self.assertEqual(smoke.total, 10)
        self.assertEqual(len(calls), 10)
        calls.clear()
        full = run_remote_evaluation(
            self.cases, "full", executor, "run-full", now=self._now
        )
        self.assertEqual(full.total, 30)
        self.assertEqual(len(calls), 30)

    def test_special_behaviors_are_classified_deterministically(self):
        from src.analytics_ai.rag_prompt import (
            ADVERSARIAL_RESPONSE,
            DATA_WAREHOUSE_RESPONSE,
            NO_DOCUMENTATION_RESPONSE,
        )

        answers = {
            "refuse_warehouse_data": DATA_WAREHOUSE_RESPONSE,
            "insufficient_context": NO_DOCUMENTATION_RESPONSE,
            "refuse_adversarial": ADVERSARIAL_RESPONSE,
        }
        for behavior, answer in answers.items():
            with self.subTest(behavior=behavior):
                case = next(case for case in self.cases if case.expected_behavior == behavior)
                result = classify_remote_result(
                    case, EvaluationObservation("unclassified", answer),
                    "run", self._now().isoformat(), "full",
                )
                self.assertEqual(result.status, "passed")
                self.assertEqual(result.observed_behavior, behavior)

    def test_insufficient_context_accepts_only_accent_case_and_space_variation(self):
        case = next(case for case in self.cases if case.id == "rag_025")
        accented = (
            "  A DOCUMENTAÇÃO provida para consulta não dispõe de informações "
            "suficientes para responder a esta questão.  "
        )
        accepted = classify_remote_result(
            case, EvaluationObservation("unclassified", accented),
            "run", self._now().isoformat(), "smoke",
        )
        different = classify_remote_result(
            case, EvaluationObservation("unclassified", accented + " Consulte o suporte."),
            "run", self._now().isoformat(), "smoke",
        )

        self.assertEqual(accepted.status, "passed")
        self.assertEqual(different.status, "failed")

    def test_wrong_special_refusal_fails(self):
        case = next(
            case for case in self.cases if case.expected_behavior == "refuse_warehouse_data"
        )
        result = classify_remote_result(
            case, EvaluationObservation("unclassified", "42"),
            "run", self._now().isoformat(), "full",
        )
        self.assertEqual(result.status, "failed")
        self.assertIn("warehouse_refusal_mismatch", result.failure_reasons)

    def test_parser_accepts_canonical_citation_without_brackets(self):
        self.assertEqual(
            parse_citations("Fonte: docs/staging.md - Secao: Componentes"),
            (ExpectedSource("docs/staging.md", "Componentes"),),
        )

    def test_parser_keeps_compatibility_with_bracketed_citation(self):
        self.assertEqual(
            parse_citations("Fonte: [docs/staging.md] - Seção: Objetivo"),
            (ExpectedSource("docs/staging.md", "Objetivo"),),
        )

    def test_technical_answer_with_evidence_needs_human_review(self):
        case = self.cases[0]
        source = case.expected_sources[0]
        answer = f"Resposta. Fonte: {source.path} - Secao: {source.section}"
        result = classify_remote_result(
            case,
            EvaluationObservation("unclassified", answer, (source,), parse_citations(answer), 0.2),
            "run", self._now().isoformat(), "full",
        )
        self.assertEqual(result.status, "needs_review")
        self.assertEqual(result.failure_reasons, ())
        self.assertIn("technical_facts_require_human_review", result.review_reasons)

    def test_plausible_alternative_source_is_not_automatically_failed(self):
        case = self.cases[0]
        alternative = ExpectedSource("docs/staging.md", "Componentes")
        answer = "Resposta. Fonte: [docs/staging.md] - Secao: Componentes"
        result = classify_remote_result(
            case,
            EvaluationObservation("unclassified", answer, (alternative,), (), 0.2),
            "run", self._now().isoformat(), "full",
        )
        self.assertEqual(result.status, "needs_review")
        self.assertIn(
            "expected_source_missing_but_plausible_editorial_source_retrieved",
            result.review_reasons,
        )

    def test_one_case_exception_does_not_interrupt_suite(self):
        selected = select_suite(self.cases, "smoke")
        calls = []

        def executor(case):
            calls.append(case.id)
            if len(calls) == 1:
                raise RuntimeError("simulated")
            return EvaluationObservation("answer", "resposta")

        summary = run_remote_evaluation(
            self.cases, "smoke", executor, "run", now=self._now
        )
        self.assertEqual(len(calls), len(selected))
        self.assertEqual(summary.total, 10)
        self.assertEqual(summary.results[0].observed_behavior, "execution_error")
        self.assertEqual(summary.results[0].status, "failed")

    def test_summary_counts_statuses_and_latency(self):
        special = [
            case for case in self.cases
            if case.expected_behavior in {"refuse_warehouse_data", "insufficient_context"}
        ][:2]
        from src.analytics_ai.rag_prompt import DATA_WAREHOUSE_RESPONSE, NO_DOCUMENTATION_RESPONSE
        answers = {
            "refuse_warehouse_data": DATA_WAREHOUSE_RESPONSE,
            "insufficient_context": NO_DOCUMENTATION_RESPONSE,
        }
        summary = run_remote_evaluation(
            special,
            "full",
            lambda case: EvaluationObservation(
                "unclassified", answers[case.expected_behavior], latency_seconds=0.5
            ),
            "run",
            now=self._now,
        )
        self.assertEqual((summary.total, summary.passed, summary.failed), (2, 2, 0))
        self.assertEqual(summary.deterministic_pass_rate, 1.0)
        self.assertEqual(summary.mean_latency_seconds, 0.5)

    def test_report_persistence_is_append_only(self):
        case = next(
            case for case in self.cases if case.expected_behavior == "insufficient_context"
        )
        from src.analytics_ai.rag_prompt import NO_DOCUMENTATION_RESPONSE
        result = classify_remote_result(
            case, EvaluationObservation("unclassified", NO_DOCUMENTATION_RESPONSE),
            "run", self._now().isoformat(), "full",
        )
        spark = MagicMock()
        dataframe = spark.createDataFrame.return_value
        selected = dataframe.select.return_value
        writer = selected.write.format.return_value.mode.return_value

        self.assertEqual(
            append_remote_results(spark, "dev_lh_nautical.rag.rag_evaluation_results", [result]),
            1,
        )
        selected.write.format.assert_called_once_with("delta")
        selected.write.format.return_value.mode.assert_called_once_with("append")
        writer.saveAsTable.assert_called_once_with(
            "dev_lh_nautical.rag.rag_evaluation_results"
        )

    def test_remote_entrypoint_parses_explicit_dataset_without_dunder_file(self):
        from src.analytics_ai import run_rag_evaluation

        sentinel = run_rag_evaluation.__dict__.pop("__file__", None)
        arguments = [
            "run_rag_evaluation.py",
            "--index-name", "catalog.schema.index",
            "--endpoint-name", "endpoint",
            "--report-table", "catalog.schema.report",
            "--dataset", "/Workspace/bundle/files/evaluation/rag_golden_dataset.jsonl",
        ]
        try:
            with patch.object(sys, "argv", arguments):
                parsed = run_rag_evaluation.parse_args()
        finally:
            if sentinel is not None:
                run_rag_evaluation.__dict__["__file__"] = sentinel

        self.assertEqual(
            parsed.dataset,
            Path("/Workspace/bundle/files/evaluation/rag_golden_dataset.jsonl"),
        )


if __name__ == "__main__":
    unittest.main()
