import json
import unittest

from src.analytics_ai.rag_documents import Chunk
from src.analytics_ai.rag_evaluation import ExpectedSource, parse_citations
from src.analytics_ai.rag_generation import check_citations, parse_citation_pairs
from src.analytics_ai.rag_operations import (
    STATUS_DEGRADED,
    STATUS_HEALTHY,
    STATUS_VIOLATED,
    IndexState,
    IsolationProbe,
    RetrievalProbe,
    RowCountDrift,
    build_health_report,
    count_table_rows,
    describe_index_state,
    health_report_row,
    probe_retrieval,
    probe_warehouse_isolation,
    should_fail,
    warehouse_schemas,
)

READY_DESCRIPTION = {
    "status": {"ready": True, "detailed_state": "ONLINE_NO_PENDING_UPDATE", "indexed_row_count": 224},
    "delta_sync_index_spec": {
        "source_table": "dev_lh_nautical.rag.document_chunks",
        "pipeline_type": "TRIGGERED",
    },
}


class FakeIndex:
    def __init__(self, description=None, rows=None, error=None):
        self._description = description
        self._rows = rows or []
        self._error = error

    def describe(self):
        if self._error:
            raise RuntimeError(self._error)
        return self._description

    def similarity_search(self, **kwargs):
        if self._error:
            raise RuntimeError(self._error)
        return {
            "manifest": {
                "columns": [
                    {"name": "source_path"},
                    {"name": "file_name"},
                    {"name": "section"},
                    {"name": "content"},
                ]
            },
            "result": {"data_array": self._rows},
        }


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def collect(self):
        return self._rows


class FakeClock:
    def __init__(self, steps):
        self._steps = list(steps)

    def __call__(self):
        return self._steps.pop(0)


def _chunk(source_path="docs/staging.md", section="Objetivo"):
    return Chunk(
        "id", source_path, source_path.split("/")[-1], "markdown", section,
        "conteudo", "hash", "date", "approved",
    )


class RagIndexStateTest(unittest.TestCase):
    def test_ready_description_is_parsed(self):
        state = describe_index_state(FakeIndex(READY_DESCRIPTION), "endpoint", "index")

        self.assertTrue(state.ready)
        self.assertEqual(state.detailed_state, "ONLINE_NO_PENDING_UPDATE")
        self.assertEqual(state.indexed_row_count, 224)
        self.assertEqual(state.source_table, "dev_lh_nautical.rag.document_chunks")
        self.assertEqual(state.pipeline_type, "TRIGGERED")
        self.assertIsNone(state.error)

    def test_string_values_from_the_sdk_are_coerced(self):
        description = {"status": {"ready": "true", "indexed_row_count": "224"}}

        state = describe_index_state(FakeIndex(description), "endpoint", "index")

        self.assertTrue(state.ready)
        self.assertEqual(state.indexed_row_count, 224)

    def test_unknown_shape_keeps_fields_none_instead_of_guessing(self):
        state = describe_index_state(FakeIndex({"unexpected": "shape"}), "endpoint", "index")

        self.assertIsNone(state.ready)
        self.assertIsNone(state.indexed_row_count)
        self.assertIsNone(state.source_table)

    def test_describe_failure_is_reported_not_raised(self):
        state = describe_index_state(FakeIndex(error="index unavailable"), "endpoint", "index")

        self.assertIn("index unavailable", state.error)
        self.assertIsNone(state.ready)

    def test_client_without_describe_is_reported(self):
        state = describe_index_state(object(), "endpoint", "index")

        self.assertEqual(state.error, "index client does not provide describe")


class RagRowCountTest(unittest.TestCase):
    def test_count_returns_the_first_column(self):
        rows = count_table_rows(lambda statement: FakeResult([[224]]), "cat.rag.chunks")

        self.assertEqual(rows, 224)

    def test_count_failure_returns_none(self):
        def failing(statement):
            raise RuntimeError("table not found")

        self.assertIsNone(count_table_rows(failing, "cat.rag.chunks"))

    def test_invalid_table_identifier_is_rejected(self):
        with self.assertRaises(ValueError):
            count_table_rows(lambda statement: FakeResult([[1]]), "rag.chunks")

    def test_drift_is_none_when_a_side_is_unknown(self):
        self.assertIsNone(RowCountDrift(None, 224).drift)
        self.assertIsNone(RowCountDrift(None, 224).aligned)
        self.assertEqual(RowCountDrift(230, 224).drift, 6)
        self.assertFalse(RowCountDrift(230, 224).aligned)
        self.assertTrue(RowCountDrift(224, 224).aligned)


