#!/usr/bin/env bash

set -e

cd "$(dirname "$0")"

echo "🧪 Running Lambda tests..."

# Check if python3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ python3 is not installed"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install -q -r requirements.txt

# Run unit tests
echo ""
echo "🧪 Running unit tests..."
pytest test_local.py -v

# Run local handler test
echo ""
echo "🚀 Running local handler test..."
python3 test_handler.py

deactivate
