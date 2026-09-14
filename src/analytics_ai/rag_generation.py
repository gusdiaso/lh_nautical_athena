"""Generation adapter for the documentation-only RAG."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

if __package__:
    from .rag_documents import Chunk
    from .rag_prompt import (
        ADVERSARIAL_RESPONSE,
        DATA_WAREHOUSE_RESPONSE,
        NO_DOCUMENTATION_RESPONSE,
        build_system_prompt,
        format_context,
        guard_question,
        normalize_deterministic_response,
    )
else:
    from rag_documents import Chunk
    from rag_prompt import (
        ADVERSARIAL_RESPONSE,
        DATA_WAREHOUSE_RESPONSE,
        NO_DOCUMENTATION_RESPONSE,
        build_system_prompt,
        format_context,
        guard_question,
        normalize_deterministic_response,
    )


class ChatClient(Protocol):
    """Minimal chat interface required by the RAG generation layer."""

    def create(self, **kwargs: Any) -> Any:
        """Generate a chat completion."""


@dataclass(frozen=True)
class RagAnswer:
    """Answer and sources returned by the generation layer."""

    answer: str
    sources: tuple[str, ...]
    refused: bool = False


@dataclass(frozen=True)
class CitationCheck:
    """Diagnostics comparing the citations of an answer with the retrieved chunks."""

    cited: tuple[tuple[str, str], ...]
    retrieved: tuple[tuple[str, str], ...]
    not_retrieved: tuple[tuple[str, str], ...]

    @property
    def valid(self) -> bool:
        """A technical answer is citable only when every citation was retrieved."""
        return bool(self.cited) and not self.not_retrieved


CITATION_PATTERN = re.compile(
    r"Fonte:\s*\[?(.+?)\]?\s*-\s*Se(?:c|ç)(?:a|ã)o:\s*([^\n]+)",
    re.IGNORECASE,
)


def parse_citation_pairs(answer: str) -> tuple[tuple[str, str], ...]:
    """Extract unique ``(document, section)`` citations preserving their order."""
    return tuple(
        dict.fromkeys(
            (path.strip(), section.strip().rstrip(". "))
            for path, section in CITATION_PATTERN.findall(answer)
        )
    )


def check_citations(answer: str, chunks: Sequence[Chunk]) -> CitationCheck:
    """Verify that every citation of the answer points to a retrieved chunk.

    The check is deterministic and local: it never proves that a claim is
    correct, only that the cited document and section were actually part of the
    context sent to the model.
    """
    cited = parse_citation_pairs(answer)
    retrieved = tuple(dict.fromkeys((chunk.source_path, chunk.section) for chunk in chunks))
    retrieved_pairs = frozenset(retrieved)
    return CitationCheck(
        cited=cited,
        retrieved=retrieved,
        not_retrieved=tuple(pair for pair in cited if pair not in retrieved_pairs),
    )


def _source_paths(chunks: list[Chunk]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(chunk.source_path for chunk in chunks))


def _answer_without_citation_lines(answer: str) -> str:
    return re.sub(r"(?im)^\s*Fonte:\s*.*$", "", answer).strip()


def _canonical_guard_response(answer: str) -> str | None:
    """Return the untouched response body when it is exactly a canonical guard."""
    without_citations = _answer_without_citation_lines(answer)
    canonical_responses = {
        normalize_deterministic_response(NO_DOCUMENTATION_RESPONSE),
        normalize_deterministic_response(DATA_WAREHOUSE_RESPONSE),
        normalize_deterministic_response(ADVERSARIAL_RESPONSE),
    }
    if normalize_deterministic_response(without_citations) in canonical_responses:
        return without_citations
    return None


def _with_exact_chunk_citations(answer: str, chunks: list[Chunk]) -> str:
    """Replace model-produced citations with exact, separately listed chunk metadata."""
    without_citations = _answer_without_citation_lines(answer)
    if not without_citations:
        # Preserve deficient model output for audit/classification. Replacing it with all
        # retrieved sources would manufacture a citation-only answer in post-processing.
        return answer.strip()
    sources = tuple(dict.fromkeys((chunk.source_path, chunk.section) for chunk in chunks))
    citations = "\n".join(
        f"Fonte: {source_path} - Secao: {section}" for source_path, section in sources
    )
    return f"{without_citations}\n\n{citations}".strip()


def generate_answer(
    client: ChatClient,
    question: str,
    chunks: list[Chunk],
    model: str,
    max_tokens: int = 500,
) -> RagAnswer:
    """Generate an answer only from retrieved chunks and return their sources."""
    refusal = guard_question(question)
    if refusal:
        return RagAnswer(refusal, (), refused=True)
    if not question.strip():
        raise ValueError("question cannot be empty")
    if not chunks:
        return RagAnswer(NO_DOCUMENTATION_RESPONSE, (), refused=True)
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")

    messages = [
        {"role": "system", "content": build_system_prompt()},
        {
            "role": "user",
            "content": (
                f"<DOCUMENTOS_RECUPERADOS>\n{format_context(chunks)}"
                f"\n</DOCUMENTOS_RECUPERADOS>\n\nPERGUNTA:\n{question}"
            ),
        },
    ]
    response = client.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.1,
    )
    try:
        answer = response.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError) as exc:
        raise ValueError("chat client returned an invalid completion") from exc
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("chat client returned an empty answer")
    if normalize_deterministic_response(answer) == normalize_deterministic_response(
        NO_DOCUMENTATION_RESPONSE
    ):
        response = client.create(
            model=model,
            messages=messages + [{
                "role": "user",
                "content": (
                    "Revise uma vez: ha trechos recuperados. Verifique se eles respondem "
                    "diretamente a todas as partes da pergunta antes de concluir que falta contexto."
                ),
            }],
            max_tokens=max_tokens,
            temperature=0.1,
        )
        try:
            answer = response.choices[0].message.content
        except (AttributeError, IndexError, KeyError, TypeError) as exc:
            raise ValueError("chat client returned an invalid retry completion") from exc
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("chat client returned an empty retry answer")
    canonical_guard = _canonical_guard_response(answer)
    if canonical_guard is not None:
        return RagAnswer(canonical_guard, (), refused=True)
    if not _answer_without_citation_lines(answer):
        response = client.create(
            model=model,
            messages=messages + [{
                "role": "user",
                "content": (
                    "A primeira saida continha somente linhas Fonte:, sem corpo textual. "
                    "Produza agora uma resposta documental com corpo textual que responda a "
                    "pergunta, usando somente os documentos recuperados. Depois do corpo, cite "
                    "apenas os pares DOCUMENTO + SECAO usados."
                ),
            }],
            max_tokens=max_tokens,
            temperature=0.1,
        )
        try:
            answer = response.choices[0].message.content
        except (AttributeError, IndexError, KeyError, TypeError) as exc:
            raise ValueError("chat client returned an invalid citation-only retry completion") from exc
        if not isinstance(answer, str):
            raise ValueError("chat client returned an invalid citation-only retry completion")
        canonical_guard = _canonical_guard_response(answer)
        if canonical_guard is not None:
            return RagAnswer(canonical_guard, (), refused=True)
    return RagAnswer(_with_exact_chunk_citations(answer, chunks), _source_paths(chunks))
