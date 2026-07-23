"""Pure configuration tests for the AgentCore deployment payloads."""

from __future__ import annotations

import unittest

from infra.deploy_agentcore import (
    build_harness_configuration,
    build_kb_target_configuration,
)


class AgentCoreDeploymentConfigurationTest(unittest.TestCase):
    def test_kb_target_binds_id_outside_agent_visible_input(self) -> None:
        target = build_kb_target_configuration("KB123", generate_response=False)
        connector = target["mcp"]["connector"]
        self.assertEqual(connector["source"]["connectorId"], "bedrock-knowledge-bases")
        agentic = connector["configurations"][0]
        values = agentic["parameterValues"]
        self.assertEqual(
            values["retrievers"][0]["configuration"]["knowledgeBase"]["knowledgeBaseId"],
            "KB123",
        )
        self.assertFalse(values["generateResponse"])

    def test_harness_uses_gateway_only_and_managed_memory(self) -> None:
        config = {
            "gateway_tool_name": "advisor-data",
            "max_iterations": 8,
            "max_tokens": 6000,
            "timeout_seconds": 120,
            "memory": {
                "managedMemoryConfiguration": {
                    "strategies": ["SUMMARIZATION", "USER_PREFERENCE"],
                    "eventExpiryDuration": 30,
                }
            },
        }
        payload = build_harness_configuration(
            config=config,
            gateway_arn="arn:example:gateway",
            execution_role_arn="arn:example:role",
            model_id=None,
        )
        self.assertNotIn("model", payload)
        self.assertEqual(payload["allowedTools"], ["@advisor-data/*"])
        self.assertEqual(payload["tools"][0]["type"], "agentcore_gateway")
        self.assertIn("managedMemoryConfiguration", payload["memory"])


if __name__ == "__main__":
    unittest.main()
