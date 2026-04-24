#!/usr/bin/env bash
# deploy-frontend.sh
# Builds the Angular app and deploys it to S3 + invalidates CloudFront.
#
# Usage:
#   ./scripts/deploy-frontend.sh
#
# Prerequisites:
#   - Node.js + npm installed
#   - AWS CLI configured with credentials that can write to S3 and CloudFront
#   - Terraform stack already applied (terraform apply)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TF_DIR="$ROOT_DIR/infrastructure/terraform"
APP_DIR="$ROOT_DIR/app"
BUILD_DIR="$APP_DIR/dist/consulta-leyes/browser"

# ── 1. Read Terraform outputs ──────────────────────────────────────────────────
echo "📋 Reading Terraform outputs..."
BUCKET_NAME=$(terraform -chdir="$TF_DIR" output -raw frontend_s3_bucket_name)
DIST_ID=$(terraform -chdir="$TF_DIR" output -raw frontend_cloudfront_distribution_id)
CF_URL=$(terraform -chdir="$TF_DIR" output -raw cloudfront_url)

# Read UI variables (handling potentially complex strings/lists)
UI_TITLE=$(terraform -chdir="$TF_DIR" output -raw ui_title 2>/dev/null || echo "Consulta leyes")
UI_SUBTITLE=$(terraform -chdir="$TF_DIR" output -raw ui_subtitle 2>/dev/null || echo "Pregunta sobre la legislación española y obtén respuestas con referencias a los documentos oficiales.")
UI_ICON=$(terraform -chdir="$TF_DIR" output -raw ui_icon 2>/dev/null || echo "⚖️")
UI_DISCLAIMER=$(terraform -chdir="$TF_DIR" output -raw ui_disclaimer 2>/dev/null || echo "Consulta leyes puede cometer errores. Verifica siempre la información con fuentes oficiales (BOE, BOJA, etc.).")
UI_EXAMPLES_JSON=$(terraform -chdir="$TF_DIR" output -json ui_examples 2>/dev/null || echo '[]')

echo "   S3 bucket    : $BUCKET_NAME"
echo "   Distribution : $DIST_ID"
echo "   App URL      : $CF_URL"
echo "   UI Title     : $UI_TITLE"

# ── 2. Inject UI variables into environment.ts ───────────────────────────────
echo ""
echo "💉 Injecting UI variables into environment.ts..."

python3 - <<EOF
import json
import os

env_path = "$APP_DIR/src/environments/environment.ts"
with open(env_path, "r") as f:
    content = f.read()

# Simple replacement strategy for our environment.ts structure
ui_config = {
    "title": """$UI_TITLE""",
    "subtitle": """$UI_SUBTITLE""",
    "icon": """$UI_ICON""",
    "examples": json.loads("""$UI_EXAMPLES_JSON"""),
    "disclaimer": """$UI_DISCLAIMER"""
}

# Find the ui: { ... } block and replace it
import re
new_ui_str = "ui: " + json.dumps(ui_config, indent=4, ensure_ascii=False)
content = re.sub(r"ui:\s*\{[\s\S]*?\}", new_ui_str, content)

with open(env_path, "w") as f:
    f.write(content)
EOF

# ── 3. Install dependencies ───────────────────────────────────────────────────
echo ""
echo "📦 Installing npm dependencies..."
cd "$APP_DIR"
npm install --prefer-offline --no-audit --no-fund

# ── 3. Build Angular app (production) ─────────────────────────────────────────
echo ""
echo "🔨 Building Angular app (production)..."
npm run build

if [ ! -d "$BUILD_DIR" ]; then
  echo "❌ Build output not found at $BUILD_DIR"
  exit 1
fi

# ── 4. Upload to S3 ────────────────────────────────────────────────────────────
echo ""
echo "☁️  Uploading to s3://$BUCKET_NAME ..."

# index.html — no cache so browsers always fetch the latest version
aws s3 cp \
  "$BUILD_DIR/index.html" \
  "s3://$BUCKET_NAME/index.html" \
  --cache-control "no-cache, no-store, must-revalidate" \
  --content-type "text/html"

# All other files — long-lived cache (Angular adds content hashes to filenames)
aws s3 sync \
  "$BUILD_DIR/" \
  "s3://$BUCKET_NAME/" \
  --delete \
  --exclude "index.html" \
  --cache-control "public, max-age=31536000, immutable"

echo "   Upload complete."

# ── 5. Invalidate CloudFront cache ─────────────────────────────────────────────
echo ""
echo "🔄 Invalidating CloudFront cache (distribution: $DIST_ID)..."
INVALIDATION_ID=$(aws cloudfront create-invalidation \
  --distribution-id "$DIST_ID" \
  --paths "/*" \
  --query 'Invalidation.Id' \
  --output text)
echo "   Invalidation ID: $INVALIDATION_ID"
echo "   (propagation takes ~1 min globally)"

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
echo "✅ Deploy complete!"
echo "🌐 App available at: $CF_URL"
