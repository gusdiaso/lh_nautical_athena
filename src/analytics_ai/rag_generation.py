"""Generation adapter for the documentation-only RAG."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

if __package__:
    from .rag_documents import Chunk
    from .rag_prompt import (
        DATA_WAREHOUSE_RESPONSE,
        NO_DOCUMENTATION_RESPONSE,
        build_system_prompt,
        format_context,
        guard_question,
    )
else:
    from rag_documents import Chunk
    from rag_prompt import (
        DATA_WAREHOUSE_RESPONSE,
        NO_DOCUMENTATION_RESPONSE,
        build_system_prompt,
        format_context,
        guard_question,
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
        return RagAnswer(DATA_WAREHOUSE_RESPONSE, (), refused=True)
    if not question.strip():
        raise ValueError("question cannot be empty")
    if not chunks:
        return RagAnswer(NO_DOCUMENTATION_RESPONSE, (), refused=True)
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")

    response = client.create(
        model=model,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {
                "role": "user",
                "content": (
                    f"<DOCUMENTOS_RECUPERADOS>\n{format_context(chunks)}"
                    f"\n</DOCUMENTOS_RECUPERADOS>\n\nPERGUNTA:\n{question}"
                ),
            },
        ],
        max_tokens=max_tokens,
        temperature=0.1,
    )
    try:
        answer = response.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError) as exc:
        raise ValueError("chat client returned an invalid completion") from exc
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("chat client returned an empty answer")
    return RagAnswer(answer.strip(), _source_paths(chunks))
