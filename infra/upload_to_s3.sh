#!/usr/bin/env bash
# Upload reviewed local data to the raw and processed S3 buckets. Run this from
# a machine with the AWS CLI configured.
#
# Two zones, two different bars:
#   - Raw zone: immutable dated snapshots of what was fetched. Low-stakes --
#     doesn't claim anything is reviewed, just mirrors data/raw/.
#   - Processed zone: the exact structured store and KB-ready prose. Uploading
#     KB files affects retrieval after the Bedrock data source is synchronized,
#     so the script asks for confirmation.
#
# Usage:
#   RAW_BUCKET=transfer-raw PROCESSED_BUCKET=transfer-processed infra/upload_to_s3.sh
#   infra/upload_to_s3.sh --skip-processed   # raw zone only

set -euo pipefail

RAW_BUCKET="${RAW_BUCKET:-transfer-raw}"
PROCESSED_BUCKET="${PROCESSED_BUCKET:-transfer-processed}"
SNAPSHOT_DATE="$(date -u +%Y-%m-%d)"
SKIP_PROCESSED=false

for arg in "$@"; do
  case "$arg" in
    --skip-processed) SKIP_PROCESSED=true ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Raw bucket:       $RAW_BUCKET"
echo "Processed bucket: $PROCESSED_BUCKET"
echo "Snapshot date:    $SNAPSHOT_DATE"
echo

# --- Raw zone: dated snapshots, mirrors data/raw/ ---
if [ -d "$ROOT/data/raw/assist" ]; then
  aws s3 sync "$ROOT/data/raw/assist" \
    "s3://$RAW_BUCKET/source=assist/date=$SNAPSHOT_DATE/" \
    --only-show-errors
  echo "Uploaded ASSIST raw snapshots."
fi

if [ -d "$ROOT/data/raw/banner" ]; then
  aws s3 sync "$ROOT/data/raw/banner" \
    "s3://$RAW_BUCKET/source=banner/date=$SNAPSHOT_DATE/" \
    --only-show-errors
  echo "Uploaded Banner raw snapshots."
fi

echo

# --- Processed zone: published structured store and KB source documents ---
if [ "$SKIP_PROCESSED" = true ]; then
  echo "Skipping processed zone (--skip-processed)."
  exit 0
fi

if [ ! -d "$ROOT/data/processed/structured_store" ]; then
  echo "No structured store found at data/processed/structured_store -- run"
  echo "scripts/build_structured_store.py first."
  exit 0
fi

if [ ! -d "$ROOT/data/processed/kb" ]; then
  echo "No KB content found at data/processed/kb -- run"
  echo "scripts/build_kb_content.py first."
  exit 1
fi

echo "About to publish reviewed structured data and KB prose to $PROCESSED_BUCKET."
echo "Synchronizing the Bedrock data source afterward will change demo retrieval."
read -r -p "Publish these artifacts? [y/N] " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
  echo "Skipped processed zone."
  exit 0
fi

aws s3 sync "$ROOT/data/processed/structured_store" \
  "s3://$PROCESSED_BUCKET/structured_store/" \
  --only-show-errors
echo "Uploaded structured store."

aws s3 sync "$ROOT/data/processed/kb" \
  "s3://$PROCESSED_BUCKET/kb/" \
  --only-show-errors
echo "Uploaded Knowledge Base source documents. Synchronize the kb/ data source next."
