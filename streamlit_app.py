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

import os
import uuid

import streamlit as st

from transfer_advisor.managed_agent import HarnessClient, HarnessReply, client_from_env
from transfer_advisor.tools.transcript import TranscriptParseError, parse_transcript_upload

EXAMPLES = [
    "What can you help me with?",
    "Tell me about MATH150",
    "How does Cal-GETC work?",
    "Show live MATH150 sections for Fall 2026",
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
            "timing": reply.timing if reply is not None else None,
        }
    )


def _render_activity(reply: HarnessReply) -> None:
    """Show a lightweight status line; keep raw diagnostics out of student UI."""
    summary: list[str] = []
    if reply.timing and reply.timing.get("total_ms") is not None:
        summary.append(f"Answered in {_format_ms(reply.timing['total_ms'])}")
    tool_count = sum(event["kind"] == "tool_start" for event in reply.activity)
    if tool_count:
        summary.append(f"{tool_count} verified data lookup{'s' if tool_count != 1 else ''}")
    if summary:
        st.caption("  ·  ".join(summary))

    if os.environ.get("SHOW_AGENT_DIAGNOSTICS", "").lower() in {"1", "true", "yes"}:
        with st.expander("Developer diagnostics"):
            st.json(
                {
                    "timing": reply.timing,
                    "activity": list(reply.activity),
                    "usage": reply.usage,
                    "stop_reason": reply.stop_reason,
                },
                expanded=False,
            )


def _format_ms(value: float | None) -> str:
    if value is None:
        return "not reported"
    return f"{value / 1000:.2f}s"


def main() -> None:
    _init_state()
    _inject_styles()

    st.markdown(
        """
        <section class="advisor-hero">
          <div class="advisor-kicker">AVC TRANSFER PLANNING</div>
          <h1>Your next step, made clearer.</h1>
          <p>
            Explore courses, transfer requirements, general education, and
            personalized plans using verified academic data.
          </p>
          <div class="advisor-trust">
            <span>✓ Verified pathway data</span>
            <span>✓ Live section checks</span>
            <span>✓ Plan validation</span>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

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
                        timing=message.get("timing"),
                    )
                )

    # Example prompts (only before the conversation starts).
    pending: str | None = st.session_state.pop("pending", None)
    if not st.session_state.messages and pending is None:
        st.markdown(
            """
            <div class="advisor-welcome">
              <h2>What would you like to figure out?</h2>
              <p>Choose a starting point or write your own question below.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        cols = st.columns(2)
        for i, example in enumerate(EXAMPLES):
            if cols[i % 2].button(example, key=f"ex_{i}"):
                st.session_state.pending = example
                st.rerun()

    # The 📎 attach control lives inside the chat input, right next to Send.
    submitted = st.chat_input(
        "Ask a question or attach your transcript…",
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

    st.markdown(
        """
        <div class="advisor-footer">
          Academic planning support—not a replacement for your counselor.
          Verify your final plan before registering.
        </div>
        """,
        unsafe_allow_html=True,
    )


def _inject_styles() -> None:
    """Friendly student-facing visual system for the Streamlit shell."""
    st.markdown(
        """
        <style>
          :root {
            --advisor-navy: #123454;
            --advisor-blue: #1e73be;
            --advisor-sky: #eaf5ff;
            --advisor-mint: #e9f8f2;
            --advisor-ink: #18324a;
            --advisor-muted: #62788d;
            --advisor-line: #dce8f2;
          }

          .stApp {
            background:
              radial-gradient(circle at 12% 0%, #eef8ff 0, transparent 28rem),
              linear-gradient(180deg, #ffffff 0%, #f8fbfe 100%);
            color: var(--advisor-ink);
          }

          .block-container {
            max-width: 900px;
            padding-top: 2rem;
            padding-bottom: 7rem;
          }

          .advisor-hero {
            background: linear-gradient(135deg, #123b61 0%, #1e73be 72%, #3b96d8 100%);
            border-radius: 24px;
            box-shadow: 0 16px 40px rgba(30, 85, 128, 0.16);
            color: white;
            margin-bottom: 2rem;
            overflow: hidden;
            padding: 2.4rem 2.5rem 2.2rem;
            position: relative;
          }

          .advisor-hero::after {
            background: rgba(255, 255, 255, 0.08);
            border-radius: 999px;
            content: "";
            height: 15rem;
            position: absolute;
            right: -5rem;
            top: -7rem;
            width: 15rem;
          }

          .advisor-kicker {
            font-size: 0.76rem;
            font-weight: 750;
            letter-spacing: 0.14em;
            margin-bottom: 0.65rem;
            opacity: 0.82;
          }

          .advisor-hero h1 {
            color: white;
            font-size: clamp(2rem, 5vw, 3.2rem);
            letter-spacing: -0.04em;
            line-height: 1.03;
            margin: 0;
            max-width: 650px;
          }

          .advisor-hero p {
            color: rgba(255, 255, 255, 0.88);
            font-size: 1.05rem;
            line-height: 1.6;
            margin: 1rem 0 1.4rem;
            max-width: 650px;
          }

          .advisor-trust {
            display: flex;
            flex-wrap: wrap;
            font-size: 0.82rem;
            gap: 0.65rem 1.2rem;
          }

          .advisor-trust span { white-space: nowrap; }

          .advisor-welcome h2 {
            color: var(--advisor-navy);
            font-size: 1.35rem;
            letter-spacing: -0.02em;
            margin: 0;
          }

          .advisor-welcome p {
            color: var(--advisor-muted);
            margin: 0.35rem 0 1rem;
          }

          div[data-testid="stButton"] > button {
            background: rgba(255, 255, 255, 0.92);
            border: 1px solid var(--advisor-line);
            border-radius: 15px;
            box-shadow: 0 6px 18px rgba(35, 83, 122, 0.06);
            color: var(--advisor-ink);
            font-weight: 600;
            justify-content: flex-start;
            min-height: 4.5rem;
            padding: 0.8rem 1rem;
            text-align: left;
            white-space: normal;
            width: 100%;
          }

          div[data-testid="stButton"] > button:hover {
            background: var(--advisor-sky);
            border-color: #87bce6;
            color: var(--advisor-navy);
            transform: translateY(-1px);
          }

          [data-testid="stChatMessage"] {
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid var(--advisor-line);
            border-radius: 18px;
            box-shadow: 0 8px 24px rgba(36, 74, 107, 0.05);
            margin-bottom: 0.85rem;
            padding: 0.5rem 0.7rem;
          }

          [data-testid="stChatMessage"]:has(
            [data-testid="stChatMessageAvatarUser"]
          ) {
            background: var(--advisor-sky);
            border-color: #c9e4f8;
          }

          [data-testid="stChatMessage"] [data-testid="stCaptionContainer"] {
            color: var(--advisor-muted);
            font-size: 0.76rem;
          }

          [data-testid="stChatInput"] {
            background: white;
            border: 1px solid #cbddea;
            border-radius: 18px;
            box-shadow: 0 12px 32px rgba(21, 66, 102, 0.14);
          }

          .advisor-footer {
            color: var(--advisor-muted);
            font-size: 0.78rem;
            line-height: 1.5;
            margin-top: 2rem;
            text-align: center;
          }

          @media (max-width: 640px) {
            .block-container { padding-top: 1rem; }
            .advisor-hero {
              border-radius: 18px;
              padding: 1.7rem 1.4rem;
            }
            .advisor-hero h1 { font-size: 2rem; }
            .advisor-trust { align-items: flex-start; flex-direction: column; }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