class RagRetrievalProbeTest(unittest.TestCase):
    def test_probe_measures_latency_and_deduplicates_sources(self):
        rows = [
            ["docs/staging.md", "staging.md", "Objetivo", "conteudo"],
            ["docs/staging.md", "staging.md", "Objetivo", "outro trecho"],
            ["docs/marts.md", "marts.md", "Fluxo", "conteudo"],
        ]

        probe = probe_retrieval(
            FakeIndex(rows=rows), "Como funciona a camada staging?", 3, clock=FakeClock([1.0, 2.5])
        )

        self.assertEqual(probe.chunk_count, 3)
        self.assertEqual(
            probe.sources, (("docs/staging.md", "Objetivo"), ("docs/marts.md", "Fluxo"))
        )
        self.assertAlmostEqual(probe.latency_seconds, 1.5)
        self.assertFalse(probe.refused)
        self.assertIsNone(probe.error)

    def test_warehouse_question_is_refused_before_the_index(self):
        probe = probe_retrieval(
            FakeIndex(rows=[]), "Qual foi o faturamento total de vendas em 2024?", 3
        )

        self.assertTrue(probe.refused)
        self.assertEqual(probe.chunk_count, 0)

    def test_retrieval_failure_is_reported_not_raised(self):
        probe = probe_retrieval(FakeIndex(error="endpoint offline"), "Como funciona o dbt?", 3)

        self.assertIn("endpoint offline", probe.error)
        self.assertEqual(probe.chunk_count, 0)


class RagIsolationProbeTest(unittest.TestCase):
    def test_permission_error_proves_isolation(self):
        def denied(statement):
            raise RuntimeError("PERMISSION_DENIED: User does not have USE SCHEMA on Schema 'gold'")

        probes = probe_warehouse_isolation(denied, ["cat.gold"])

        self.assertEqual(len(probes), 1)
        self.assertTrue(probes[0].blocked)
        self.assertEqual(probes[0].statement, "SHOW TABLES IN cat.gold")

    def test_successful_statement_is_a_violation(self):
        probes = probe_warehouse_isolation(lambda statement: FakeResult([["gold", "dim_customers"]]), ["cat.gold"])

        self.assertFalse(probes[0].blocked)

    def test_non_permission_error_stays_inconclusive(self):
        def flaky(statement):
            raise RuntimeError("connection reset by peer")

        probes = probe_warehouse_isolation(flaky, ["cat.gold"])

        self.assertIsNone(probes[0].blocked)
        self.assertIn("connection reset", probes[0].error)

    def test_lazy_results_are_collected_so_the_privilege_is_exercised(self):
        collected = []

        class LazyResult:
            def collect(self):
                collected.append(True)
                raise RuntimeError("PERMISSION_DENIED on collect")

        probes = probe_warehouse_isolation(lambda statement: LazyResult(), ["cat.gold"])

        self.assertEqual(collected, [True])
        self.assertTrue(probes[0].blocked)

    def test_invalid_schema_identifier_is_rejected(self):
        with self.assertRaises(ValueError):
            probe_warehouse_isolation(lambda statement: FakeResult([]), ["gold; DROP TABLE x"])

    def test_schemas_inherit_the_catalog_only_when_unqualified(self):
        self.assertEqual(
            warehouse_schemas("dev_lh_nautical", ["bronze", "other.gold"]),
            ("dev_lh_nautical.bronze", "other.gold"),
        )


