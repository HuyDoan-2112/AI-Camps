"""Provision or update the managed AgentCore Harness core flow.

This script is intentionally idempotent. It can create narrowly scoped
development IAM roles when ``--bootstrap-iam`` is supplied, then creates or
updates:

1. an IAM-authenticated AgentCore Gateway;
2. a native managed-Knowledge-Base connector target;
3. an AgentCore Harness that uses the Gateway and managed memory.

The deterministic academic validator will be added to the same Gateway as an
MCP target; it is not part of this first managed-KB deployment.

Usage:
    BEDROCK_KB_ID=... python infra/deploy_agentcore.py --bootstrap-iam

Optional:
    BEDROCK_MODEL_ID=...        # overrides agentcore/config.json
    AGENTCORE_HARNESS_ROLE_ARN=...
    AGENTCORE_GATEWAY_ROLE_ARN=...
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import boto3

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "agentcore" / "config.json"
PROMPT_PATH = ROOT / "agentcore" / "system_prompt.md"

HARNESS_ROLE_NAME = "AvcTransferAdvisorBedrockAgentCoreHarnessRole"
GATEWAY_ROLE_NAME = "AvcTransferAdvisorBedrockAgentCoreGatewayRole"
ROLE_POLICY_NAME = "AvcTransferAdvisorRuntimeAccess"


def _load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def build_kb_target_configuration(
    knowledge_base_id: str,
    *,
    generate_response: bool,
) -> dict[str, Any]:
    return {
        "mcp": {
            "connector": {
                "source": {"connectorId": "bedrock-knowledge-bases"},
                "configurations": [
                    {
                        "name": "AgenticRetrieveStream",
                        "parameterValues": {
                            "retrievers": [
                                {
                                    "description": (
                                        "Reviewed AVC transfer pathways, major preparation, "
                                        "destination GE policy, Cal-GETC, catalog, and FAQs"
                                    ),
                                    "configuration": {
                                        "knowledgeBase": {
                                            "knowledgeBaseId": knowledge_base_id
                                        }
                                    },
                                }
                            ],
                            "agenticRetrieveConfiguration": {
                                "foundationModelType": "MANAGED",
                                "rerankingModelType": "MANAGED",
                            },
                            "generateResponse": generate_response,
                        },
                    },
                    {
                        "name": "Retrieve",
                        "parameterValues": {"knowledgeBaseId": knowledge_base_id},
                    },
                ],
            }
        }
    }


def build_harness_configuration(
    *,
    config: dict[str, Any],
    gateway_arn: str,
    execution_role_arn: str,
    model_id: str | None,
) -> dict[str, Any]:
    gateway_tool_name = config["gateway_tool_name"]
    payload: dict[str, Any] = {
        "executionRoleArn": execution_role_arn,
        "systemPrompt": [{"text": PROMPT_PATH.read_text(encoding="utf-8")}],
        "tools": [
            {
                "type": "agentcore_gateway",
                "name": gateway_tool_name,
                "config": {
                    "agentCoreGateway": {
                        "gatewayArn": gateway_arn,
                        "outboundAuth": {"awsIam": {}},
                    }
                },
            }
        ],
        # Built-in shell/file tools are not needed for student advising.
        "allowedTools": [f"@{gateway_tool_name}/*"],
        "memory": config["memory"],
        "maxIterations": int(config["max_iterations"]),
        "maxTokens": int(config["max_tokens"]),
        "timeoutSeconds": int(config["timeout_seconds"]),
    }
    if model_id:
        payload["model"] = {
            "bedrockModelConfig": {
                "modelId": model_id,
                "apiFormat": "converse_stream",
            }
        }
    return payload


def _role_trust_policy(account_id: str, region: str) -> dict[str, Any]:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": account_id},
                    "ArnLike": {
                        "aws:SourceArn": (
                            f"arn:aws:bedrock-agentcore:{region}:{account_id}:*"
                        )
                    },
                },
            }
        ],
    }


def _gateway_role_policy(
    *,
    account_id: str,
    region: str,
    knowledge_base_id: str,
) -> dict[str, Any]:
    kb_arn = f"arn:aws:bedrock:{region}:{account_id}:knowledge-base/{knowledge_base_id}"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "ManagedKnowledgeBaseAgenticRetrieval",
                "Effect": "Allow",
                "Action": [
                    "bedrock:AgenticRetrieveStream",
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                "Resource": "*",
            },
            {
                "Sid": "ReadSelectedManagedKnowledgeBase",
                "Effect": "Allow",
                "Action": [
                    "bedrock:GetKnowledgeBase",
                    "bedrock:Retrieve",
                    "bedrock:GetDocumentContent",
                ],
                "Resource": kb_arn,
            },
        ],
    }


def _harness_role_policy(
    gateway_arn: str,
    *,
    account_id: str,
    region: str,
) -> dict[str, Any]:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "InvokeConfiguredBedrockModels",
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                "Resource": "*",
            },
            {
                "Sid": "InvokeAdvisorGateway",
                "Effect": "Allow",
                "Action": "bedrock-agentcore:InvokeGateway",
                "Resource": gateway_arn,
            },
            {
                "Sid": "UseHarnessManagedMemory",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:CreateEvent",
                    "bedrock-agentcore:ListEvents",
                    "bedrock-agentcore:RetrieveMemoryRecords",
                ],
                # The managed memory ID is allocated by CreateHarness, after
                # this execution role must already exist.
                "Resource": (
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:memory/*"
                ),
            },
        ],
    }


def _ensure_role(
    iam: Any,
    *,
    name: str,
    trust_policy: dict[str, Any],
    permissions_policy: dict[str, Any],
) -> str:
    try:
        role = iam.get_role(RoleName=name)["Role"]
        iam.update_assume_role_policy(
            RoleName=name,
            PolicyDocument=json.dumps(trust_policy),
        )
    except iam.exceptions.NoSuchEntityException:
        role = iam.create_role(
            RoleName=name,
            Description="AVC Transfer Advisor Amazon Bedrock AgentCore execution role",
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Tags=[
                {"Key": "Project", "Value": "avc-transfer-advisor"},
                {"Key": "ManagedBy", "Value": "infra/deploy_agentcore.py"},
            ],
        )["Role"]
    iam.put_role_policy(
        RoleName=name,
        PolicyName=ROLE_POLICY_NAME,
        PolicyDocument=json.dumps(permissions_policy),
    )
    return role["Arn"]


def _find_by_name(items: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in items
            if (item.get("name") or item.get("harnessName")) == name
        ),
        None,
    )


def _wait_until_ready(
    getter,
    *,
    label: str,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        item = getter()
        status = item.get("status")
        if status in {"READY", "ACTIVE"}:
            return item
        if status in {"CREATE_FAILED", "UPDATE_FAILED", "FAILED", "DELETING"}:
            raise RuntimeError(f"{label} entered terminal status {status}: {item}")
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for {label} to become ready")


def _ensure_gateway(control: Any, *, name: str, role_arn: str) -> dict[str, Any]:
    existing = _find_by_name(control.list_gateways().get("items", []), name)
    if existing is None:
        gateway = control.create_gateway(
            name=name,
            description="Governed tool access for the AVC transfer advising harness",
            roleArn=role_arn,
            protocolType="MCP",
            authorizerType="AWS_IAM",
            tags={"Project": "avc-transfer-advisor"},
        )
        gateway_id = gateway["gatewayId"]
    else:
        gateway_id = existing["gatewayId"]
        control.update_gateway(
            gatewayIdentifier=gateway_id,
            name=name,
            description="Governed tool access for the AVC transfer advising harness",
            roleArn=role_arn,
            protocolType="MCP",
            authorizerType="AWS_IAM",
        )
    return _wait_until_ready(
        lambda: control.get_gateway(gatewayIdentifier=gateway_id),
        label=f"gateway {name}",
    )


def _ensure_kb_target(
    control: Any,
    *,
    gateway_id: str,
    name: str,
    target_configuration: dict[str, Any],
) -> dict[str, Any]:
    targets = control.list_gateway_targets(gatewayIdentifier=gateway_id).get("items", [])
    existing = _find_by_name(targets, name)
    credentials = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
    if existing is None:
        target = control.create_gateway_target(
            gatewayIdentifier=gateway_id,
            name=name,
            description="Native connector to the reviewed AVC managed Knowledge Base",
            targetConfiguration=target_configuration,
            credentialProviderConfigurations=credentials,
        )
        target_id = target["targetId"]
    else:
        target_id = existing["targetId"]
        control.update_gateway_target(
            gatewayIdentifier=gateway_id,
            targetId=target_id,
            name=name,
            description="Native connector to the reviewed AVC managed Knowledge Base",
            targetConfiguration=target_configuration,
            credentialProviderConfigurations=credentials,
        )
    return _wait_until_ready(
        lambda: control.get_gateway_target(
            gatewayIdentifier=gateway_id,
            targetId=target_id,
        ),
        label=f"gateway target {name}",
    )


def _ensure_harness(
    control: Any,
    *,
    name: str,
    configuration: dict[str, Any],
) -> dict[str, Any]:
    existing = _find_by_name(control.list_harnesses().get("harnesses", []), name)
    if existing is None:
        response = control.create_harness(
            harnessName=name,
            **configuration,
            tags={"Project": "avc-transfer-advisor"},
        )
        harness_id = response["harness"]["harnessId"]
    else:
        harness_id = existing["harnessId"]
        update_configuration = dict(configuration)
        update_configuration["memory"] = {"optionalValue": configuration["memory"]}
        control.update_harness(harnessId=harness_id, **update_configuration)
    return _wait_until_ready(
        lambda: control.get_harness(harnessId=harness_id)["harness"],
        label=f"harness {name}",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bootstrap-iam",
        action="store_true",
        help="Create/update the two scoped AgentCore execution roles.",
    )
    args = parser.parse_args()

    config = _load_config()
    region = os.environ.get("AWS_REGION", "us-west-2")
    knowledge_base_id = os.environ.get("BEDROCK_KB_ID", "").strip()
    if not knowledge_base_id:
        raise SystemExit("Set BEDROCK_KB_ID to the managed Knowledge Base to connect.")
    model_id = (
        os.environ.get("BEDROCK_MODEL_ID", "").strip()
        or config.get("model_id")
        or None
    )

    session = boto3.Session(region_name=region)
    sts = session.client("sts")
    iam = session.client("iam")
    control = session.client("bedrock-agentcore-control")
    account_id = sts.get_caller_identity()["Account"]
    trust = _role_trust_policy(account_id, region)

    gateway_role_arn = os.environ.get("AGENTCORE_GATEWAY_ROLE_ARN", "").strip()
    harness_role_arn = os.environ.get("AGENTCORE_HARNESS_ROLE_ARN", "").strip()
    if args.bootstrap_iam:
        gateway_role_arn = _ensure_role(
            iam,
            name=GATEWAY_ROLE_NAME,
            trust_policy=trust,
            permissions_policy=_gateway_role_policy(
                account_id=account_id,
                region=region,
                knowledge_base_id=knowledge_base_id,
            ),
        )
        # Create with regional Gateway scope; tighten to the exact Gateway below.
        harness_role_arn = _ensure_role(
            iam,
            name=HARNESS_ROLE_NAME,
            trust_policy=trust,
            permissions_policy=_harness_role_policy(
                f"arn:aws:bedrock-agentcore:{region}:{account_id}:gateway/*",
                account_id=account_id,
                region=region,
            ),
        )
        # IAM role propagation is eventually consistent.
        time.sleep(5)
    elif not gateway_role_arn or not harness_role_arn:
        raise SystemExit(
            "Set AGENTCORE_GATEWAY_ROLE_ARN and AGENTCORE_HARNESS_ROLE_ARN, "
            "or rerun with --bootstrap-iam."
        )

    gateway = _ensure_gateway(
        control,
        name=config["gateway_name"],
        role_arn=gateway_role_arn,
    )
    gateway_arn = gateway["gatewayArn"]
    gateway_id = gateway["gatewayId"]

    if args.bootstrap_iam:
        _ensure_role(
            iam,
            name=HARNESS_ROLE_NAME,
            trust_policy=trust,
            permissions_policy=_harness_role_policy(
                gateway_arn,
                account_id=account_id,
                region=region,
            ),
        )
        time.sleep(3)

    _ensure_kb_target(
        control,
        gateway_id=gateway_id,
        name=config["knowledge_base_target_name"],
        target_configuration=build_kb_target_configuration(
            knowledge_base_id,
            generate_response=bool(config["knowledge_base_generate_response"]),
        ),
    )
    harness = _ensure_harness(
        control,
        name=config["harness_name"],
        configuration=build_harness_configuration(
            config=config,
            gateway_arn=gateway_arn,
            execution_role_arn=harness_role_arn,
            model_id=model_id,
        ),
    )

    print("AgentCore managed flow is ready.")
    print(f"AGENTCORE_HARNESS_ARN={harness['arn']}")
    print("AGENTCORE_HARNESS_ENDPOINT=DEFAULT")
    print(f"AGENTCORE_GATEWAY_ARN={gateway_arn}")
    print(f"BEDROCK_KB_ID={knowledge_base_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
