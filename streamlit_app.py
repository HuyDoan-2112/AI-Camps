"""Streamlit UI for the managed AgentCore transfer-advising Harness.

Streamlit owns presentation and transcript parsing only. Amazon Bedrock
AgentCore Harness owns conversation history, memory, model calls, tool
selection, and response generation.

Run locally:
    pip install -e ".[streamlit]"
    streamlit run streamlit_app.py

Required environment:
    AGENTCORE_HARNESS_ARN=<deployed Harness ARN>
    AWS_REGION=us-west-2
"""

from __future__ import annotations

import uuid

import streamlit as st

from transfer_advisor.managed_agent import HarnessClient, HarnessReply, client_from_env
from transfer_advisor.tools.transcript import TranscriptParseError, parse_transcript_upload

EXAMPLES = [
    "I want to transfer for mechanical engineering to UCLA — what should I take next?",
    "Tell me about MATH150",
    "Is Cal-GETC required for UCLA engineering?",
    "Which GE courses transfer to Cal Poly Pomona?",
]

st.set_page_config(page_title="AVC Transfer Advising Assistant", page_icon="🎓")


@st.cache_resource
def get_agent() -> HarnessClient:
    """One managed-Harness client reused across Streamlit reruns."""
    return client_from_env()


def _init_state() -> None:
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []  # list[{"role", "content"}]
        st.session_state.completed_courses = None  # from an uploaded transcript
        st.session_state.transcript_name = None
        st.session_state.transcript_context_pending = False


def _handle_transcript(uploaded) -> None:
    """Parse a transcript attached to the chat input into completed course
    keys. Only course codes are kept -- grades never leave the parser. Stores
    a status banner for the next render rather than drawing one here."""
    if uploaded is None or uploaded.name == st.session_state.transcript_name:
        return
    try:
        courses = parse_transcript_upload(uploaded.getvalue())
    except TranscriptParseError as exc:
        st.session_state.transcript_status = ("error", str(exc))
        return
    st.session_state.completed_courses = sorted(courses)
    st.session_state.transcript_name = uploaded.name
    st.session_state.transcript_context_pending = True
    st.session_state.transcript_status = (
        "ok",
        f"Transcript read — {len(courses)} completed courses found. Ask about your pathway and "
        "I'll personalize the advising conversation around what you've already done.",
    )


def _run_turn(prompt: str) -> None:
    """Send only the newest turn; AgentCore restores prior session memory."""
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                completed_context = (
                    st.session_state.completed_courses
                    if st.session_state.transcript_context_pending
                    else None
                )
                st.session_state.transcript_context_pending = False
                reply = get_agent().reply(
                    prompt,
                    session_id=st.session_state.session_id,
                    actor_id=st.session_state.session_id,
                    completed_courses=completed_context,
                )
                answer = reply.text or "The managed agent returned an empty response."
            except Exception as exc:  # noqa: BLE001 -- surface any Bedrock/creds failure plainly
                answer = f"⚠️ Couldn't generate an answer: {exc}"
                reply = None
        st.markdown(answer)
        if reply is not None:
            _render_activity(reply)
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer,
            "activity": list(reply.activity) if reply is not None else [],
            "usage": reply.usage if reply is not None else None,
            "stop_reason": reply.stop_reason if reply is not None else None,
        }
    )


def _render_activity(reply: HarnessReply) -> None:
    if reply.activity:
        with st.expander("Managed agent activity"):
            for event in reply.activity:
                if event["kind"] == "tool_start":
                    st.markdown(f"Called **{event['text']}**")
                elif event.get("text"):
                    st.caption(event["text"])
    if reply.usage:
        with st.expander("Invocation metrics"):
            st.json(reply.usage, expanded=False)


def main() -> None:
    _init_state()
    _inject_styles()

    st.title("🎓 Transfer & Pathway Advising Assistant")

    # Transcript status banner (set when a PDF is attached to the chat input).
    status = st.session_state.get("transcript_status")
    if status:
        kind, text = status
        (st.success if kind == "ok" else st.error)(text)

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                _render_activity(
                    HarnessReply(
                        text=message["content"],
                        activity=tuple(message.get("activity") or []),
                        usage=message.get("usage"),
                        stop_reason=message.get("stop_reason"),
                    )
                )

    # Example prompts (only before the conversation starts).
    pending: str | None = st.session_state.pop("pending", None)
    if not st.session_state.messages and pending is None:
        st.write("Try one of these:")
        cols = st.columns(2)
        for i, example in enumerate(EXAMPLES):
            if cols[i % 2].button(example, key=f"ex_{i}"):
                st.session_state.pending = example
                st.rerun()

    # The 📎 attach control lives inside the chat input, right next to Send.
    submitted = st.chat_input(
        "Ask about your transfer pathway…  (attach your transcript with 📎)",
        accept_file=True,
        file_type=["pdf"],
    )

    prompt: str | None = None
    if submitted is not None:
        if submitted.files:
            _handle_transcript(submitted.files[0])
        if submitted.text and submitted.text.strip():
            prompt = submitted.text.strip()
    elif pending:
        prompt = pending

    if prompt:
        _run_turn(prompt)
    if prompt or (submitted is not None and submitted.files):
        st.rerun()

    st.caption("Verify any plan with a counselor before registering.")


def _inject_styles() -> None:
    """Light polish on top of .streamlit/config.toml's #64B5F6/white theme."""
    st.markdown(
        """
        <style>
          .block-container { max-width: 820px; padding-top: 2.2rem; }
          h1 { color: #1E6FB8; font-weight: 700; }
          /* Assistant answers on a soft blue-tinted card, user on #64B5F6. */
          [data-testid="stChatMessage"] { border-radius: 14px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
