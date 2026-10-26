#!/bin/bash

set -u

# ============================================================
# SimpleDirect Raspberry Pi benchmark - Ollama backend
# ============================================================
# Usage:
#   ./run_ollama_benchmark.sh <ollama-model-tag>
#   ./run_ollama_benchmark.sh qwen3:1.7b
#   ./run_ollama_benchmark.sh llama3.2:3b --no-warmup
# ============================================================

BENCHMARK_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$BENCHMARK_DIR/.venv/bin/python"
OLLAMA_HOST_URL="http://127.0.0.1:11434"

MODEL="${1:-}"
WARMUP=1

if [ "${2:-}" = "--no-warmup" ]; then
    WARMUP=0
fi

if [ -z "$MODEL" ]; then
    echo "Usage: $0 <ollama-model-tag> [--no-warmup]"
    echo
    echo "Installed models:"
    ollama list
    exit 1
fi

# ============================================================
# Environment check
# ============================================================

echo
echo "=========================================="
echo " SimpleDirect Raspberry Pi Benchmark"
echo " Backend: Ollama"
echo "=========================================="
echo

SETUP_NEEDED=0

if [ ! -x "$VENV_PYTHON" ]; then
    echo " - Python virtual environment missing"
    SETUP_NEEDED=1
elif ! "$VENV_PYTHON" -c "import psutil, requests" >/dev/null 2>&1; then
    echo " - Python packages psutil/requests missing"
    SETUP_NEEDED=1
fi

if ! command -v ollama >/dev/null 2>&1; then
    echo " - Ollama missing"
    SETUP_NEEDED=1
fi

if [ "$SETUP_NEEDED" -eq 1 ]; then
    echo
    echo "Running setup_ollama.sh..."
    echo
    "$BENCHMARK_DIR/setup_ollama.sh" || exit 1
fi

# ============================================================
# Ollama reachability and model presence
# ============================================================

if ! curl -fsS "$OLLAMA_HOST_URL/api/tags" >/dev/null 2>&1; then
    echo "ERROR: Ollama API is not reachable at $OLLAMA_HOST_URL"
    echo "Try: sudo systemctl restart ollama"
    exit 1
fi

if ! ollama list | awk 'NR>1 {print $1}' | grep -qx "$MODEL"; then
    echo
    echo "Model '$MODEL' is not installed."
    read -r -p "Pull it now? [Y/n] " answer

    case "$answer" in
        [nN]*) echo "Aborted."; exit 1 ;;
    esac

    ollama pull "$MODEL" || exit 1
fi

# ============================================================
# Warm-up
# ============================================================
# Loading a model from disk takes 10-60 seconds on a Pi. Warming up
# keeps model load out of the first prompt's TTFT, and keep_alive
# stops Ollama unloading the model mid-run.

if [ "$WARMUP" -eq 1 ]; then

    echo "Warming up $MODEL (loads weights, keep_alive 30m)..."

    curl -fsS "$OLLAMA_HOST_URL/api/generate" \
        -d "{\"model\":\"$MODEL\",\"prompt\":\"hi\",\"stream\":false,\"keep_alive\":\"30m\",\"options\":{\"num_predict\":1}}" \
        >/dev/null || {
            echo "ERROR: Warm-up request failed."
            exit 1
        }

    echo "Model loaded."
    echo

fi

# ============================================================
# Run the benchmark
# ============================================================

export BENCHMARK_BACKEND="ollama"
export BENCHMARK_SERVER_URL="$OLLAMA_HOST_URL/v1/chat/completions"
export BENCHMARK_MODEL_NAME="$MODEL"
export BENCHMARK_MODEL_REPO="ollama/$MODEL"
export BENCHMARK_QUANTIZATION="$(ollama show "$MODEL" 2>/dev/null | awk -F': *' '/quantization/ {print $2; exit}')"
export BENCHMARK_HARDWARE_LABEL="Raspberry Pi 5 (16 GB, CPU)"

[ -n "${BENCHMARK_QUANTIZATION:-}" ] || export BENCHMARK_QUANTIZATION="unknown"

echo "Model:        $MODEL"
echo "Quantization: $BENCHMARK_QUANTIZATION"
echo "Endpoint:     $BENCHMARK_SERVER_URL"
echo

"$VENV_PYTHON" "$BENCHMARK_DIR/benchmark.py"

echo
echo "Benchmark finished. Results are in:"
echo "$BENCHMARK_DIR/results"
echo
