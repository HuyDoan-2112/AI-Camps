"""Thin application client for Amazon Bedrock AgentCore Harness.

AgentCore owns conversation history, model calls, tool selection, retries, and
memory. This client only sends the newest user turn and translates the event
stream into UI-friendly events.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HarnessEvent:
    kind: str
    text: str = ""
    data: dict[str, Any] | None = None


@dataclass(frozen=True)
class HarnessReply:
    text: str
    activity: tuple[dict[str, Any], ...] = ()
    usage: dict[str, Any] | None = None
    stop_reason: str | None = None


class HarnessClient:
    def __init__(
        self,
        harness_arn: str,
        *,
        region_name: str = "us-west-2",
        qualifier: str | None = None,
        client: Any = None,
    ) -> None:
        if not harness_arn:
            raise ValueError("harness_arn must not be empty")
        if client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("boto3 is required for AgentCore Harness") from exc
            client = boto3.client("bedrock-agentcore", region_name=region_name)
        self._client = client
        self._harness_arn = harness_arn
        self._qualifier = qualifier

    def stream(
        self,
        prompt: str,
        *,
        session_id: str,
        actor_id: str | None = None,
        completed_courses: list[str] | None = None,
    ) -> Iterator[HarnessEvent]:
        """Invoke one managed turn and yield normalized streaming events.

        The same ``session_id`` must be reused for subsequent turns; AgentCore
        Memory restores prior messages, so the application does not resend the
        full chat history.
        """
        if len(session_id) < 33:
            raise ValueError("AgentCore runtime session IDs must contain at least 33 characters")
        if not prompt.strip():
            raise ValueError("prompt must not be empty")

        message = prompt.strip()
        if completed_courses is not None:
            course_text = ", ".join(sorted({course.upper() for course in completed_courses}))
            message = (
                "Student-provided transcript context: completed AVC courses are "
                f"{course_text or 'none'}. Treat this only as completed-course context; "
                "do not infer grades or ability.\n\n"
                f"Student message: {message}"
            )

        request: dict[str, Any] = {
            "harnessArn": self._harness_arn,
            "runtimeSessionId": session_id,
            "messages": [{"role": "user", "content": [{"text": message}]}],
        }
        if actor_id:
            request["actorId"] = actor_id
            request["runtimeUserId"] = actor_id
        if self._qualifier:
            request["qualifier"] = self._qualifier

        response = self._client.invoke_harness(**request)
        for event in response["stream"]:
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"].get("delta") or {}
                if delta.get("text"):
                    yield HarnessEvent("text", text=delta["text"])
                if delta.get("toolResultMetadata"):
                    yield HarnessEvent(
                        "tool_metadata",
                        text=delta["toolResultMetadata"].get("metadata", ""),
                    )
            elif "contentBlockStart" in event:
                start = event["contentBlockStart"].get("start") or {}
                tool = start.get("toolUse")
                if tool:
                    yield HarnessEvent(
                        "tool_start",
                        text=tool.get("name", "tool"),
                        data={
                            "tool_use_id": tool.get("toolUseId"),
                            "server": tool.get("serverName"),
                            "type": tool.get("type"),
                        },
                    )
            elif "messageStop" in event:
                yield HarnessEvent(
                    "stop",
                    text=event["messageStop"].get("stopReason", ""),
                )
            elif "metadata" in event:
                yield HarnessEvent("metadata", data=event["metadata"])
            else:
                for error_key in (
                    "runtimeClientError",
                    "validationException",
                    "internalServerException",
                ):
                    if error_key in event:
                        error = event[error_key]
                        message_text = error.get("message") or str(error)
                        raise RuntimeError(f"AgentCore Harness {error_key}: {message_text}")

    def reply(
        self,
        prompt: str,
        *,
        session_id: str,
        actor_id: str | None = None,
        completed_courses: list[str] | None = None,
    ) -> HarnessReply:
        text_parts: list[str] = []
        activity: list[dict[str, Any]] = []
        usage: dict[str, Any] | None = None
        stop_reason: str | None = None

        for event in self.stream(
            prompt,
            session_id=session_id,
            actor_id=actor_id,
            completed_courses=completed_courses,
        ):
            if event.kind == "text":
                text_parts.append(event.text)
            elif event.kind in {"tool_start", "tool_metadata"}:
                activity.append({"kind": event.kind, "text": event.text, **(event.data or {})})
            elif event.kind == "metadata":
                usage = event.data
            elif event.kind == "stop":
                stop_reason = event.text

        return HarnessReply(
            text="".join(text_parts).strip(),
            activity=tuple(activity),
            usage=usage,
            stop_reason=stop_reason,
        )


def client_from_env() -> HarnessClient:
    harness_arn = os.environ.get("AGENTCORE_HARNESS_ARN", "").strip()
    if not harness_arn:
        raise RuntimeError(
            "Set AGENTCORE_HARNESS_ARN to the deployed AgentCore Harness ARN."
        )
    return HarnessClient(
        harness_arn,
        region_name=os.environ.get("AWS_REGION", "us-west-2"),
        qualifier=os.environ.get("AGENTCORE_HARNESS_ENDPOINT") or None,
    )
