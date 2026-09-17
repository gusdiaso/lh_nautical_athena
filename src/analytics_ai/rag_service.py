"""UI-independent orchestration. Clients are lazy so refusals need no credentials."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from time import perf_counter
from typing import Callable
from uuid import uuid4

if __package__:
    from .rag_databricks import retrieve_chunks
    from .rag_generation import check_citations, generate_answer
    from .rag_prompt import guard_question, NO_DOCUMENTATION_RESPONSE, normalize_deterministic_response
else:
    from rag_databricks import retrieve_chunks
    from rag_generation import check_citations, generate_answer
    from rag_prompt import guard_question, NO_DOCUMENTATION_RESPONSE, normalize_deterministic_response


@dataclass
class Interaction:
    id: str
    timestamp: str
    question: str
    status: str
    answer: str
    retrieved: list[dict]
    citations_valid: bool
    duration_seconds: float
    feedback: str | None = None


def export_interactions(interactions: list[Interaction]) -> str:
    return json.dumps({"schema_version": 1, "interactions": [asdict(i) for i in interactions]},
                      ensure_ascii=False, indent=2)


class RagService:
    def __init__(self, clients: Callable, model: str, max_results: int = 5):
        if not 1 <= max_results <= 10:
            raise ValueError("max_results must be between 1 and 10")
        self.clients = clients
        self.model = model
        self.max_results = max_results

    def ask(self, question: str) -> Interaction:
        started = perf_counter()
        interaction = Interaction(str(uuid4()), datetime.now(timezone.utc).isoformat(),
                                  question.strip(), "error", "", [], False, 0)
        try:
            if not interaction.question or len(interaction.question) > 4000:
                interaction.answer = "Informe uma pergunta entre 1 e 4000 caracteres."
                return interaction
            refusal = guard_question(interaction.question)
            chunks = []
            chat = None
            if not refusal:
                index, chat = self.clients()
                chunks = retrieve_chunks(index, interaction.question, self.max_results,
                                         filters={"status": "approved"})
            interaction.retrieved = [dict(document=c.source_path, section=c.section, content=c.content)
                                     for c in chunks]
            generated = generate_answer(chat, interaction.question, chunks, self.model)
            interaction.answer = generated.answer
            if normalize_deterministic_response(generated.answer) == normalize_deterministic_response(NO_DOCUMENTATION_RESPONSE):
                interaction.status = "insufficient_context"
            else:
                interaction.status = "refused" if generated.refused else "answer"
            interaction.citations_valid = check_citations(generated.answer, chunks).valid
        except Exception:
            # SDK exceptions can contain credentials, request headers or user content.
            # Never place their raw text in the UI, export, or application logs.
            interaction.status = "error"
            interaction.answer = "Não foi possível consultar a RAG. Confira autenticação, permissões e disponibilidade dos serviços."
        finally:
            interaction.duration_seconds = perf_counter() - started
        return interaction
