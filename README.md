# AVC Transfer & Pathway Advising Assistant

A Streamlit demonstration that combines:

- Amazon Bedrock AgentCore Harness for the model loop, conversation memory,
  tool selection, retries, and session isolation;
- an IAM-authenticated AgentCore Gateway;
- managed Amazon Bedrock Knowledge Base agentic retrieval for catalog,
  destination GE policy, Cal-GETC options, combined pathways, and advising
  prose;
- a deterministic validator for model-proposed plans. The validator checks
  facts and student constraints; it does not generate a schedule;
- Streamlit as a thin demo client.

Lambda, DynamoDB, FastAPI, and the React frontend are intentionally not part of
the demo architecture.

## Architecture

```text
Streamlit
  └─ Amazon Bedrock AgentCore Harness
       ├─ managed conversation memory and model-led student interview
       └─ AgentCore Gateway
            └─ AgenticRetrieveStream -> managed Knowledge Base
                 (major preparation + destination GE policy + Cal-GETC)
```

The Knowledge Base receives readable, generated projections of articulation
and Cal-GETC data so a retrieval-only answer includes both major preparation
and general education. The model designs an individualized plan only after it
has learned the student's goals and constraints. Deterministic code validates
the exact proposal; there is no fixed or greedy plan template.

The managed KB flow is deployed. The validator is implemented locally and is
the next Gateway MCP target; until that target is attached, the Harness is
configured not to emit a term-by-term schedule.

## Setup

Python 3.12 or later is supported.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

Configure AWS credentials using your normal AWS CLI or SSO flow, then export:

```bash
export AWS_REGION=us-west-2
export BEDROCK_KB_ID=<managed-knowledge-base-id>
```

Deploy or update the managed core. The checked-in default model is
`us.anthropic.claude-sonnet-4-6`; `BEDROCK_MODEL_ID` can override it.

```bash
BEDROCK_KB_ID="$BEDROCK_KB_ID" \
  .venv/bin/python infra/deploy_agentcore.py --bootstrap-iam
export AGENTCORE_HARNESS_ARN=<ARN printed by the deployer>
export AGENTCORE_HARNESS_ENDPOINT=DEFAULT
```

Run the app:

```bash
.venv/bin/streamlit run streamlit_app.py
```

## Data workflow

```bash
.venv/bin/python scripts/validate_config.py
.venv/bin/python scripts/fetch_assist_seed.py
.venv/bin/python scripts/fetch_banner_backfill.py
.venv/bin/python scripts/build_reviewed_prereqs.py
.venv/bin/python scripts/build_structured_store.py
.venv/bin/python scripts/build_kb_content.py
```

`data/raw/` and intermediate transforms remain ignored. The small published
runtime store under `data/processed/structured_store/` and the KB-ready files
under `data/processed/kb/` are versioned so tests and Streamlit work from a
clean clone.

Upload reviewed data using [`infra/upload_to_s3.sh`](infra/upload_to_s3.sh),
then sync the managed Knowledge Base data source in Amazon Bedrock. Generated
files under `data/processed/kb/` are pipeline outputs, not runtime-generated
answers.

## Verification

```bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m compileall -q src scripts streamlit_app.py tests
```

The advising output is a planning aid, not a registration guarantee. Verify
course eligibility, articulation, and the final plan with a counselor.
