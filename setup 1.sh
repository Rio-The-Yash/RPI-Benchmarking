#!/bin/bash

set -e

# ============================================================
# RPI-Benchmarking Setup for Raspberry Pi
# ============================================================

BENCHMARK_DIR="$(cd "$(dirname "$0")" && pwd)"
LLAMA_DIR="$HOME/llama.cpp"

MODEL_DIR="$BENCHMARK_DIR/models"
MODEL_FILE="$MODEL_DIR/Vinci-Piccolo-1.0-Q4_K_M.gguf"

echo
echo "=========================================="
echo " RPI-Benchmarking Setup (Raspberry Pi)"
echo "=========================================="
echo
echo "Benchmark directory:"
echo "$BENCHMARK_DIR"
echo

# --------------------------------------------------
# Check Raspberry Pi OS
# --------------------------------------------------

if [ "$(uname -s)" != "Linux" ]; then
    echo "ERROR: This setup script is intended for Linux (Raspberry Pi OS)."
    exit 1
fi

if [ "$(uname -m)" != "aarch64" ]; then
    echo "ERROR: This setup requires aarch64 architecture (Raspberry Pi). Current: $(uname -m)"
    exit 1
fi

echo "System:"
echo "  Raspberry Pi OS ($(cat /etc/os-release | grep VERSION_ID | head -1 | tr -d '\"'))"
echo "  Architecture: $(uname -m)"
echo

# --------------------------------------------------
# Required command-line tools (Debian/apt)
# --------------------------------------------------

echo "Checking required tools..."

for package in git cmake python3 curl; do
    if ! command -v "$package" >/dev/null 2>&1; then
        echo "Installing $package..."
        sudo apt-get update -qq && sudo apt-get install -y -qq "$package"
    else
        echo "$package found."
    fi
done

# --------------------------------------------------
# Python dependencies
# --------------------------------------------------

echo
echo "Installing/checking Python dependencies..."

python3 -m pip install --user psutil requests

# --------------------------------------------------
# Create model directory
# --------------------------------------------------

mkdir -p "$MODEL_DIR"
echo "Model directory:"
echo "$MODEL_DIR"
echo

# --------------------------------------------------
# Download Vinci-Piccolo model
# --------------------------------------------------

echo
echo "Checking Vinci-Piccolo model..."

MODEL_VALID=0

if [ -s "$MODEL_FILE" ]; then
    MODEL_SIZE="$(wc -c < "$MODEL_FILE" | tr -d ' ')"
    MODEL_HEADER="$(head -c 4 "$MODEL_FILE" 2>/dev/null || true)"

    if [ "$MODEL_SIZE" -gt 1000000000 ] && \
       [ "$MODEL_HEADER" = "GGUF" ]; then
        MODEL_VALID=1
    fi
fi

if [ "$MODEL_VALID" -eq 1 ]; then
    echo "Vinci-Piccolo model already exists."
    echo "$MODEL_FILE"
else
    echo "Model not found. Downloading Vinci-Piccolo Q4_K_M..."
    echo

    # Find the current Q4_K_M GGUF filename directly from Hugging Face
    MODEL_URL=$(python3 - <<'PY'
import json
from urllib.parse import quote
from urllib.request import urlopen

repo = "simpledirect/Vinci-Piccolo-1.0-GGUF"

with urlopen(
    f"https://huggingface.co/api/models/{repo}",
    timeout=30
) as response:
    files = json.load(response)["siblings"]

matches = [
    item["rfilename"]
    for item in files
    if item["rfilename"].lower().endswith(".gguf")
    and "Q4_K_M" in item["rfilename"].upper()
]

if len(matches) != 1:
    raise SystemExit(
        f"Expected one Q4_K_M GGUF file; found: {matches}"
    )

filename = matches[0]

print(
    f"https://huggingface.co/{repo}/resolve/main/"
    f"{quote(filename, safe='/')}"
)
PY
)

    if [ -z "$MODEL_URL" ]; then
        echo "ERROR: Could not determine model download URL."
        exit 1
    fi

    PART_FILE="$MODEL_FILE.part"

    echo "Downloading model..."
    echo

    curl \
        --location \
        --fail \
        --retry 3 \
        --continue-at - \
        --progress-bar \
        --output "$PART_FILE" \
        "$MODEL_URL"

    echo

    if [ ! -s "$PART_FILE" ]; then
        echo "ERROR: Model download failed."
        exit 1
    fi

    MODEL_SIZE="$(wc -c < "$PART_FILE" | tr -d ' ')"
    MODEL_HEADER="$(head -c 4 "$PART_FILE" 2>/dev/null || true)"

    if [ "$MODEL_SIZE" -le 1000000000 ] || \
       [ "$MODEL_HEADER" != "GGUF" ]; then

        echo "ERROR: Downloaded file is incomplete or not a GGUF model."
        exit 1

    fi

    mv "$PART_FILE" "$MODEL_FILE"

    echo
    echo "Model downloaded successfully."
fi

# --------------------------------------------------
# Build llama.cpp with KleidiAI for ARM AArch64
# --------------------------------------------------

echo
echo "Building llama.cpp for aarch64 CPU..."
echo

rm -rf "$LLAMA_DIR"

git clone https://github.com/ggerganov/llama.cpp "$LLAMA_DIR"

cd "$LLAMA_DIR"

# Enable KleidiAI CPU microkernels for better performance on ARM Cortex-A76
cmake -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DGGML_CPU_KLEIDIAI=ON

cmake --build build --config Release -j$(nproc)

if [ ! -x "$LLAMA_DIR/build/bin/llama-server" ]; then
    echo "ERROR: llama-server build failed."
    exit 1
fi

# --------------------------------------------------
# Make scripts executable
# --------------------------------------------------

chmod +x "$BENCHMARK_DIR/run_benchmark.sh"
chmod +x "$BENCHMARK_DIR/setup.sh"

# --------------------------------------------------
# Final verification
# --------------------------------------------------

echo
echo "Verifying installation..."

FAILED=0

if [ ! -x "$LLAMA_DIR/build/bin/llama-server" ]; then
    echo "ERROR: llama-server missing."
    FAILED=1
fi

if [ ! -f "$MODEL_FILE" ]; then
    echo "ERROR: Vinci-Piccolo model missing."
    FAILED=1
fi

if ! python3 -c "import psutil, requests" >/dev/null 2>&1; then
    echo "ERROR: Required Python packages are missing."
    FAILED=1
fi

if [ "$FAILED" -ne 0 ]; then
    echo
    echo "ERROR: Setup verification failed."
    exit 1
fi

echo
echo "=========================================="
echo " Setup complete"
echo "=========================================="
echo
echo "llama-server:"
echo "$LLAMA_DIR/build/bin/llama-server"
echo
echo "Model:"
echo "$MODEL_FILE"
echo
echo "Setup verification passed."
