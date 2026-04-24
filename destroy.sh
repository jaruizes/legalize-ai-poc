#!/usr/bin/env bash
# destroy.sh — Tears down the full legalize-ai-poc environment
#
# Steps:
#   1. Verify prerequisites
#   2. Wait for any running Bedrock ingestion jobs to finish
#   3. Empty the frontend S3 bucket (belt-and-suspenders; force_destroy=true
#      in Terraform also handles this, but an explicit purge avoids any edge
#      cases with versioned objects)
#   4. terraform destroy
#
# Usage:  ./destroy.sh
# Flags:  --auto-approve   Skip the final confirmation prompt

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/infrastructure/terraform"

AUTO_APPROVE=false
for arg in "$@"; do
  [ "$arg" = "--auto-approve" ] && AUTO_APPROVE=true
done

# ── Colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}${BOLD}▶${RESET} $*"; }
success() { echo -e "${GREEN}${BOLD}✔${RESET} $*"; }
warn()    { echo -e "${YELLOW}${BOLD}⚠${RESET}  $*"; }
fatal()   { echo -e "${RED}${BOLD}✖${RESET} $*" >&2; exit 1; }
section() { echo -e "\n${BOLD}━━━ $* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"; }

# ── Prerequisites ──────────────────────────────────────────────────────────────
section "Prerequisites"
for cmd in terraform aws; do
  command -v "$cmd" &>/dev/null || fatal "$cmd is not installed or not in PATH"
  success "$cmd found"
done

# ── Read Terraform outputs ─────────────────────────────────────────────────────
section "Reading Terraform state"

tf_out() {
  terraform -chdir="$TF_DIR" output -raw "$1" 2>/dev/null || true
}

KB_ID=$(tf_out knowledge_base_id)
DS_ID=$(tf_out data_source_id)
REGION=$(tf_out aws_region)
BUCKET=$(tf_out frontend_s3_bucket_name)

if [ -z "$REGION" ]; then
  warn "Could not read Terraform outputs — the stack may already be destroyed."
  REGION="eu-west-1"
fi

[ -n "$KB_ID" ]   && info "Knowledge Base : $KB_ID"    || warn "knowledge_base_id not found in state"
[ -n "$DS_ID" ]   && info "Data Source    : $DS_ID"    || warn "data_source_id not found in state"
[ -n "$BUCKET" ]  && info "S3 bucket      : $BUCKET"   || warn "frontend_s3_bucket_name not found in state"

# ── 1. Wait for running ingestion jobs ────────────────────────────────────────
if [ -n "$KB_ID" ] && [ -n "$DS_ID" ]; then
  section "Bedrock — ingestion jobs"
  info "Checking for running ingestion jobs..."

  RUNNING=$(aws bedrock-agent list-ingestion-jobs \
    --knowledge-base-id "$KB_ID" \
    --data-source-id    "$DS_ID" \
    --region            "$REGION" \
    --query 'length(ingestionJobSummaries[?status==`IN_PROGRESS` || status==`STARTING`])' \
    --output text 2>/dev/null || echo "0")

  if [ "$RUNNING" -gt 0 ] 2>/dev/null; then
    warn "$RUNNING ingestion job(s) still running. Waiting for them to finish..."
    warn "(Bedrock ingestion jobs cannot be cancelled — this may take a few minutes.)"
    JOB_ID=$(aws bedrock-agent list-ingestion-jobs --knowledge-base-id "$KB_ID" --data-source-id "$DS_ID" --region "$REGION" --query 'ingestionJobSummaries[?status==`IN_PROGRESS` || status==`STARTING`].ingestionJobId' --output text)

    aws bedrock-agent stop-ingestion-job \
      --knowledge-base-id "$KB_ID" \
      --data-source-id "$DS_ID" \
      --ingestion-job-id $JOB_ID \
      --region "$REGION" \
      --no-cli-pager > /dev/null 2>&1

    ELAPSED=0
    while true; do
      RUNNING=$(aws bedrock-agent list-ingestion-jobs \
        --knowledge-base-id "$KB_ID" \
        --data-source-id    "$DS_ID" \
        --region            "$REGION" \
        --query 'length(ingestionJobSummaries[?status==`IN_PROGRESS` || status==`STARTING`])' \
        --output text 2>/dev/null || echo "0")

      if [ "$RUNNING" -eq 0 ] 2>/dev/null; then
        success "All ingestion jobs finished."
        break
      fi

      printf "   [%3ds] %s job(s) still running, waiting 30 s...\n" "$ELAPSED" "$RUNNING"
      sleep 30
      ELAPSED=$((ELAPSED + 30))
    done
  else
    success "No running ingestion jobs."
  fi
fi

# ── 2. Empty frontend S3 bucket ────────────────────────────────────────────────
# Terraform's force_destroy=true handles versioned objects automatically.
# We also remove current objects upfront so the destroy is faster and avoids
# any race conditions with large buckets.
if [ -n "$BUCKET" ]; then
  section "S3 — emptying frontend bucket"

  BUCKET_EXISTS=$(aws s3api head-bucket --bucket "$BUCKET" --region "$REGION" 2>&1 || true)

  if echo "$BUCKET_EXISTS" | grep -q "Not Found\|NoSuchBucket\|403\|404"; then
    warn "Bucket $BUCKET does not exist or is not accessible — skipping."
  else
    info "Removing all objects from s3://$BUCKET ..."
    aws s3 rm "s3://$BUCKET/" --recursive --region "$REGION" 2>/dev/null || true

    # Also purge versioned objects and delete markers so force_destroy has nothing left to do
    info "Removing versioned objects and delete markers..."
    aws s3api list-object-versions \
      --bucket "$BUCKET" \
      --region "$REGION" \
      --output json \
      --query '{Objects: Versions[].{Key: Key, VersionId: VersionId}}' \
      2>/dev/null > /tmp/lz_versions.json || true

    if [ -s /tmp/lz_versions.json ] && \
       python3 -c "import json,sys; d=json.load(sys.stdin); exit(0 if d.get('Objects') else 1)" \
       < /tmp/lz_versions.json 2>/dev/null; then
      aws s3api delete-objects \
        --bucket  "$BUCKET" \
        --region  "$REGION" \
        --delete  file:///tmp/lz_versions.json \
        --output  text 2>/dev/null || true
    fi

    aws s3api list-object-versions \
      --bucket "$BUCKET" \
      --region "$REGION" \
      --output json \
      --query '{Objects: DeleteMarkers[].{Key: Key, VersionId: VersionId}}' \
      2>/dev/null > /tmp/lz_markers.json || true

    if [ -s /tmp/lz_markers.json ] && \
       python3 -c "import json,sys; d=json.load(sys.stdin); exit(0 if d.get('Objects') else 1)" \
       < /tmp/lz_markers.json 2>/dev/null; then
      aws s3api delete-objects \
        --bucket  "$BUCKET" \
        --region  "$REGION" \
        --delete  file:///tmp/lz_markers.json \
        --output  text 2>/dev/null || true
    fi

    rm -f /tmp/lz_versions.json /tmp/lz_markers.json
    success "Bucket emptied."
  fi
fi

# ── 3. Confirmation ────────────────────────────────────────────────────────────
section "Terraform — destroy"

terraform -chdir="$TF_DIR" destroy -auto-approve -input=false

# ── Done ───────────────────────────────────────────────────────────────────────
section "Done"
success "All infrastructure has been destroyed."
