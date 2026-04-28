#!/usr/bin/env bash
# start.sh — Full environment bootstrap for advanced-ai-poc
#
# Steps:
#   1. Verify prerequisites
#   2. terraform init + apply
#   3. Build & deploy Angular app to S3 / CloudFront
#   4. Start Bedrock Knowledge Base ingestion and wait for completion
#
# Usage:  ./start.sh
# Flags:  --skip-frontend   Skip Angular build/deploy
#         --skip-ingestion  Skip KB ingestion (useful for re-deploys)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/infrastructure/terraform"
DEPLOY_SCRIPT="$SCRIPT_DIR/scripts/deploy-frontend.sh"

SKIP_FRONTEND=false
SKIP_INGESTION=false

for arg in "$@"; do
  case $arg in
    --skip-frontend)  SKIP_FRONTEND=true  ;;
    --skip-ingestion) SKIP_INGESTION=true ;;
  esac
done

# ── Colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}${BOLD}▶${RESET} $*"; }
success() { echo -e "${GREEN}${BOLD}✔${RESET} $*"; }
warn()    { echo -e "${YELLOW}${BOLD}⚠${RESET}  $*"; }
fatal()   { echo -e "${RED}${BOLD}✖${RESET} $*" >&2; exit 1; }
section() { echo -e "\n${BOLD}━━━ $* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"; }

# ── 1. Prerequisites ───────────────────────────────────────────────────────────
section "Prerequisites"

for cmd in terraform aws node npm; do
  if command -v "$cmd" &>/dev/null; then
    success "$cmd $(${cmd} --version 2>&1 | head -1)"
  else
    fatal "$cmd is not installed or not in PATH"
  fi
done

# ── 2. Terraform init + apply ──────────────────────────────────────────────────
section "Terraform — init"
info "Initialising providers and modules..."
terraform -chdir="$TF_DIR" init -upgrade -input=false

section "Terraform — pre-flight"
# When a previous destroy fails mid-way, some resources can remain in AWS but
# be absent from the Terraform state. The S3 frontend bucket is the most common
# victim: AWS returns 409 BucketAlreadyOwnedByYou instead of the normal conflict
# error, which trips up Terraform. We detect this case and import the bucket so
# the subsequent apply can proceed cleanly.
#
# The bucket name mirrors the formula in main.tf:
#   ${var.project}-${var.environment}-frontend-${account_id}-${region_short}
# We respect TF_VAR_* overrides so custom projects/envs work too.
_TF_PROJECT="${TF_VAR_project:-radar-ai-poc}"
_TF_ENV="${TF_VAR_environment:-dev}"
_REGION=$(aws configure get region 2>/dev/null || echo "eu-west-1")
_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || true)
_REGION_SHORT=$(echo "$_REGION" | awk -F'-' '{print substr($1,1,2) substr($2,1,1) $3}')
_FRONTEND_BUCKET="${_TF_PROJECT}-${_TF_ENV}-frontend-${_ACCOUNT_ID}-${_REGION_SHORT}"

if [ -n "$_ACCOUNT_ID" ] && aws s3api head-bucket --bucket "$_FRONTEND_BUCKET" --region "$_REGION" 2>/dev/null; then
  if ! terraform -chdir="$TF_DIR" state show 'module.frontend.aws_s3_bucket.frontend' &>/dev/null; then
    warn "Bucket '$_FRONTEND_BUCKET' exists in AWS but is missing from state (leftover from a failed destroy)."
    info "Importing bucket into Terraform state..."
    terraform -chdir="$TF_DIR" import 'module.frontend.aws_s3_bucket.frontend' "$_FRONTEND_BUCKET"
    success "Bucket imported — apply will proceed without attempting to create it."
  else
    success "Bucket '$_FRONTEND_BUCKET' already tracked in state."
  fi
fi

section "Terraform — apply"
warn "This provisions OpenSearch Serverless and Bedrock Knowledge Base."
warn "First-time deployment typically takes 10–15 minutes."
terraform -chdir="$TF_DIR" apply -auto-approve -input=false

success "Infrastructure ready."

# ── Clean up Lambda ZIPs ───────────────────────────────────────────────────────
section "Cleanup — Lambda ZIPs"
for zip in \
  "$SCRIPT_DIR/infrastructure/terraform/modules/api/lambda/ask/handler.zip" \
  "$SCRIPT_DIR/lambda/enricher.zip"
do
  if [ -f "$zip" ]; then
    rm "$zip"
    success "Removed $zip"
  fi
done

# ── Read outputs ───────────────────────────────────────────────────────────────
section "Reading outputs"

tf_out() { terraform -chdir="$TF_DIR" output -raw "$1"; }

KB_ID=$(tf_out knowledge_base_id)
DS_ID=$(tf_out data_source_id)
REGION=$(tf_out aws_region)
CF_URL=$(tf_out cloudfront_url)
BUCKET=$(tf_out frontend_s3_bucket_name)
DIST_ID=$(tf_out frontend_cloudfront_distribution_id)

info "Knowledge Base  : $KB_ID"
info "Data Source     : $DS_ID"
info "Region          : $REGION"
info "S3 bucket       : $BUCKET"
info "CloudFront dist : $DIST_ID"

# ── 3. Build & deploy Angular app ─────────────────────────────────────────────
if [ "$SKIP_FRONTEND" = false ]; then
  section "Frontend — build & deploy"
  bash "$DEPLOY_SCRIPT"
else
  warn "Skipping frontend deploy (--skip-frontend)"
fi

# ── 4. Bedrock KB ingestion ────────────────────────────────────────────────────
section "Bedrock — Knowledge Base ingestion"
info "Starting ingestion job for data source $DS_ID ..."
JOB_ID=$(aws bedrock-agent start-ingestion-job \
    --knowledge-base-id "$KB_ID" \
    --data-source-id   "$DS_ID" \
    --region           "$REGION" \
    --query 'ingestionJob.ingestionJobId' \
    --output text)

success "Ingestion job started: $JOB_ID"

# ── Done ───────────────────────────────────────────────────────────────────────
section "Done"
success "Environment is ready!"
echo -e "\n  ${BOLD}🌐 App URL:${RESET} ${GREEN}${CF_URL}${RESET}\n"
