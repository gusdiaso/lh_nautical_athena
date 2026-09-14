"""Context-only LLM judge for semantic groundedness evaluation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Sequence

if __package__:
    from .rag_documents import Chunk
else:
    from rag_documents import Chunk

JUDGE_PROMPT_VERSION = "groundedness-v4-claim-and-evidence-ids"
CLAIM_VERDICTS = frozenset({"supported", "unsupported", "contradicted"})


@dataclass(frozen=True)
class JudgeEvidence:
    evidence_id: str
    path: str
    section: str


@dataclass(frozen=True)
class JudgedClaim:
    claim_text: str
    verdict: str
    evidence: tuple[JudgeEvidence, ...]


@dataclass(frozen=True)
class GroundednessEvaluation:
    status: str
    groundedness_score: float | None
    grounded: bool | None
    claims: tuple[JudgedClaim, ...]
    prompt_version: str
    endpoint: str
    latency_seconds: float
    raw_output: str | None
    structured_output: dict[str, Any] | None
    failure_reason: str | None = None

    @property
    def supported_claims(self) -> int | None:
        return self._claim_count("supported")

    @property
    def unsupported_claims(self) -> int | None:
        return self._claim_count("unsupported")

    @property
    def contradicted_claims(self) -> int | None:
        return self._claim_count("contradicted")

    def _claim_count(self, verdict: str) -> int | None:
        if self.status != "completed":
            return None
        return sum(claim.verdict == verdict for claim in self.claims)


class JudgeOutputError(ValueError):
    """Raised when the judge does not satisfy the strict output contract."""


def _parse_judge_json(raw_output: str) -> tuple[Any, str]:
    """Parse JSON, repairing only one proven trailing-brace failure mode."""
    try:
        return json.loads(raw_output), "none"
    except json.JSONDecodeError as exc:
        if exc.msg != "Extra data":
            raise JudgeOutputError(f"invalid_json: {exc}") from exc
        stripped = raw_output.lstrip()
        try:
            parsed, end = json.JSONDecoder().raw_decode(stripped)
        except json.JSONDecodeError as raw_exc:
            raise JudgeOutputError(f"invalid_json: {raw_exc}") from raw_exc
        if stripped[end:].strip() != "}":
            raise JudgeOutputError(f"invalid_json: {exc}") from exc
        return parsed, "removed_single_trailing_closing_brace"


def answer_body(answer: str) -> str:
    """Remove citation lines while preserving the literal answer text."""
    return "\n".join(
        line for line in answer.splitlines()
        if not line.lstrip().casefold().startswith("fonte:")
    ).strip()


def extract_material_claims(answer: str) -> tuple[tuple[str, str], ...]:
    """Extract ordered literal sentences after removing citation lines."""
    body = answer_body(answer)
    if not body:
        return ()
    sentences = tuple(
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", body)
        if sentence.strip()
    )
    return tuple((f"claim_{index}", sentence) for index, sentence in enumerate(sentences, 1))


def evidence_candidates(chunks: Sequence[Chunk]) -> tuple[tuple[str, Chunk], ...]:
    """Assign stable request-local IDs to retrieved chunks in retrieval order."""
    return tuple((f"evidence_{index}", chunk) for index, chunk in enumerate(chunks, 1))


def build_judge_messages(
    question: str,
    answer: str,
    chunks: Sequence[Chunk],
    citations: Sequence[Any],
) -> list[dict[str, str]]:
    """Build a judge request containing only the explicitly allowed inputs."""
    payload = {
        "question": question,
        "claims": [
            {"id": claim_id, "text": text}
            for claim_id, text in extract_material_claims(answer)
        ],
        "evidence_candidates": [
            {
                "evidence_id": evidence_id,
                "document": chunk.source_path,
                "section": chunk.section,
                "content": chunk.content,
            }
            for evidence_id, chunk in evidence_candidates(chunks)
        ],
        "citations": [
            {"document": citation.path, "section": citation.section}
            for citation in citations
        ],
    }
    system = """Voce e um juiz estrito de groundedness documental.
