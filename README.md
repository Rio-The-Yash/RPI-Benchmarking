# RPI-Benchmarking (Raspberry Pi)

Benchmarks the **simpledirect/Vinci-Piccolo** model on a **Raspberry Pi 5** using llama.cpp, collecting system telemetry (CPU/RAM usage, temperatures, power estimates) across 4 LLM profiles.

## Hardware requirements

- **Raspberry Pi 5** (aarch64)
- 4 GB LPDDR4 (unified memory) — or larger
- ARM Cortex-A76 4x + Cortex-A53 4x @ 1.6 GHz

> NOTE: llama.cpp cannot use the VideoCore VII GPU for inference on Pi. Inference runs entirely on CPU. No eGPU setup is possible within this project as-is.

## Quick start (single command)

```bash
cd ~/Projects/RPI-Benchmarking
./setup.sh && ./run_benchmark.sh
```

This will:
1. Install build dependencies (`cmake`, `python3`, `curl`).
2. Install Python deps (`psutil`, `requests`).
3. Download the Vinci-Piccolo Q4_K_M GGUF model (~1 GB).
4. Clone and build llama.cpp for aarch64 with KleidiAI CPU kernels.
5. Run `llama-server` in the background.
6. Launch `benchmark.py` against the server.
7. Collect telemetry throughout and save CSV/JSON/raw output files.

## Manual setup

If `./setup.sh` fails or you prefer control, do the steps manually:

### 1. Install dependencies

```bash
sudo apt-get update -qq && sudo apt-get install -y -qq git cmake python3 curl
python3 -m pip install --user psutil requests
sudo apt-get install -y vcgencmd    # needed for temperature monitoring
```

### 2. Download the model

```bash
mkdir -p models
curl -L https://huggingface.co/simpledirect/Vinci-Piccolo-1.0-GGUF/resolve/main/Vinci-Piccolo-1.0-Q4_K_M.gguf \
     -o models/Vinci-Piccolo-1.0-Q4_K_M.gguf
```

Verify the file header starts with `GGUF`:

```bash
head -c 4 models/Vinci-Piccolo-1.0-Q4_K_M.gguf
```

### 3. Build llama.cpp for aarch64

```bash
mkdir -p ~/llama.cpp
git clone https://github.com/ggerganov/llama.cpp ~/llama.cpp
cd ~/llama.cpp
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_CPU_KLEIDIAI=ON
cmake --build build --config Release -j$(nproc)
```

Check the build produced `build/bin/llama-server`. If it does not, see step 3 and try with additional CMake flags:

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release \
      -DGGML_CPU_KLEIDIAI=ON \
      -DCMAKE_CXX_FLAGS="-mcpu=cortex-a76 -mtune=cortex-a76"
```

Note: `nproc` may report 6 while there are only 4 physical cores in some board revisions. Use `cat /proc/cpuinfo | grep -c processor` to count logical cores instead.

### 4. Run the benchmark

```bash
cd ~/Projects/RPI-Benchmarking
./run_benchmark.sh
```

If the environment is already complete, it skips setup automatically and just runs the benchmark.

### 5. View results

Results are written to the `results/` directory next to the script:

| File | Contents |
|------|----------|
| `rpi5_YYYYMMDD_HHMMSS_all_profiles.csv` | One row per prompt, with latency, throughput, telemetry columns |
| `rpi5_YYYYMMDD_HHMMSS_responses.json` | Completed prompt answers |
| `rpi5_YYYYMMDD_HHMMSS_raw_session.txt` | Raw request/response stream including reasoning blocks |

## Configuration details

### Profiles (unchanged from original)

Each of the 4 profiles runs 6 prompts (1 main + 5 extras), 24 total per full pass:

| Profile | Temp | Thinking | Focus |
|---------|------|----------|-------|
| 1 – Thinking – General | 1.0 | ON | Energy strategy |
| 2 – Thinking – Precise Coding | 0.6 | ON | TypeScript algorithm design |
| 3 – Instruct – General | 0.7 | OFF | Educational explainers |
| 4 – Instruct – Reasoning | 1.0 | OFF | Operations optimization |

### Telemetry differences vs. macOS version

| Metric | Original (Mac Mini) | This version (Pi) |
|--------|-------------------|--------------------|
| CPU utilisation | psutil, per-core | psutil, per-core (same) |
| Memory | Virtual/swap | Virtual/swap (same) |
| CPU/GPU temp | macmon process | `vcgencmd measure_temp` (SoC temp, combined) |
| Power draw | `powermetrics` process | Estimated via `vcgencmd get_config` + GPIO |
| GPU utilisation | macmon active residency | N/A — no GPU offload, omitted |

The CSV column names are identical so results are directly comparable row-by-row if you port them to another machine later.

## Troubleshooting

- **`vcgencmd` not found**: ensure `vcgencmd` ships with the Raspberry Pi firmware package. On Raspberry Pi OS it is typically at `/usr/bin/vcgencmd` but may need installation: `apt-get install firmware-misc-nonfree` (older image) or rebuilt from BCM2708 firmware.
- **`llama-server` not built**: some users report needing `-DCMAKE_C_FLAGS="-mcpu=cortex-a76 -mtune=cortex-a76"`. Build again with that flag.
- **Port already in use**: kill any existing llama-server first, or change `PORT` in `run_benchmark.sh`.
- **Model download slow**: increase disk space, download via a mirror like `ggml-org` or HuggingFace mirror if your network is slow.