class RagHealthReportTest(unittest.TestCase):
    def _healthy_parts(self):
        index = IndexState("endpoint", "index", True, "ONLINE_NO_PENDING_UPDATE", 224, "cat.rag.chunks", "TRIGGERED")
        rows = RowCountDrift(224, 224)
        probe = RetrievalProbe("Como funciona o dbt?", 3, (("docs/staging.md", "Objetivo"),), 1.2)
        isolation = (
            IsolationProbe("cat.bronze", "SHOW TABLES IN cat.bronze", True, "PERMISSION_DENIED"),
            IsolationProbe("cat.gold", "SHOW TABLES IN cat.gold", True, "PERMISSION_DENIED"),
        )
        return index, rows, probe, isolation

    def test_all_signals_green_is_healthy(self):
        report = build_health_report(*self._healthy_parts())

        self.assertEqual(report.status, STATUS_HEALTHY)
        self.assertEqual(report.reasons, ())

    def test_reachable_warehouse_dominates_every_other_signal(self):
        index, rows, probe, _ = self._healthy_parts()
        isolation = (IsolationProbe("cat.gold", "SHOW TABLES IN cat.gold", False),)

        report = build_health_report(index, rows, probe, isolation)

        self.assertEqual(report.status, STATUS_VIOLATED)
        self.assertIn("warehouse isolation is broken for cat.gold", report.reasons)

    def test_inconclusive_isolation_is_degraded_not_healthy(self):
        index, rows, probe, _ = self._healthy_parts()
        isolation = (IsolationProbe("cat.gold", "SHOW TABLES IN cat.gold", None, "timeout"),)

        report = build_health_report(index, rows, probe, isolation)

        self.assertEqual(report.status, STATUS_DEGRADED)

    def test_missing_isolation_probe_is_degraded(self):
        index, rows, probe, _ = self._healthy_parts()

        report = build_health_report(index, rows, probe, ())

        self.assertEqual(report.status, STATUS_DEGRADED)
        self.assertIn("warehouse isolation was not probed", report.reasons)

    def test_row_drift_and_unready_index_are_degraded(self):
        _, _, probe, isolation = self._healthy_parts()
        index = IndexState("endpoint", "index", False, "PROVISIONING", 200)

        report = build_health_report(index, RowCountDrift(224, 200), probe, isolation)

        self.assertEqual(report.status, STATUS_DEGRADED)
        self.assertIn("index is not ready (PROVISIONING)", report.reasons)
        self.assertTrue(any("row count drift of 24" in reason for reason in report.reasons))

    def test_empty_probe_is_degraded(self):
        index, rows, _, isolation = self._healthy_parts()
        probe = RetrievalProbe("Como funciona o dbt?", 0, (), 0.4)

        report = build_health_report(index, rows, probe, isolation)

        self.assertEqual(report.status, STATUS_DEGRADED)
        self.assertIn("retrieval probe returned no chunks", report.reasons)

    def test_report_row_flattens_diagnostics_for_delta(self):
        report = build_health_report(*self._healthy_parts())

        row = health_report_row(report, "run-1", "2026-09-10T00:00:00+00:00", "checkpoint")

        self.assertEqual(row["status"], STATUS_HEALTHY)
        self.assertEqual(row["run_label"], "checkpoint")
        self.assertEqual(row["table_rows"], 224)
        self.assertEqual(row["row_count_drift"], 0)
        self.assertEqual(row["isolation_violations"], 0)
        self.assertEqual(row["isolation_inconclusive"], 0)
        self.assertEqual(
            json.loads(row["probe_sources_json"]),
            [{"document": "docs/staging.md", "section": "Objetivo"}],
        )
        self.assertEqual(len(json.loads(row["isolation_probes_json"])), 2)

    def test_fail_on_severity_matrix(self):
        self.assertTrue(should_fail(STATUS_VIOLATED, STATUS_VIOLATED))
        self.assertFalse(should_fail(STATUS_DEGRADED, STATUS_VIOLATED))
        self.assertTrue(should_fail(STATUS_DEGRADED, STATUS_DEGRADED))
        self.assertFalse(should_fail(STATUS_HEALTHY, STATUS_DEGRADED))
        self.assertFalse(should_fail(STATUS_VIOLATED, "never"))
        with self.assertRaises(ValueError):
            should_fail(STATUS_HEALTHY, "sometimes")


class RagCitationCheckTest(unittest.TestCase):
    def test_citations_of_retrieved_chunks_are_valid(self):
        answer = "Resposta documental.\n\nFonte: docs/staging.md - Secao: Objetivo"

        check = check_citations(answer, [_chunk()])

        self.assertEqual(check.cited, (("docs/staging.md", "Objetivo"),))
        self.assertEqual(check.not_retrieved, ())
        self.assertTrue(check.valid)

    def test_citation_outside_the_context_is_flagged(self):
        answer = "Resposta.\n\nFonte: docs/marts.md - Secao: Fluxo"

        check = check_citations(answer, [_chunk()])

        self.assertEqual(check.not_retrieved, (("docs/marts.md", "Fluxo"),))
        self.assertFalse(check.valid)

    def test_answer_without_citations_is_not_valid(self):
        check = check_citations("Resposta sem fonte.", [_chunk()])

        self.assertEqual(check.cited, ())
        self.assertFalse(check.valid)

    def test_pairs_are_deduplicated_and_trimmed(self):
        answer = (
            "Fonte: docs/staging.md - Secao: Objetivo.\n"
            "Fonte: docs/staging.md - Seção: Objetivo\n"
        )

        self.assertEqual(parse_citation_pairs(answer), (("docs/staging.md", "Objetivo"),))

    def test_evaluation_contract_still_returns_expected_sources(self):
        answer = "Fonte: docs/staging.md - Secao: Objetivo"

        self.assertEqual(
            parse_citations(answer), (ExpectedSource("docs/staging.md", "Objetivo"),)
        )


if __name__ == "__main__":
    unittest.main()
