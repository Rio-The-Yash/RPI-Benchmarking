# RPI-Benchmarking (Raspberry Pi)

Benchmarks the **simpledirect/Vinci-Piccolo** model on a **Raspberry Pi 5** using llama.cpp, collecting system telemetry (CPU/RAM usage, temperatures, power estimates) across 4 LLM profiles.

## Requirements

- **Raspberry Pi 5** running Raspberry Pi OS (64-bit)
- ARM Cortex-A76 cores with KleidiAI CPU microkernels
- llama.cpp built for aarch64

## Setup

```bash
./setup.sh        # Installs dependencies, downloads Vinci-Piccolo model, builds llama.cpp
```

Or run setup manually:

```bash
sudo apt-get update && sudo apt-get install -y git cmake python3 curl
python3 -m pip install --user psutil requests
cd llama.cpp && \
  cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_CPU_KLEIDIAI=ON && \
  cmake --build build --config Release -j$(nproc)
mkdir -p models && curl -L https://huggingface.co/simpledirect/Vinci-Piccolo-1.0-GGUF/resolve/main/Vinci-Piccolo-1.0-Q4_K_M.gguf -o models/Vinci-Piccolo-1.0-Q4_K_M.gguf
```

## Running

```bash
./run_benchmark.sh
```

The benchmark runs 24 prompts (4 profiles × 6 prompts) and outputs CSV, JSON responses, and raw session files in `results/`.

## Hardware Profile

| Component | Detail |
|-----------|--------|
| CPU | ARM Cortex-A76 4x + Cortex-A53 4x @ 1.6 GHz |
| Memory | 4 GB LPDDR4 (unified) |
| GPU | VideoCore VII — not supported by llama.cpp |
| Accel | CPU only (no GPU offload) |

## Telemetry

Temperature via `vcgencmd measure_temp`. Power estimates via `vcgencmd get_config` + GPIO stats. No external monitoring tools needed.
