"""Internal single-user documentary RAG test interface."""
from pathlib import Path
import sys

# The deployed source root must include src/analytics_ai, without copying its logic.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
from src.analytics_ai.rag_clients import create_clients
from src.analytics_ai.rag_config import RagRuntimeConfig
from src.analytics_ai.rag_service import RagService, export_interactions

st.set_page_config(page_title="RAG documental — testes", page_icon="📚")
st.title("RAG documental")
st.warning("Versão interna de testes. Confira as fontes antes de usar a resposta.")
st.caption("Perguntas independentes sobre a documentação. Histórico e feedback existem somente nesta sessão.")

if "interactions" not in st.session_state:
    st.session_state.interactions = []


def clients():
    # Session-local: no credentials or conversation state shared through a global cache.
    if "rag_clients" not in st.session_state:
        config = RagRuntimeConfig.from_environment()
        st.session_state.rag_clients = create_clients(config.index.index_name)
    return st.session_state.rag_clients


question = st.chat_input("Faça uma pergunta documental", max_chars=4000)
if question:
    with st.spinner("Consultando documentos e preparando a resposta…"):
        config = RagRuntimeConfig.from_environment()
        result = RagService(clients, config.llm_endpoint_name).ask(question)
        st.session_state.interactions.append(result)

for interaction in st.session_state.interactions:
    with st.chat_message("user"):
        st.text(interaction.question)
    with st.chat_message("assistant"):
        if interaction.status == "error":
            st.error(interaction.answer)
        elif interaction.status == "refused":
            st.warning("Pergunta recusada pelas diretrizes documentais.")
            st.text(interaction.answer)
        elif interaction.status == "insufficient_context":
            st.info("Contexto documental insuficiente.")
            st.text(interaction.answer)
        else:
            # Plain text avoids executing HTML or fetching model-provided remote images.
            st.text(interaction.answer)
            if not interaction.citations_valid:
                st.warning("As citações desta resposta não puderam ser verificadas.")
        if interaction.retrieved:
            st.caption("Documentos recuperados para esta resposta — presença no contexto não comprova suporte a cada afirmação.")
            for number, source in enumerate(interaction.retrieved, 1):
                with st.expander(f"Trecho {number}"):
                    st.text(f"{source['document']} — {source['section']}")
                    st.text(source["content"])
        st.caption(f"Interação {interaction.id} · {interaction.duration_seconds:.1f}s")
        feedback = st.radio("Esta resposta foi útil?", ["Sem avaliação", "Útil", "Não útil"],
                            key=f"feedback_{interaction.id}", horizontal=True)
        interaction.feedback = {"Sem avaliação": None, "Útil": "useful", "Não útil": "not_useful"}[feedback]

if st.session_state.interactions:
    st.download_button("Exportar interações em JSON", export_interactions(st.session_state.interactions),
                       file_name="rag-interacoes.json", mime="application/json")
    st.caption("A exportação inclui perguntas, respostas, trechos e feedback. Nada é gravado em uma tabela.")
