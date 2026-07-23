# Managed AgentCore advising architecture

## One application path

`streamlit_app.py` is the only user-facing runtime. It is a thin client for an
Amazon Bedrock AgentCore Harness and keeps only display state plus the stable
AgentCore session/actor identifiers in `st.session_state`.

There is no React frontend, HTTP API, Lambda function, or DynamoDB session table
in the demo architecture.

## Responsibility boundaries

| Concern | Owner | Implementation |
|---|---|---|
| Student interview and individualized plan design | Model | AgentCore Harness |
| Conversation state and durable preferences | Managed service | AgentCore Memory |
| Model/tool loop, retries, context, and isolation | Managed service | AgentCore Harness |
| Tool governance and authentication | Managed service | AgentCore Gateway |
| Catalog, Cal-GETC, destination policy, and combined pathways | Retrieval | Managed Bedrock Knowledge Base |
| Prerequisites, units, offerings, articulation, and constraint checks | Deterministic validation | Python structured-store validator |

AgentCore owns the agent loop. Application code does not contain a second loop,
hardcoded questionnaire, or fixed schedule template.

## Runtime flow

1. Streamlit sends only the newest student turn to AgentCore Harness.
2. AgentCore restores session/actor memory and continues the model-led
   interview.
3. The Harness selects tools exposed through the IAM-authenticated Gateway.
4. The native managed-KB connector retrieves reviewed source chunks.
5. After enough student context exists, the model proposes an individualized
   plan.
6. Deterministic validation checks that exact proposal and returns factual
   errors and warnings; it never chooses courses or constructs a schedule.
7. The model revises until the exact proposal passes, then explains the result
   with retrieved evidence and counselor-verification boundaries.

The managed KB path is live. The validation function is implemented locally;
deploying it as an AgentCore Runtime MCP server and attaching it to the Gateway
is the next infrastructure slice. Until then, the Harness is instructed not to
emit term-by-term schedules.

## Data publication

1. Source adapters write local raw snapshots.
2. Transforms normalize and validate the data.
3. A reviewer approves blocking prerequisite, articulation, and destination
   policy decisions.
4. The published structured store is rebuilt.
5. `build_kb_content.py` generates KB-ready catalog, Cal-GETC area, and
   combined major-plus-GE pathway documents; reviewed FAQs are published beside
   them.
6. Generated KB artifacts are uploaded to S3 and the managed Knowledge Base
   data source is synchronized.

The Knowledge Base is the readable projection used for retrieval. Structured
JSON and reviewed CSV policy remain the source for exact validation. A KB
answer never replaces prerequisite checking, articulation checking, or final
counselor review.
