# AWS resources used by the Streamlit demo

The application uses:

- one private S3 raw-data bucket;
- one private S3 processed-data/Knowledge-Base source bucket;
- one managed Amazon Bedrock Knowledge Base;
- one IAM-authenticated AgentCore Gateway with a managed-KB connector;
- one AgentCore Harness with managed memory;
- one Bedrock text-generation inference profile.

The demo does not require Lambda, DynamoDB, API Gateway, Amplify, or a separate
frontend deployment.

## Environment

```bash
export AWS_REGION=us-west-2
export BEDROCK_KB_ID=<managed-knowledge-base-id>
BEDROCK_KB_ID="$BEDROCK_KB_ID" \
  .venv/bin/python infra/deploy_agentcore.py --bootstrap-iam
```

The deployer creates or updates two scoped execution roles in development mode.
It prints the Harness ARN required by Streamlit. `BEDROCK_MODEL_ID` is an
optional override for the model pinned in `agentcore/config.json`.

The execution roles grant the managed core only the required model, Gateway,
managed-memory, and selected Knowledge Base actions, including:

- `bedrock:AgenticRetrieveStream`
- `bedrock:Retrieve`
- `bedrock:GetDocumentContent`
- `bedrock:InvokeModel`
- `bedrock-agentcore:InvokeGateway`
- `bedrock-agentcore:CreateEvent`
- `bedrock-agentcore:ListEvents`
- `bedrock-agentcore:RetrieveMemoryRecords`

Scope resources to the selected Knowledge Base and model wherever the AWS API
supports resource-level permissions.

## Data upload

Build and review the local data first, then run:

```bash
RAW_BUCKET=transfer-raw \
PROCESSED_BUCKET=transfer-processed \
infra/upload_to_s3.sh
```

The processed upload includes both:

- `structured_store/`, used by local deterministic tools and retained in S3 as
  a published copy;
- `kb/`, used as the managed Knowledge Base data-source prefix.

After uploading `kb/`, synchronize the Knowledge Base data source in the
Bedrock console or with the AWS SDK.

## Cost controls

- Keep the Knowledge Base managed and confirm its current pricing.
- Bound Harness iterations, output tokens, and timeout in
  `agentcore/config.json`.
- Configure an AWS Budget alert before sharing the demo broadly.
- Do not place long-lived AWS access keys in Streamlit source or Git.
