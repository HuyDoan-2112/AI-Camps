"""Pure configuration tests for the AgentCore deployment payloads."""

from __future__ import annotations

import unittest

from infra.deploy_agentcore import (
    build_advisor_tools_schema,
    build_advisor_tools_target_configuration,
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

    def test_advisor_lambda_target_exposes_live_and_validation_tools(self) -> None:
        function_arn = "arn:aws:lambda:us-west-2:123456789012:function:AdvisorTools"
        target = build_advisor_tools_target_configuration(function_arn)
        tools = build_advisor_tools_schema()

        lambda_target = target["mcp"]["lambda"]
        self.assertEqual(lambda_target["lambdaArn"], function_arn)
        self.assertEqual(
            [tool["name"] for tool in tools],
            ["get_live_course_sections", "validate_transfer_plan"],
        )
        validator_schema = tools[1]["inputSchema"]
        self.assertEqual(
            validator_schema["properties"]["terms"]["items"]["type"],
            "object",
        )
        self.assertIn("terms", validator_schema["required"])


if __name__ == "__main__":
    unittest.main()