Voce nao deve responder a pergunta, completar a resposta, deduzir novas afirmacoes dos chunks nem reescrever o texto das claims.
Use exclusivamente o conteudo em evidence_candidates. Nao use conhecimento externo, memoria, suposicoes ou inferencias sem evidencia textual.
As claims ja foram extraidas deterministicamente da resposta. Julgue cada ID uma unica vez e devolva todos os IDs, sem adicionar IDs ou texto.
Se uma claim misturar conteudo sustentado e inferencia sem base, marque a claim inteira como unsupported.
Para cada claim use:
- supported: afirmacao escrita ou claramente implicada pelos chunks;
- unsupported: afirmacao nao sustentada pelos chunks;
- contradicted: chunks afirmam explicitamente o contrario.
Devolva somente evidence_ids fornecidos. Nao copie, reescreva ou invente evidencias.
supported e contradicted exigem ao menos uma evidencia; unsupported pode ter lista vazia.
Retorne somente JSON, sem markdown, neste contrato:
{"claims":[{"claim_id":"claim_1","verdict":"supported|unsupported|contradicted","evidence_ids":["evidence_1"]}]}"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def validate_judge_output(raw_output: str, answer: str, chunks: Sequence[Chunk]) -> tuple[
    tuple[JudgedClaim, ...], float, bool, dict[str, Any]
]:
    """Parse and validate the complete judge JSON contract."""
    if not isinstance(raw_output, str):
        raise JudgeOutputError("invalid_json: output must be a string")
    parsed, normalization = _parse_judge_json(raw_output)
    if not isinstance(parsed, dict):
        raise JudgeOutputError("output must be a JSON object")
    if set(parsed) != {"claims"}:
        raise JudgeOutputError("output must contain exactly claims")
    claims_raw = parsed["claims"]
    if not isinstance(claims_raw, list) or not claims_raw:
        raise JudgeOutputError("claims must be a non-empty list")
    available_evidence = dict(evidence_candidates(chunks))
    material_claims = dict(extract_material_claims(answer))
    if not material_claims:
        raise JudgeOutputError("answer has no material text after removing citations")
    claims: list[JudgedClaim] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(claims_raw):
        if not isinstance(item, dict) or set(item) != {"claim_id", "verdict", "evidence_ids"}:
            raise JudgeOutputError(f"claims[{index}] has an invalid schema")
        claim_id = item["claim_id"]
        verdict = item["verdict"]
        evidence_ids = item["evidence_ids"]
        if claim_id not in material_claims:
            raise JudgeOutputError(f"claims[{index}].claim_id is unknown")
        if claim_id in seen_ids:
            raise JudgeOutputError(f"claims[{index}].claim_id is duplicated")
        seen_ids.add(claim_id)
        if verdict not in CLAIM_VERDICTS:
            raise JudgeOutputError(f"claims[{index}].verdict is invalid")
        if not isinstance(evidence_ids, list) or not all(isinstance(value, str) for value in evidence_ids):
            raise JudgeOutputError(f"claims[{index}].evidence_ids must be a list of strings")
        if len(evidence_ids) != len(set(evidence_ids)):
            raise JudgeOutputError(f"claims[{index}].evidence_ids contains duplicates")
        evidence: list[JudgeEvidence] = []
        for evidence_id in evidence_ids:
            if evidence_id not in available_evidence:
                raise JudgeOutputError(f"claims[{index}] references unknown evidence_id")
            chunk = available_evidence[evidence_id]
            evidence.append(JudgeEvidence(evidence_id, chunk.source_path, chunk.section))
        if verdict in {"supported", "contradicted"} and not evidence:
            raise JudgeOutputError(f"claims[{index}] verdict {verdict} requires evidence")
        claims.append(JudgedClaim(material_claims[claim_id], verdict, tuple(evidence)))

    missing_ids = set(material_claims) - seen_ids
    if missing_ids:
        raise JudgeOutputError(
            "judge did not evaluate all claim IDs: " + ", ".join(sorted(missing_ids))
        )

    score = sum(claim.verdict == "supported" for claim in claims) / len(claims)
    grounded = all(claim.verdict == "supported" for claim in claims)
    structured = {
        "claims": parsed["claims"],
        "output_normalization": normalization,
        "evidence_catalog": [
            {
                "evidence_id": evidence_id,
                "document": chunk.source_path,
                "section": chunk.section,
                "content": chunk.content,
            }
            for evidence_id, chunk in evidence_candidates(chunks)
        ],
        "groundedness_score": score,
        "grounded": grounded,
    }
    return tuple(claims), score, grounded, structured


def evaluate_groundedness(
    client: Any,
    question: str,
    answer: str,
    chunks: Sequence[Chunk],
    citations: Sequence[Any],
    endpoint: str,
    timeout_seconds: float = 60.0,
) -> GroundednessEvaluation:
    """Call and validate the context-only judge without leaking endpoint failures."""
    if timeout_seconds <= 0:
        raise ValueError("judge timeout must be positive")
    started = perf_counter()
    raw_output: str | None = None
    try:
        response = client.create(
            model=endpoint,
            messages=build_judge_messages(question, answer, chunks, citations),
            max_tokens=1200,
            temperature=0.0,
            timeout=timeout_seconds,
        )
        raw_output = response.choices[0].message.content
        if not isinstance(raw_output, str) or not raw_output.strip():
            raise JudgeOutputError("judge returned an empty response")
        claims, score, grounded, structured = validate_judge_output(raw_output, answer, chunks)
        return GroundednessEvaluation(
            "completed", score, grounded, claims, JUDGE_PROMPT_VERSION, endpoint,
            perf_counter() - started, raw_output, structured,
        )
    except Exception as exc:
        status = (
            "invalid_output" if isinstance(exc, JudgeOutputError)
            else "timeout" if isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower()
            else "endpoint_error"
        )
        return GroundednessEvaluation(
            status, None, None, (), JUDGE_PROMPT_VERSION, endpoint,
            perf_counter() - started, raw_output, None,
            f"{type(exc).__name__}: {exc}",
        )
