#!/usr/bin/env bash

set -e

cd "$(dirname "$0")"

echo "Running enricher Lambda tests..."

if ! command -v python3 &> /dev/null; then
    echo "python3 is not installed"
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Installing dependencies..."
pip install -q -r requirements.txt

echo ""
echo "Running unit tests..."
pytest test_handler.py -v

echo ""
echo "Running local handler test..."
python3 test_local.py

deactivate
