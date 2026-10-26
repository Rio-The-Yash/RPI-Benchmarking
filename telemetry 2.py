import json
import math
import re
import shutil
import subprocess
import threading
import time

import psutil


def get_memory_metrics():
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()

    return {
        "ram_used_mb": memory.used / (1024 * 1024),
        "ram_total_mb": memory.total / (1024 * 1024),
        "swap_used_mb": swap.used / (1024 * 1024),
        "swap_total_mb": swap.total / (1024 * 1024),
    }


def get_cpu_metrics():
    per_core = psutil.cpu_percent(
        interval=None,
        percpu=True
    )

    if not per_core:
        return {
            "cpu_avg_percent": None,
            "cpu_peak_core_percent": None,
        }

    return {
        "cpu_percent_per_core": per_core,
        "cpu_avg_percent":
            sum(per_core) / len(per_core),
        "cpu_peak_core_percent":
            max(per_core),
    }


def parse_powermetrics_sample(text):
    data = {}

    # GPU utilization / active residency
    gpu = re.search(
        r"GPU\s+(?:HW\s+)?active residency:\s*([\d.]+)%",
        text,
        re.IGNORECASE
    )

    if gpu:
        data["gpu_percent"] = float(
            gpu.group(1)
        )

    # CPU power
    cpu_power = re.search(
        r"CPU Power:\s*([\d.]+)\s*mW",
        text,
        re.IGNORECASE
    )

    # GPU power
    gpu_power = re.search(
        r"GPU Power:\s*([\d.]+)\s*mW",
        text,
        re.IGNORECASE
    )

    # Combined Apple Silicon power
    combined_power = re.search(
        r"Combined Power"
        r"(?: \(CPU \+ GPU \+ ANE\))?"
        r":\s*([\d.]+)\s*mW",
        text,
        re.IGNORECASE
    )

    if combined_power:
        data["power_current_mw"] = float(
            combined_power.group(1)
        )

    elif cpu_power or gpu_power:

        total = 0.0

        if cpu_power:
            total += float(
                cpu_power.group(1)
            )

        if gpu_power:
            total += float(
                gpu_power.group(1)
            )

        data["power_current_mw"] = total

    return data


_power_process = None
_power_thread = None
_latest_power_metrics = {}
_power_lock = threading.Lock()
_latest_power_at = 0.0
_temp_process = None
_temp_thread = None
_latest_temp_metrics = {}
_temp_lock = threading.Lock()
_latest_temp_at = 0.0


def _temperature_reader(process):
    """Read one JSON temperature sample per line from macmon."""
    global _latest_temp_at
    for line in process.stdout:
        try:
            temp = json.loads(line).get("temp") or {}
        except (ValueError, TypeError, AttributeError):
            continue
        metrics = {}
        for field, key in (("cpu_temp_avg", "cpu_temp_c"),
                           ("gpu_temp_avg", "gpu_temp_c")):
            value = temp.get(field)
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                metrics[key] = value
        if metrics:
            with _temp_lock:
                _latest_temp_metrics.clear()
                _latest_temp_metrics.update(metrics)
                _latest_temp_at = time.monotonic()


def start_temperature_monitor():
    """Start one macmon sensor process for the full benchmark."""
    global _temp_process, _temp_thread, _latest_temp_at
    if _temp_process is not None:
        return
    if shutil.which("macmon") is None:
        raise RuntimeError(
            "Temperature sensor tool not found. Install with: brew install macmon"
        )
    _temp_process = subprocess.Popen(
        ["macmon", "pipe", "-i", "1000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    with _temp_lock:
        _latest_temp_metrics.clear()
        _latest_temp_at = 0.0
    _temp_thread = threading.Thread(
        target=_temperature_reader, args=(_temp_process,), daemon=True
    )
    _temp_thread.start()
    time.sleep(2.5)
    if _temp_process.poll() is not None:
        message = _temp_process.stderr.read().strip()
        stop_temperature_monitor()
        raise RuntimeError("macmon could not start: " + (message or "no error details returned"))
    with _temp_lock:
        ready = bool(_latest_temp_metrics)
    if not ready:
        stop_temperature_monitor()
        raise RuntimeError("macmon started but returned no CPU/GPU temperatures. Try: macmon pipe -s 2")


def stop_temperature_monitor():
    global _temp_process, _temp_thread
    process = _temp_process
    if process is None:
        return
    try:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if process.poll() is None:
            process.kill()
            process.wait()
    if _temp_thread:
        _temp_thread.join(timeout=2)
    if process.stdout:
        process.stdout.close()
    if process.stderr:
        process.stderr.close()
    _temp_process = None
    _temp_thread = None


def _powermetrics_reader(process):
    """Read the single monitor shared by every prompt in this benchmark."""
    global _latest_power_at
    block = []
    for line in process.stdout:
        if "*** Sampled system activity" in line and block:
            parsed = parse_powermetrics_sample("".join(block))
            if parsed:
                with _power_lock:
                    _latest_power_metrics.clear()
                    _latest_power_metrics.update(parsed)
                    _latest_power_at = time.monotonic()
            block = []
        block.append(line)
    if block:
        parsed = parse_powermetrics_sample("".join(block))
        if parsed:
            with _power_lock:
                _latest_power_metrics.clear()
                _latest_power_metrics.update(parsed)
                _latest_power_at = time.monotonic()


def start_power_monitor():
    """Ask for the Mac password once, then leave powermetrics running."""
    global _power_process, _power_thread, _latest_power_at
    if _power_process is not None:
        return
    print("Authorize Mac GPU/power monitoring (sudo may ask for your password).", flush=True)
    subprocess.run(["sudo", "-v"], check=True)
    _power_process = subprocess.Popen(
        ["sudo", "-n", "powermetrics", "--samplers",
         "cpu_power,gpu_power", "-i", "1000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    with _power_lock:
        _latest_power_metrics.clear()
        _latest_power_at = 0.0
    _power_thread = threading.Thread(
        target=_powermetrics_reader, args=(_power_process,), daemon=True
    )
    _power_thread.start()
    time.sleep(1.5)
    if _power_process.poll() is not None:
        message = _power_process.stderr.read().strip()
        stop_power_monitor()
        raise RuntimeError(
            "powermetrics could not start: " + (message or "no error details returned")
        )


def stop_power_monitor():
    global _power_process, _power_thread
    process = _power_process
    if process is None:
        return
    try:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if process.poll() is None:
            process.kill()
            process.wait()
    if _power_thread:
        _power_thread.join(timeout=2)
    if process.stdout:
        process.stdout.close()
    if process.stderr:
        process.stderr.close()
    _power_process = None
    _power_thread = None


def collect_telemetry(stop_event):
    samples = []

    # Initialize psutil CPU counters
    psutil.cpu_percent(
        interval=None,
        percpu=True
    )

    while not stop_event.is_set():

        sample = {}

        # RAM and swap
        sample.update(
            get_memory_metrics()
        )

        # CPU utilization
        sample.update(
            get_cpu_metrics()
        )

        # GPU utilization + power
        with _power_lock:
            if time.monotonic() - _latest_power_at < 4.0:
                sample.update(_latest_power_metrics)

        # The macmon values are the average of available CPU/GPU sensors.
        sample["cpu_temp_c"] = None
        sample["gpu_temp_c"] = None
        with _temp_lock:
            if time.monotonic() - _latest_temp_at < 4.0:
                sample.update(_latest_temp_metrics)

        sample["timestamp"] = time.time()

        samples.append(sample)

        stop_event.wait(1.0)

    return samples
