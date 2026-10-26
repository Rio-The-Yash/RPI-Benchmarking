#!/bin/bash

set -u

# ============================================================
# Paths / Configuration
# ============================================================

LLAMA_DIR="$HOME/llama.cpp"
BENCHMARK_DIR="$(cd "$(dirname "$0")" && pwd)"

MODEL="$BENCHMARK_DIR/models/Vinci-Piccolo-1.0-Q4_K_M.gguf"
SETUP_SCRIPT="$BENCHMARK_DIR/setup.sh"

PORT=8080
SERVER_PID=""

# ============================================================
# Cleanup
# ============================================================

cleanup() {
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        echo
        echo "Stopping llama-server..."
        kill "$SERVER_PID" 2>/dev/null
        wait "$SERVER_PID" 2>/dev/null
    fi
}

trap cleanup EXIT INT TERM

echo
echo "=========================================="
echo " SimpleDirect Mac Mini Benchmark"
echo "=========================================="
echo

# ============================================================
# Check whether setup is required
# ============================================================

SETUP_NEEDED=0

echo "Checking benchmark environment..."

if [ ! -x "$LLAMA_DIR/build/bin/llama-server" ]; then
    echo "  - llama-server missing"
    SETUP_NEEDED=1
fi

if [ ! -f "$MODEL" ]; then
    echo "  - Vinci-Piccolo model missing"
    SETUP_NEEDED=1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "  - Python 3 missing"
    SETUP_NEEDED=1
else

    if ! python3 -c "import psutil" >/dev/null 2>&1; then
        echo "  - Python package psutil missing"
        SETUP_NEEDED=1
    fi

    if ! python3 -c "import requests" >/dev/null 2>&1; then
        echo "  - Python package requests missing"
        SETUP_NEEDED=1
    fi

fi

if ! command -v macmon >/dev/null 2>&1; then
    echo "  - macmon missing"
    SETUP_NEEDED=1
fi

# ============================================================
# Automatically run setup when required
# ============================================================

if [ "$SETUP_NEEDED" -eq 1 ]; then

    echo
    echo "=========================================="
    echo " Setup required"
    echo "=========================================="
    echo
    echo "Some required components are missing."
    echo "Running setup.sh automatically..."
    echo

    if [ ! -f "$SETUP_SCRIPT" ]; then
        echo "ERROR: setup.sh was not found:"
        echo "$SETUP_SCRIPT"
        exit 1
    fi

    chmod +x "$SETUP_SCRIPT"

    if ! "$SETUP_SCRIPT"; then
        echo
        echo "ERROR: setup.sh failed."
        echo "Benchmark cannot continue."
        exit 1
    fi

    echo
    echo "=========================================="
    echo " Setup completed"
    echo "=========================================="
    echo

else

    echo "Environment ready."
    echo "Setup not required."
    echo

fi

# ============================================================
# Verify environment after setup
# ============================================================

if [ ! -x "$LLAMA_DIR/build/bin/llama-server" ]; then
    echo "ERROR: llama-server was not found:"
    echo "$LLAMA_DIR/build/bin/llama-server"
    exit 1
fi

if [ ! -f "$MODEL" ]; then
    echo "ERROR: Model file was not found:"
    echo "$MODEL"
    exit 1
fi

if ! python3 -c "import psutil, requests" >/dev/null 2>&1; then
    echo "ERROR: Required Python packages are missing."
    exit 1
fi

if ! command -v macmon >/dev/null 2>&1; then
    echo "ERROR: macmon is missing."
    exit 1
fi

# ============================================================
# Check port
# ============================================================

if lsof -iTCP:${PORT} -sTCP:LISTEN >/dev/null 2>&1; then
    echo "ERROR: Port ${PORT} is already in use."
    echo "Stop the existing llama-server and try again."
    exit 1
fi

# ============================================================
# Start llama-server
# ============================================================

cd "$LLAMA_DIR" || exit 1

echo "Starting Vinci-Piccolo..."
echo

# ============================================================
# Measure startup time
# ============================================================
# Start timing before llama-server launches so this includes
# the complete server/model startup period.

START_TIME=$(python3 - <<'PY'
import time
print(time.time())
PY
)

./build/bin/llama-server \
    -m "$MODEL" \
    -ngl 99 \
    --host 127.0.0.1 \
    --port "$PORT" \
    > "$BENCHMARK_DIR/llama-server-mac.log" 2>&1 &

SERVER_PID=$!

echo "llama-server PID: $SERVER_PID"
echo "Waiting for model to load..."

READY=0

for i in $(seq 1 180); do

    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo
        echo "ERROR: llama-server stopped during startup."
        echo
        echo "Last server log lines:"
        tail -30 "$BENCHMARK_DIR/llama-server-mac.log"
        exit 1
    fi

    if curl -s "http://127.0.0.1:${PORT}/health" \
        | grep -q '"status":"ok"'; then

        READY=1
        break
    fi

    sleep 1

done

if [ "$READY" -ne 1 ]; then
    echo
    echo "ERROR: Server did not become ready."
    echo
    echo "Last server log lines:"
    tail -30 "$BENCHMARK_DIR/llama-server-mac.log"
    exit 1
fi

END_TIME=$(python3 - <<'PY'
import time
print(time.time())
PY
)

STARTUP_TIME=$(python3 - <<PY
start = float("$START_TIME")
end = float("$END_TIME")
print(f"{end - start:.2f}")
PY
)

echo
echo "Model ready."
echo "Startup/load time: ${STARTUP_TIME} seconds"
echo

# ============================================================
# Run benchmark
# ============================================================

cd "$BENCHMARK_DIR" || exit 1

# Pass the measured startup time and model metadata to benchmark.py.
export MODEL_STARTUP_TIME="$STARTUP_TIME"
export BENCHMARK_MODEL_NAME="Vinci-Piccolo-1.0-GGUF"
export BENCHMARK_MODEL_REPO="simpledirect/Vinci-Piccolo-1.0-GGUF"
export BENCHMARK_QUANTIZATION="Q4_K_M"

python3 benchmark.py
BENCHMARK_EXIT=$?

echo

if [ "$BENCHMARK_EXIT" -eq 0 ]; then

    echo "=========================================="
    echo " Benchmark finished"
    echo "=========================================="
    echo
    echo "Model startup/load time: ${STARTUP_TIME} seconds"

else

    echo "=========================================="
    echo " Benchmark failed"
    echo "=========================================="
    echo
    echo "benchmark.py exited with code: $BENCHMARK_EXIT"

    exit "$BENCHMARK_EXIT"

fi