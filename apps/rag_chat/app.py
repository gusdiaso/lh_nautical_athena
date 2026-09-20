"""Internal single-user documentary RAG test interface."""
from pathlib import Path
import sys

# The deployed source root must include both apps/ and src/.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
from src.analytics_ai.rag_clients import create_clients
from src.analytics_ai.rag_config import RagRuntimeConfig
from src.analytics_ai.rag_service import RagService, export_interactions

st.set_page_config(
    page_title="Assistente de Documentação · LH Nautical",
    page_icon="📚",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Static presentation styles only. All generated and retrieved content remains
# rendered as plain text below; no model output is interpreted as HTML.
st.markdown(
    """
    <style>
      :root {
        --rag-navy: #071a2b;
        --rag-night: #0b2238;
        --rag-card: #102d49;
        --rag-blue: #48a9e6;
        --rag-blue-soft: #dceffc;
        --rag-blue-line: #6daed4;
        --rag-text: #f1f7fc;
        --rag-muted: #bdd1e1;
        --rag-ink: #12314b;
      }
      html, body, .stApp, [data-testid="stAppViewContainer"],
      [data-testid="stMain"], [data-testid="stHeader"] {
        background-color: var(--rag-navy) !important;
      }
      .stApp, .stApp p, .stApp label, .stApp [data-testid="stMarkdownContainer"] {
        color: var(--rag-text);
      }
      .stApp { --background-color: var(--rag-navy); --secondary-background-color: var(--rag-night);
        --text-color: var(--rag-text); --primary-color: #69c5ff; color: var(--rag-text); }
      [data-testid="stMainBlockContainer"] {
        max-width: 920px;
        padding-top: 2.2rem;
        padding-bottom: 2rem;
      }
      h1, h2, h3 { color: #f3f8fc !important; letter-spacing: -0.025em; }
      .rag-eyebrow {
        display: block; position: relative; z-index: 2; overflow: visible;
        color: #b9e7ff !important; -webkit-text-fill-color: #b9e7ff !important;
        font-size: .78rem; font-weight: 700; line-height: 1.4;
        letter-spacing: .075em; text-transform: uppercase;
        margin: 1rem 0 .8rem; padding-top: .35rem;
      }
      .rag-title-row { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
      .rag-main-title {
        color: #f3f8fc !important; font-size: clamp(2rem, 4vw, 3rem);
        font-weight: 700; line-height: 1.1; letter-spacing: -0.025em;
        margin: 0; padding: 0;
      }
      .rag-env {
        display: inline-block; white-space: nowrap; border: 1px solid #4e9cca;
        color: #dff3ff; background: #123e5e; border-radius: 999px;
        padding: .35rem .7rem; font-size: .72rem; font-weight: 700; letter-spacing: .04em;
      }
      .rag-subtitle { color: var(--rag-muted); margin-top: -.45rem; }
      .rag-notice {
        background: var(--rag-blue-soft); border-left: 3px solid var(--rag-blue);
        color: var(--rag-ink); border-radius: .45rem; padding: .75rem 1rem;
        margin: 1.2rem 0 1.5rem; font-size: .9rem;
      }
      .rag-notice strong { color: #0a4267; }
      .rag-section-label { color: #e3f3ff; font-weight: 650; margin: .5rem 0 .25rem; }
      div[data-testid="stChatMessage"] {
        border-radius: .8rem; background: var(--rag-night); border: 1px solid #1d4564;
        padding: .7rem .85rem;
      }
      div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p { line-height: 1.65; }
      div[data-testid="stChatMessage"] [data-testid="stText"] { color: var(--rag-text) !important; }
      div[data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--rag-card); border-radius: .85rem;
      }
      div[data-testid="stExpander"] {
        border: 1px solid #a6cde5; border-radius: .55rem; background: var(--rag-blue-soft);
      }
      /* Streamlit paints <details>/<summary> with the theme's dark secondary
         background on top of the wrapper, which hid the dark header text. */
      div[data-testid="stExpander"] details,
      div[data-testid="stExpander"] summary,
      div[data-testid="stExpander"] summary:hover,
      div[data-testid="stExpander"] summary:focus,
      div[data-testid="stExpander"] summary:focus-visible,
      div[data-testid="stExpander"] details[open] summary {
        background: var(--rag-blue-soft) !important;
        background-color: var(--rag-blue-soft) !important;
      }
      div[data-testid="stExpander"] summary svg {
        fill: #102b43 !important; color: #102b43 !important;
      }
      /* Keep all document-expander copy readable on the light-blue surface. */
      div[data-testid="stExpander"] summary,
      div[data-testid="stExpander"] summary *,
      div[data-testid="stExpander"] [data-testid="stMarkdownContainer"],
      div[data-testid="stExpander"] [data-testid="stMarkdownContainer"] *,
      div[data-testid="stExpander"] [data-testid="stText"],
      div[data-testid="stExpander"] [data-testid="stText"] *,
      div[data-testid="stExpander"] [data-testid="stCaptionContainer"],
      div[data-testid="stExpander"] [data-testid="stCaptionContainer"] *,
      div[data-testid="stExpander"] p,
      div[data-testid="stExpander"] li,
      div[data-testid="stExpander"] blockquote,
      div[data-testid="stExpander"] code {
        color: #102b43 !important;
        -webkit-text-fill-color: #102b43 !important;
      }
      div[data-testid="stExpander"] a,
      div[data-testid="stExpander"] a:visited {
        color: #07527d !important;
        -webkit-text-fill-color: #07527d !important;
        text-decoration: underline;
      }
      div[data-testid="stExpander"] a:hover,
      div[data-testid="stExpander"] a:focus-visible {
        color: #062f4b !important;
        -webkit-text-fill-color: #062f4b !important;
      }
      div[data-testid="stButton"] > button {
        border: 1px solid #438bb9; color: #f2f8fc; background: #16466a;
        border-radius: .65rem; min-height: 3.2rem; white-space: normal;
        transition: border-color .15s ease, background .15s ease, color .15s ease;
      }
      div[data-testid="stButton"] > button:hover {
        border-color: #9ddcff; color: #fff; background: #205f89;
      }
      div[data-testid="stDownloadButton"] > button {
        border: 1px solid #438bb9; color: #dff3ff; background: #123e5e; border-radius: .55rem;
      }
      div[data-testid="stDownloadButton"] > button:hover {
        border-color: #9ddcff; color: #fff; background: #205f89;
      }
      div[data-testid="stRadio"] label, div[data-testid="stCaptionContainer"] { color: var(--rag-muted); }
      div[data-testid="stChatInput"] {
        border: 1px solid #438bb9 !important; border-radius: .8rem !important;
        background: #123552 !important; overflow: hidden !important;
        padding: 0 !important;
      }
      div[data-testid="stChatInput"] > div,
      div[data-testid="stChatInput"] [data-baseweb="textarea"] {
        border-radius: .8rem !important; overflow: hidden !important;
        background: #123552 !important;
      }
      div[data-testid="stChatInput"] textarea {
        color: #f1f7fc !important; border-radius: .8rem 0 0 .8rem !important;
      }
      div[data-testid="stChatInput"] textarea::placeholder { color: #b7d0e3 !important; }
      div[data-testid="stChatInput"] button {
        color: #8dd5ff !important; border-radius: 0 .8rem .8rem 0 !important;
        background: #16466a !important; border: 0 !important;
      }
      div[data-testid="stAlert"][kind="info"] {
        background: var(--rag-blue-soft); border-color: #68acd5;
      }
      div[data-testid="stAlert"][kind="info"] p,
      div[data-testid="stAlert"][kind="info"] [data-testid="stMarkdownContainer"] { color: var(--rag-ink) !important; }
      div[data-testid="stAlert"][kind="warning"] { border-color: #d99a34; }
      div[data-testid="stAlert"][kind="error"] { border-color: #d65b66; }
      div[data-testid="stAlert"] p { line-height: 1.5; }
      [data-testid="stRadio"] input { accent-color: #69c5ff; }
      @media (max-width: 640px) {
        [data-testid="stMainBlockContainer"] { padding-left: 1rem; padding-right: 1rem; }
        .rag-title-row { align-items: flex-start; }
        .rag-env { margin-top: .35rem; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)

if "interactions" not in st.session_state:
    st.session_state.interactions = []

title_col, environment_col = st.columns([5, 1.5], vertical_alignment="center")
with title_col:
    st.markdown(
        '<div class="rag-eyebrow">LH Nautical · RAG documental</div>'
        '<h1 class="rag-main-title">Assistente de Documentação</h1>',
        unsafe_allow_html=True,
    )
with environment_col:
    st.markdown('<div class="rag-env">DEV · uso interno</div>', unsafe_allow_html=True)
st.markdown('<div class="rag-subtitle">Pergunte sobre a documentação técnica do projeto.</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="rag-notice"><strong>Assistente interno de documentação.</strong> '
    'Confira as fontes antes de usar a resposta. As perguntas são independentes; '
    'histórico e feedback existem somente nesta sessão.</div>',
    unsafe_allow_html=True,
)


def clients():
    # Session-local: no credentials or conversation state shared through a global cache.
    if "rag_clients" not in st.session_state:
        config = RagRuntimeConfig.from_environment()
        st.session_state.rag_clients = create_clients(config.index.index_name)
    return st.session_state.rag_clients


suggested_question = None
if not st.session_state.interactions:
    st.markdown('<div class="rag-section-label">Perguntas para começar</div>', unsafe_allow_html=True)
    suggestions = [
        "Como funciona o processo de ingestão e transformação do projeto?",
        "Onde ficam os testes e as regras de negócio dos marts?",
        "Quais pilares de negócio o modelo dimensional pretende atender?",
    ]
    suggestion_cols = st.columns(3)
    for index, (column, suggestion) in enumerate(zip(suggestion_cols, suggestions)):
        with column:
            if st.button(suggestion, key=f"starter_question_{index}", use_container_width=True):
                suggested_question = suggestion

question = st.chat_input("Faça uma pergunta documental…", max_chars=4000)
question = question or suggested_question
if question:
    with st.spinner("Consultando a documentação e preparando a resposta…"):
        config = RagRuntimeConfig.from_environment()
        result = RagService(clients, config.llm_endpoint_name).ask(question)
        st.session_state.interactions.append(result)

for interaction in st.session_state.interactions:
    with st.chat_message("user"):
        st.text(interaction.question)

    with st.chat_message("assistant"):
        with st.container(border=True):
            heading_col, duration_col = st.columns([5, 1], vertical_alignment="center")
            with heading_col:
                st.markdown("**Resposta documental**")
            with duration_col:
                st.caption(f"{interaction.duration_seconds:.1f}s")

            if interaction.status == "error":
                st.error(interaction.answer, icon="⚠️")
            elif interaction.status == "refused":
                st.warning("Pergunta recusada pelas diretrizes documentais.", icon="⛔")
                st.text(interaction.answer)
            elif interaction.status == "insufficient_context":
                st.info("Não encontrei evidência suficiente na documentação recuperada.", icon="ℹ️")
                st.text(interaction.answer)
            else:
                # Keep generated text unparsed to avoid interpreting model HTML/links.
                st.text(interaction.answer)
                if not interaction.citations_valid:
                    st.info("As citações desta resposta não puderam ser verificadas.", icon="ℹ️")

            if interaction.retrieved:
                st.markdown("**Documentos recuperados**")
                st.caption("A presença no contexto não comprova suporte a cada afirmação.")
                for source in interaction.retrieved:
                    with st.expander(f"{source['document']} · {source['section']}"):
                        st.text(source["content"])

        feedback_col, interaction_col = st.columns([3, 2], vertical_alignment="center")
        with feedback_col:
            feedback = st.radio(
                "Esta resposta foi útil?",
                ["Sem avaliação", "Útil", "Não útil"],
                key=f"feedback_{interaction.id}",
                horizontal=True,
                label_visibility="collapsed",
            )
        interaction.feedback = {
            "Sem avaliação": None,
            "Útil": "useful",
            "Não útil": "not_useful",
        }[feedback]
        with interaction_col:
            st.caption(f"Interação {interaction.id}")

if st.session_state.interactions:
    with st.container():
        st.download_button(
            "Exportar sessão em JSON",
            export_interactions(st.session_state.interactions),
            file_name="rag-interacoes.json",
            mime="application/json",
            type="secondary",
        )
        st.caption("O arquivo inclui perguntas, respostas, trechos recuperados e feedback; nada é salvo em tabela.")
