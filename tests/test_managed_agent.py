"""Unit tests for the AgentCore Harness application boundary."""

from __future__ import annotations

import unittest

from transfer_advisor.managed_agent import HarnessClient


class FakeHarnessClient:
    def __init__(self, events):
        self.events = events
        self.requests = []

    def invoke_harness(self, **request):
        self.requests.append(request)
        return {"stream": iter(self.events)}


class HarnessClientTest(unittest.TestCase):
    def test_sends_only_current_turn_and_collects_stream(self) -> None:
        fake = FakeHarnessClient(
            [
                {"contentBlockDelta": {"delta": {"text": "Hello "}}},
                {
                    "contentBlockStart": {
                        "start": {
                            "toolUse": {
                                "name": "managed-kb___AgenticRetrieveStream",
                                "toolUseId": "tool-1",
                                "type": "mcp_tool_use",
                            }
                        }
                    }
                },
                {"contentBlockDelta": {"delta": {"text": "student"}}},
                {"messageStop": {"stopReason": "end_turn"}},
                {
                    "metadata": {
                        "usage": {"inputTokens": 10, "outputTokens": 2, "totalTokens": 12},
                        "metrics": {"latencyMs": 25},
                    }
                },
            ]
        )
        client = HarnessClient("arn:example:harness", client=fake)
        reply = client.reply("Plan with me", session_id="s" * 33, actor_id="student-1")

        self.assertEqual(reply.text, "Hello student")
        self.assertEqual(reply.stop_reason, "end_turn")
        self.assertEqual(reply.activity[0]["kind"], "tool_start")
        request = fake.requests[0]
        self.assertEqual(
            request["messages"],
            [{"role": "user", "content": [{"text": "Plan with me"}]}],
        )
        self.assertEqual(request["actorId"], "student-1")

    def test_transcript_context_is_explicit_without_grades(self) -> None:
        fake = FakeHarnessClient(
            [
                {"contentBlockDelta": {"delta": {"text": "Thanks"}}},
                {"messageStop": {"stopReason": "end_turn"}},
            ]
        )
        client = HarnessClient("arn:example:harness", client=fake)
        client.reply(
            "What next?",
            session_id="s" * 33,
            completed_courses=["math150", "PHYS110", "MATH150"],
        )
        message = fake.requests[0]["messages"][0]["content"][0]["text"]
        self.assertIn("MATH150, PHYS110", message)
        self.assertIn("do not infer grades or ability", message)

    def test_stream_errors_are_raised(self) -> None:
        fake = FakeHarnessClient(
            [{"runtimeClientError": {"message": "gateway is unavailable"}}]
        )
        client = HarnessClient("arn:example:harness", client=fake)
        with self.assertRaisesRegex(RuntimeError, "gateway is unavailable"):
            client.reply("Hello", session_id="s" * 33)

    def test_rejects_short_session_id_before_calling_aws(self) -> None:
        fake = FakeHarnessClient([])
        client = HarnessClient("arn:example:harness", client=fake)
        with self.assertRaisesRegex(ValueError, "at least 33"):
            client.reply("Hello", session_id="short")
        self.assertEqual(fake.requests, [])


if __name__ == "__main__":
    unittest.main()
