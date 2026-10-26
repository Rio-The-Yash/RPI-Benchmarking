#!/bin/bash

set -e

# ============================================================
# SimpleDirect Mac Mini Setup
# ============================================================

BENCHMARK_DIR="$(cd "$(dirname "$0")" && pwd)"
LLAMA_DIR="$HOME/llama.cpp"

MODEL_DIR="$BENCHMARK_DIR/models"
MODEL_FILE="$MODEL_DIR/Vinci-Piccolo-1.0-Q4_K_M.gguf"

echo
echo "=========================================="
echo " SimpleDirect Mac Mini Setup"
echo "=========================================="
echo
echo "Benchmark directory:"
echo "$BENCHMARK_DIR"
echo

# --------------------------------------------------
# Check macOS / Apple Silicon
# --------------------------------------------------

if [ "$(uname -s)" != "Darwin" ]; then
    echo "ERROR: This setup script is intended for macOS."
    exit 1
fi

echo "System:"
echo "  macOS $(sw_vers -productVersion)"
echo "  Architecture: $(uname -m)"
echo

# --------------------------------------------------
# Homebrew
# --------------------------------------------------

echo "Checking Homebrew..."

if command -v brew >/dev/null 2>&1; then
    BREW_BIN="$(command -v brew)"

elif [ -x /opt/homebrew/bin/brew ]; then
    BREW_BIN="/opt/homebrew/bin/brew"

elif [ -x /usr/local/bin/brew ]; then
    BREW_BIN="/usr/local/bin/brew"

else
    echo
    echo "Homebrew not found."
    echo "Installing Homebrew..."
    echo

    /bin/bash -c \
        "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    if [ -x /opt/homebrew/bin/brew ]; then
        BREW_BIN="/opt/homebrew/bin/brew"

    elif [ -x /usr/local/bin/brew ]; then
        BREW_BIN="/usr/local/bin/brew"

    else
        echo "ERROR: Homebrew installation could not be verified."
        exit 1
    fi
fi

BREW_PREFIX="$("$BREW_BIN" --prefix)"
export PATH="$BREW_PREFIX/bin:$PATH"

echo "Homebrew found:"
echo "$BREW_BIN"

# --------------------------------------------------
# Required command-line tools
# --------------------------------------------------

echo
echo "Checking required tools..."

for package in cmake git curl python; do

    case "$package" in
        python)
            COMMAND="python3"
            FORMULA="python"
            ;;
        *)
            COMMAND="$package"
            FORMULA="$package"
            ;;
    esac

    if ! command -v "$COMMAND" >/dev/null 2>&1; then
        echo "Installing $FORMULA..."
        "$BREW_BIN" install "$FORMULA"
    else
        echo "$COMMAND found."
    fi

done

# --------------------------------------------------
# Python dependencies
# --------------------------------------------------

echo
echo "Installing/checking Python dependencies..."

python3 -m pip install --user psutil requests

# --------------------------------------------------
# macmon
# --------------------------------------------------

echo
echo "Checking macmon..."

if ! command -v macmon >/dev/null 2>&1; then

    echo "macmon not found."
    echo "Installing macmon..."

    "$BREW_BIN" install macmon

else

    echo "macmon found."

fi

# Refresh Homebrew PATH after installation.
export PATH="$("$BREW_BIN" --prefix)/bin:$PATH"

if ! command -v macmon >/dev/null 2>&1; then
    echo "ERROR: macmon installation could not be verified."
    exit 1
fi

# --------------------------------------------------
# llama.cpp
# --------------------------------------------------

echo
echo "Checking llama.cpp..."

if [ ! -d "$LLAMA_DIR/.git" ]; then

    if [ -e "$LLAMA_DIR" ]; then
        echo "Existing $LLAMA_DIR is not a valid llama.cpp Git repository."
        echo "Removing incomplete directory..."
        rm -rf "$LLAMA_DIR"
    fi

    echo "Cloning llama.cpp..."

    git clone https://github.com/ggerganov/llama.cpp.git "$LLAMA_DIR"

else

    echo "llama.cpp repository already exists."

fi

# --------------------------------------------------
# Build llama.cpp with Metal
# --------------------------------------------------

echo
echo "Checking llama-server build..."

cd "$LLAMA_DIR"

if [ ! -x "$LLAMA_DIR/build/bin/llama-server" ]; then

    echo "llama-server not found."
    echo "Building llama.cpp with Metal support..."
    echo

    rm -rf build

    cmake -B build \
        -DGGML_METAL=ON \
        -DCMAKE_BUILD_TYPE=Release

    cmake --build build --config Release -j

else

    echo "llama-server already built."

fi

if [ ! -x "$LLAMA_DIR/build/bin/llama-server" ]; then
    echo "ERROR: llama-server build failed."
    exit 1
fi

# --------------------------------------------------
# Create model directory
# --------------------------------------------------

echo
echo "Checking model directory..."

mkdir -p "$MODEL_DIR"

echo "Model directory:"
echo "$MODEL_DIR"

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

    echo "Model not found."
    echo "Downloading Vinci-Piccolo Q4_K_M..."
    echo

    # Find the current Q4_K_M GGUF filename directly from
    # the Hugging Face repository.
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

if ! command -v macmon >/dev/null 2>&1; then
    echo "ERROR: macmon missing."
    FAILED=1
fi

if [ "$FAILED" -ne 0 ]; then
    echo
    echo "ERROR: Setup verification failed."
    exit 1
fi

# --------------------------------------------------
# Setup complete
# --------------------------------------------------

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
echo