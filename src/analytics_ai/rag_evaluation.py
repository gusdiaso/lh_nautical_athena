"""Offline validation, coverage reporting, and result contracts for RAG evaluation."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterable, Mapping, Sequence

from .rag_documents import DEFAULT_ALLOWED_PATHS, Chunk, build_chunks, load_documents, parse_content

EXPECTED_BEHAVIORS = frozenset(
    {"answer", "insufficient_context", "refuse_warehouse_data", "refuse_adversarial"}
)
DIFFICULTIES = frozenset({"medium", "hard"})
SCOPES = frozenset({"single_document", "multi_document", "out_of_scope", "adversarial"})
PRIMARY_CATEGORIES = frozenset(
    {
        "technical_focused",
        "troubleshooting",
        "synthesis",
        "insufficient_context",
        "warehouse_refusal",
        "adversarial",
    }
)
MINIMUM_CATEGORY_COUNTS = {
    "technical_focused": 12,
    "troubleshooting": 6,
    "synthesis": 6,
    "insufficient_context": 3,
    "warehouse_refusal": 2,
    "adversarial": 1,
}
ANSWER_BEHAVIOR = "answer"


class DatasetValidationError(ValueError):
    """Raised when one or more Golden Dataset invariants are violated."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(errors)
        super().__init__("Golden Dataset is invalid:\n- " + "\n- ".join(self.errors))


@dataclass(frozen=True)
class ExpectedSource:
    path: str
    section: str


@dataclass(frozen=True)
class GoldenCase:
    id: str
    question: str
    expected_behavior: str
    expected_facts: tuple[str, ...]
    expected_sources: tuple[ExpectedSource, ...]
    forbidden_claims: tuple[str, ...]
    category: str
    difficulty: str
    suite: tuple[str, ...]
    scope: str
    rationale: str


@dataclass(frozen=True)
class EvaluationObservation:
    """Provider-neutral output captured from a future local or remote runner."""

    behavior: str
    answer: str
    retrieved_sources: tuple[ExpectedSource, ...] = ()
    cited_sources: tuple[ExpectedSource, ...] = ()
    latency_seconds: float = 0.0


@dataclass(frozen=True)
class CaseEvaluationResult:
    case_id: str
    expected_behavior: str
    observed_behavior: str
    answer: str
    retrieved_sources: tuple[ExpectedSource, ...]
    expected_sources_present: tuple[ExpectedSource, ...]
    expected_sources_missing: tuple[ExpectedSource, ...]
    cited_sources: tuple[ExpectedSource, ...]
    fact_coverage: Mapping[str, bool | None]
    latency_seconds: float
    retrieval_passed: bool
    refusal_passed: bool | None
    generation_review: str
    passed: bool | None


@dataclass(frozen=True)
class EvaluationSummary:
    total: int
    passed: int
    failed: int
    needs_review: int
    mean_latency_seconds: float
    results: tuple[CaseEvaluationResult, ...] = field(repr=False)


