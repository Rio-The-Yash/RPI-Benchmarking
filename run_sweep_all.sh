#!/usr/bin/env bash
set -u
cd "$HOME/RPI-Benchmarking"
for m in granite4:3b llama3.2:3b phi4-mini:3.8b qwen3.5:2b; do
  tag=$(echo "$m" | tr ':/' '__')
  echo "=== $(date -Is) START $m ==="
  printf '0\n' | ./run_ollama_benchmark.sh "$m" 2>&1 | tee "sweep_$tag.log"
  echo "=== $(date -Is) END $m ==="
  sleep 30
done
echo "ALL SWEEPS DONE"
