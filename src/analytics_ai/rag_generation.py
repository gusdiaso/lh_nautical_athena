"""Generation adapter for the documentation-only RAG."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

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
    return RagAnswer(_with_exact_chunk_citations(answer, chunks), _source_paths(chunks))
