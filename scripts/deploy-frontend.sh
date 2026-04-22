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

echo "   S3 bucket    : $BUCKET_NAME"
echo "   Distribution : $DIST_ID"
echo "   App URL      : $CF_URL"

# ── 2. Install dependencies ───────────────────────────────────────────────────
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
