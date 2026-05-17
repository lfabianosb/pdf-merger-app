#!/usr/bin/env bash
# Launch the PDF Merger backend using the project virtual environment
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV"
fi

# Ensure dependencies are installed
"$VENV/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt" 2>/dev/null || "$VENV/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

# Check for system-level Tesseract OCR (required by ocrmypdf)
if ! command -v tesseract &>/dev/null; then
    echo "⚠  WARNING: tesseract is not installed. OCR features will be unavailable."
    echo "   Install it with:"
    echo "     Ubuntu/Debian: sudo apt install tesseract-ocr tesseract-ocr-eng"
    echo "     macOS:         brew install tesseract"
    echo "     Fedora:        sudo dnf install tesseract"
    echo ""
fi

echo "Starting PDF Merger API on http://127.0.0.1:8000"
exec "$VENV/bin/uvicorn" main:app --host 127.0.0.1 --port 8000 --reload "$@"
