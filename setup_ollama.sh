#!/bin/bash

set -e

# ============================================================
# SimpleDirect Raspberry Pi setup - Ollama backend
# ============================================================
# No llama.cpp build required. Only the benchmark scripts, a Python
# virtual environment and a running Ollama server are needed.
# ============================================================

BENCHMARK_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$BENCHMARK_DIR/.venv"

echo
echo "=========================================="
echo " SimpleDirect Pi Setup (Ollama backend)"
echo "=========================================="
echo

# --------------------------------------------------
# Check 64-bit Raspberry Pi OS
# --------------------------------------------------

ARCH="$(uname -m)"

if [ "$ARCH" != "aarch64" ] && [ "$ARCH" != "arm64" ]; then
    echo "ERROR: 64-bit Raspberry Pi OS is required (found $ARCH)."
    exit 1
fi

echo "Device: $(cat /proc/device-tree/model 2>/dev/null | tr -d '\0' || echo unknown)"
echo "Architecture: $ARCH"
echo

# --------------------------------------------------
# System packages
# --------------------------------------------------

PACKAGES="python3 python3-venv python3-pip curl lsof"
MISSING=""

for package in $PACKAGES; do
    if ! dpkg -s "$package" >/dev/null 2>&1; then
        MISSING="$MISSING $package"
    fi
done

if [ -n "$MISSING" ]; then
    echo "Installing:$MISSING"
    sudo apt-get update
    sudo apt-get install -y $MISSING
else
    echo "System packages already installed."
fi

# --------------------------------------------------
# Ollama check
# --------------------------------------------------

if ! command -v ollama >/dev/null 2>&1; then
    echo
    echo "Ollama is not installed."
    echo "Install it with:"
    echo "  curl -fsSL https://ollama.com/install.sh | sh"
    exit 1
fi

if ! systemctl is-active --quiet ollama; then
    echo "Ollama service is not running. Starting it..."
    sudo systemctl enable --now ollama
fi

if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "Ollama API is reachable on port 11434."
else
    echo "ERROR: Ollama API is not answering on 127.0.0.1:11434."
    exit 1
fi

# --------------------------------------------------
# Python environment
# --------------------------------------------------

echo
echo "Checking Python dependencies..."

if [ ! -x "$VENV_DIR/bin/python" ]; then
    python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null
"$VENV_DIR/bin/python" -m pip install psutil requests

mkdir -p "$BENCHMARK_DIR/results"

chmod +x "$BENCHMARK_DIR/run_ollama_benchmark.sh" 2>/dev/null || true

echo
echo "=========================================="
echo " Setup complete"
echo "=========================================="
echo
echo "Installed models:"
ollama list || true
echo
echo "Run a benchmark with:"
echo "  ./run_ollama_benchmark.sh qwen3:1.7b"
echo
