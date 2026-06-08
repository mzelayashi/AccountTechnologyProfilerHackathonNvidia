"""Customer Meeting Insight — Streamlit app.

M0 (this file): upload a Teams transcript (.vtt/.docx/.txt) and analyze it with an LLM.
M1 adds an "OneDrive" source that auto-finds transcripts in your Recordings folder
(see src/ui/onedrive_view.py).
"""
from __future__ import annotations

import config
import streamlit as st
from src.auth import session
from src.llm.factory import get_provider
from src.llm.prompts import analyze_transcript
from src.transcript.parse import parse_transcript
from src.ui.analysis_view import render_analysis

st.set_page_config(page_title="Customer Meeting Insight", page_icon="📊", layout="wide")

# Must run before anything else: redeem an auth code if we just came back from sign-in.
session.process_redirect()

st.title("📊 Customer Meeting Insight")
st.caption(
    "Analyze a customer meeting transcript — summary, what the customer wants, "
    "and action items."
)

# --- LLM readiness banner ---
if not config.llm_configured():
    st.warning(
        "⚠️ No LLM configured yet. Copy `.env.example` → `.env` and set either "
        "**Azure OpenAI** (`AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_API_KEY`) or "
        "**Anthropic** (`ANTHROPIC_API_KEY`), then restart."
    )

with st.sidebar:
    st.header("Source")
    options = ["Upload a file", "OneDrive (sign in)"]
    # Default to OneDrive once signed in, otherwise Upload.
    default_idx = 1 if (config.graph_configured() and session.is_authenticated()) else 0
    source = st.radio(
        "Where is the transcript?",
        options,
        index=default_idx,
        help="Upload works with no Azure setup. OneDrive pulls from your Recordings "
        "folder using Files.Read.All.",
    )
    customer = st.text_input("Customer / account name", placeholder="e.g. Contoso")


def _analyze(filename: str, data: bytes) -> None:
    try:
        parsed = parse_transcript(filename, data)
    except Exception as e:  # noqa: BLE001
        st.error(f"Could not parse transcript: {e}")
        return
    if not parsed.get("text"):
        st.error("The transcript appears to be empty.")
        return
    try:
        provider = get_provider()
    except Exception as e:  # noqa: BLE001
        st.error(str(e))
        return
    with st.spinner(f"Analyzing with {provider.name}…"):
        try:
            result = analyze_transcript(provider, parsed["text"], customer or None)
        except Exception as e:  # noqa: BLE001
            st.error(f"LLM analysis failed: {e}")
            return
    render_analysis(result, parsed, customer or None)


if source == "Upload a file":
    uploaded = st.file_uploader(
        "Upload a Teams meeting transcript",
        type=["vtt", "docx", "txt"],
        help="In Teams: open the meeting → Recap/Transcript → download .vtt or .docx.",
    )
    if uploaded is not None:
        st.success(f"Loaded **{uploaded.name}** ({uploaded.size:,} bytes)")
        if st.button("Analyze meeting", type="primary"):
            _analyze(uploaded.name, uploaded.getvalue())
else:
    try:
        from src.ui.onedrive_view import render_onedrive_source

        render_onedrive_source(customer, _analyze)
    except ModuleNotFoundError:
        st.info("OneDrive source arrives in M1. Use **Upload a file** for now.")
