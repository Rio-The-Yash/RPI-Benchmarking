#!/usr/bin/env bash
set -u
cd "$HOME/RPI-Benchmarking"
for m in qwen3.5:4b-q4_K_M vinci-piccolo:q4; do
  tag=$(echo "$m" | tr ':/' '__')
  echo "=== $(date -Is) START $m ==="
  printf '0\n' | ./run_ollama_benchmark.sh "$m" 2>&1 | tee "sweep_$tag.log"
  echo "=== $(date -Is) END $m ==="
  sleep 30
done
echo "ALL RERUNS DONE"