def _required_mapping(value: Any, name: str, errors: list[str], case_ref: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{case_ref}: {name} must be an object")
        return {}
    return value


def _string_list(value: Any, name: str, errors: list[str], case_ref: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        errors.append(f"{case_ref}: {name} must be a list of non-empty strings")
        return ()
    return tuple(item.strip() for item in value)


def _parse_case(raw: Any, line_number: int, errors: list[str]) -> GoldenCase | None:
    case_ref = f"line {line_number}"
    if not isinstance(raw, dict):
        errors.append(f"{case_ref}: each line must contain a JSON object")
        return None
    inputs = _required_mapping(raw.get("inputs"), "inputs", errors, case_ref)
    expectations = _required_mapping(raw.get("expectations"), "expectations", errors, case_ref)
    metadata = _required_mapping(raw.get("metadata"), "metadata", errors, case_ref)
    required_keys = {
        "inputs": ({"question"}, inputs),
        "expectations": (
            {"expected_behavior", "expected_facts", "expected_sources", "forbidden_claims"},
            expectations,
        ),
        "metadata": ({"category", "difficulty", "suite", "scope", "rationale"}, metadata),
    }
    for group, (required, values) in required_keys.items():
        missing = sorted(required - values.keys())
        if missing:
            errors.append(f"{case_ref}: {group} is missing required fields: {', '.join(missing)}")
    identifier = raw.get("id")
    question = inputs.get("question")
    behavior = expectations.get("expected_behavior")
    category = metadata.get("category")
    difficulty = metadata.get("difficulty")
    scope = metadata.get("scope")
    rationale = metadata.get("rationale")
    if not isinstance(identifier, str) or not re.fullmatch(r"rag_\d{3}", identifier):
        errors.append(f"{case_ref}: id must match rag_NNN")
        identifier = f"invalid-line-{line_number}"
    case_ref = identifier
    if not isinstance(question, str) or not question.strip():
        errors.append(f"{case_ref}: inputs.question must be a non-empty string")
        question = ""
    if behavior not in EXPECTED_BEHAVIORS:
        errors.append(f"{case_ref}: invalid expected_behavior {behavior!r}")
    if category not in PRIMARY_CATEGORIES:
        errors.append(f"{case_ref}: invalid category {category!r}")
    if difficulty not in DIFFICULTIES:
        errors.append(f"{case_ref}: invalid difficulty {difficulty!r}")
    if scope not in SCOPES:
        errors.append(f"{case_ref}: invalid scope {scope!r}")
    if not isinstance(rationale, str) or not rationale.strip():
        errors.append(f"{case_ref}: metadata.rationale must be a non-empty string")
        rationale = ""
    facts = _string_list(expectations.get("expected_facts", []), "expected_facts", errors, case_ref)
    forbidden = _string_list(expectations.get("forbidden_claims", []), "forbidden_claims", errors, case_ref)
    suites = _string_list(metadata.get("suite"), "metadata.suite", errors, case_ref)
    if any(suite not in {"smoke", "full"} for suite in suites) or "full" not in suites:
        errors.append(f"{case_ref}: suite must contain full and only smoke/full values")
    sources_raw = expectations.get("expected_sources", [])
    sources: list[ExpectedSource] = []
    if not isinstance(sources_raw, list):
        errors.append(f"{case_ref}: expected_sources must be a list")
    else:
        for source_number, source in enumerate(sources_raw, 1):
            if not isinstance(source, dict) or not isinstance(source.get("path"), str) or not isinstance(source.get("section"), str) or not source["path"].strip() or not source["section"].strip():
                errors.append(f"{case_ref}: expected_sources[{source_number}] must contain path and section")
                continue
            sources.append(ExpectedSource(source["path"].strip(), source["section"].strip()))
    if behavior == ANSWER_BEHAVIOR and not facts:
        errors.append(f"{case_ref}: answer cases require expected_facts")
    if behavior == ANSWER_BEHAVIOR and not sources:
        errors.append(f"{case_ref}: answer cases require expected_sources")
    if scope == "single_document" and len({source.path for source in sources}) != 1:
        errors.append(f"{case_ref}: single_document cases require exactly one source document")
    if scope == "multi_document" and len({source.path for source in sources}) < 2:
        errors.append(f"{case_ref}: multi_document cases require at least two source documents")
    return GoldenCase(
        str(identifier), question.strip(), str(behavior), facts, tuple(sources), forbidden,
        str(category), str(difficulty), suites, str(scope), rationale.strip()
    )


def _normalized_tokens(question: str) -> frozenset[str]:
    normalized = unicodedata.normalize("NFKD", question.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return frozenset(re.findall(r"[a-z0-9_]+", normalized))


def _validate_near_duplicates(cases: Sequence[GoldenCase], errors: list[str]) -> None:
    token_sets = {case.id: _normalized_tokens(case.question) for case in cases}
    for position, left in enumerate(cases):
        for right in cases[position + 1:]:
            union = token_sets[left.id] | token_sets[right.id]
            similarity = len(token_sets[left.id] & token_sets[right.id]) / len(union) if union else 1.0
            if similarity >= 0.88:
                errors.append(f"{left.id}/{right.id}: questions are near-duplicates (Jaccard {similarity:.2f})")


def _document_section_contents(repository_root: Path) -> dict[str, dict[str, str]]:
    """Return sanitized text owned by each editorial Markdown section."""
    sections: dict[str, dict[str, str]] = {}
    for relative_path in DEFAULT_ALLOWED_PATHS:
        path = repository_root / relative_path
        if not path.is_file():
            continue
        content = parse_content(path)
        headings = list(re.finditer(r"(?m)^#{1,6}\s+(.+?)\s*$", content))
        sections[relative_path] = {
            heading.group(1).strip(): content[
                heading.end() : headings[position + 1].start() if position + 1 < len(headings) else len(content)
            ].strip()
            for position, heading in enumerate(headings)
        }
    return sections


def _generated_document_sections(repository_root: Path) -> dict[str, set[str]]:
    """Return current chunk metadata for diagnostics, never as editorial truth."""
    generated: dict[str, set[str]] = defaultdict(set)
    for chunk in build_chunks(load_documents(repository_root)):
        generated[chunk.source_path].add(chunk.section)
    return generated


def load_golden_dataset(path: Path, repository_root: Path, expected_count: int = 30) -> list[GoldenCase]:
    """Load JSONL and validate schema, composition, sources, and stable corpus sections."""
    errors: list[str] = []
    cases: list[GoldenCase] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                errors.append(f"line {line_number}: blank lines are not allowed")
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_number}: invalid JSON ({exc.msg})")
                continue
            case = _parse_case(raw, line_number, errors)
            if case:
                cases.append(case)
    if len(cases) != expected_count:
        errors.append(f"dataset must contain exactly {expected_count} cases, found {len(cases)}")
    identifiers = [case.id for case in cases]
    duplicate_ids = sorted(identifier for identifier, count in Counter(identifiers).items() if count > 1)
    if duplicate_ids:
        errors.append(f"duplicate IDs: {', '.join(duplicate_ids)}")
    normalized_questions = [" ".join(case.question.casefold().split()) for case in cases]
    if len(normalized_questions) != len(set(normalized_questions)):
        errors.append("dataset contains exact duplicate questions")
    _validate_near_duplicates(cases, errors)
    category_counts = Counter(case.category for case in cases)
    for category, minimum in MINIMUM_CATEGORY_COUNTS.items():
        if category_counts[category] < minimum:
            errors.append(f"category {category} requires at least {minimum} cases")
    smoke_count = sum("smoke" in case.suite for case in cases)
    if smoke_count != 10:
        errors.append(f"dataset must contain exactly 10 smoke cases, found {smoke_count}")
    if not any(case.scope == "single_document" for case in cases):
        errors.append("dataset requires at least one single_document case")
    if not any(case.scope == "multi_document" for case in cases):
        errors.append("dataset requires at least one multi_document case")
    sections = _document_section_contents(repository_root)
    allowed = set(DEFAULT_ALLOWED_PATHS)
    for case in cases:
        for source in case.expected_sources:
            if source.path not in allowed:
                errors.append(f"{case.id}: source is outside the RAG allowlist: {source.path}")
            elif not (repository_root / source.path).is_file():
                errors.append(f"{case.id}: source file does not exist: {source.path}")
            elif source.section not in sections.get(source.path, {}):
                errors.append(f"{case.id}: section {source.section!r} does not exist in {source.path}")
            elif not sections[source.path][source.section]:
                errors.append(
                    f"{case.id}: section {source.section!r} has no textual evidence in the "
                    f"sanitized corpus for {source.path}"
                )
    if errors:
        raise DatasetValidationError(errors)
    return cases


def select_suite(cases: Iterable[GoldenCase], suite: str) -> list[GoldenCase]:
    if suite not in {"smoke", "full"}:
        raise ValueError("suite must be smoke or full")
    return [case for case in cases if suite in case.suite]


def coverage_report(cases: Sequence[GoldenCase], repository_root: Path) -> dict[str, Any]:
    source_sections: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        for source in case.expected_sources:
            source_sections[source.path].add(source.section)
    covered = set(source_sections)
    generated_sections = _generated_document_sections(repository_root)
    metadata_mismatches = [
        {
            "case_id": case.id,
            "path": source.path,
            "expected_editorial_section": source.section,
            "diagnostic": "section_metadata_mismatch",
        }
        for case in cases
        for source in case.expected_sources
        if source.section not in generated_sections.get(source.path, set())
    ]
    return {
        "total_cases": len(cases),
        "by_category": dict(sorted(Counter(case.category for case in cases).items())),
        "by_difficulty": dict(sorted(Counter(case.difficulty for case in cases).items())),
        "by_behavior": dict(sorted(Counter(case.expected_behavior for case in cases).items())),
        "by_scope": dict(sorted(Counter(case.scope for case in cases).items())),
        "by_suite": {
            "full": sum("full" in case.suite for case in cases),
            "smoke": sum("smoke" in case.suite for case in cases),
        },
        "documents_used": {path: sorted(sections) for path, sections in sorted(source_sections.items())},
        "allowlist_documents_not_covered": sorted(set(DEFAULT_ALLOWED_PATHS) - covered),
        "section_metadata_mismatch": metadata_mismatches,
        "repository_root": str(repository_root.resolve()),
    }


def evaluate_observation(case: GoldenCase, observation: EvaluationObservation) -> CaseEvaluationResult:
    """Score deterministic signals; semantic fact correctness remains explicitly unscored."""
    retrieved = set(observation.retrieved_sources)
    present = tuple(source for source in case.expected_sources if source in retrieved)
    missing = tuple(source for source in case.expected_sources if source not in retrieved)
    retrieval_passed = not missing if case.expected_behavior == ANSWER_BEHAVIOR else True
    refusal_passed = (
        observation.behavior == case.expected_behavior
        if case.expected_behavior != ANSWER_BEHAVIOR
        else None
    )
    fact_coverage: dict[str, bool | None] = {fact: None for fact in case.expected_facts}
    generation_review = "not_applicable" if not case.expected_facts else "human_or_llm_judge_required"
    deterministic_failure = not retrieval_passed or refusal_passed is False
    passed: bool | None = False if deterministic_failure else (True if not case.expected_facts else None)
    return CaseEvaluationResult(
        case.id, case.expected_behavior, observation.behavior, observation.answer,
        observation.retrieved_sources, present, missing, observation.cited_sources,
        fact_coverage, observation.latency_seconds, retrieval_passed, refusal_passed,
        generation_review, passed,
    )


def evaluate_cases(
    cases: Sequence[GoldenCase],
    runner: Callable[[GoldenCase], EvaluationObservation],
) -> EvaluationSummary:
    """Run through an injected adapter without coupling evaluation to Databricks or an LLM."""
    results: list[CaseEvaluationResult] = []
    for case in cases:
        started = perf_counter()
        observation = runner(case)
        if observation.latency_seconds <= 0:
            observation = EvaluationObservation(
                observation.behavior, observation.answer, observation.retrieved_sources,
                observation.cited_sources, perf_counter() - started,
            )
        results.append(evaluate_observation(case, observation))
    latencies = [result.latency_seconds for result in results]
    return EvaluationSummary(
        total=len(results),
        passed=sum(result.passed is True for result in results),
        failed=sum(result.passed is False for result in results),
        needs_review=sum(result.passed is None for result in results),
        mean_latency_seconds=sum(latencies) / len(latencies) if latencies else 0.0,
        results=tuple(results),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and summarize the RAG Golden Dataset")
    parser.add_argument("command", nargs="?", choices=("validate",), default="validate")
    parser.add_argument("--dataset", type=Path, default=Path("evaluation/rag_golden_dataset.jsonl"))
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--suite", choices=("smoke", "full"), default="full")
    args = parser.parse_args()
    cases = load_golden_dataset(args.dataset, args.repository_root)
    selected = select_suite(cases, args.suite)
    print(json.dumps(coverage_report(selected, args.repository_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
