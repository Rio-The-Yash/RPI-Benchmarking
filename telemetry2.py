import glob
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time

import psutil

# ============================================================
# Raspberry Pi specific telemetry helpers
# ============================================================

def get_rpi_cpu_temp():
    """Get Raspberry Pi CPU temperature using vcgencmd or sysfs."""
    try:
        result = subprocess.run(['vcgencmd', 'measure_temp'],
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            temp_str = result.stdout.strip()
            # Output format: "temp=56.3'C"
            if temp_str.startswith('temp='):
                return float(temp_str[5:-1])
    except Exception:
        pass

    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        pass

    return None


def get_rpi_gpu_temp():
    """Get Raspberry Pi SoC (combined CPU+GPU) temperature via vcgencmd."""
    try:
        result = subprocess.run(['vcgencmd', 'measure_temp'],
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            temp_str = result.stdout.strip()
            if temp_str.startswith('temp='):
                return float(temp_str[5:-1])
    except Exception:
        pass

    return None


def get_rpi_power_estimate():
    """Estimate board power consumption via vcgencmd config flags."""
    power = {}

    try:
        result = subprocess.run(['vcgencmd', 'get_config'],
                              capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("max_frames_per_sec"):
                value = stripped.split("=", 1)[1]
                try:
                    val = int(value)
                    if val > 0:
                        power["cpu_clocks"] = val
                except ValueError:
                    pass
    except Exception:
        pass

    # Try GPIO power stats (available on some Pi models with gpio stats)
    try:
        import glob
        power_dir = '/sys/class/gpio/'
        files = [f for f in glob.glob(power_dir + '*')]
        for f in files:
            try:
                with open(f'{f}/name', 'r') as fh:
                    if 'power' in fh.read().lower():
                        path = os.path.join(f, 'state') if hasattr(os, 'path') else f'{f}/state'
                        try:
                            with open(path, 'r') as pfh:
                                vals = [l.strip() for l in pfh.readlines()]
                                if vals and len(vals) >= 3:
                                    try:
                                        voltage = float(vals[2].strip().replace(',', '.'))
                                        current = float(vals[3].strip().replace(',', '.'))
                                        power["estimated_w"] = voltage * current / 1000.0
                                    except ValueError:
                                        pass
                        except Exception:
                            pass
            except Exception:
                pass
    except Exception:
        pass

    return power


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


# ============================================================
# State variables for background monitor threads
# ============================================================

_power_metrics = {}
_power_lock = threading.Lock()
_latest_power_at = 0.0

_temp_metrics = {}
_temp_lock = threading.Lock()
_latest_temp_at = 0.0


def _refresh_telemetry():
    """Fetch current RPI telemetry values into the global state."""
    global _power_metrics, _power_lock, _latest_power_at
    global _temp_metrics, _temp_lock, _latest_temp_at

    # Power — poll every ~2 seconds
    now = time.monotonic()
    if now - _latest_power_at >= 2.0:
        power = get_rpi_power_estimate()
        with _power_lock:
            _power_metrics.clear()
            _power_metrics.update(power)
            _latest_power_at = now

    # Temperature — poll every ~2 seconds
    if now - _latest_temp_at >= 2.0:
        with _temp_lock:
            _temp_metrics.clear()
            _temp_metrics['cpu_temp_c'] = get_rpi_cpu_temp()
            _temp_metrics['gpu_temp_c'] = get_rpi_gpu_temp()
            _latest_temp_at = now


def collect_telemetry(stop_event):
    """Periodically snapshot system metrics while benchmark runs."""
    samples = []

    # Prime the psutil CPU percent counters
    psutil.cpu_percent(interval=None, percpu=True)

    while not stop_event.is_set():
        _refresh_telemetry()

        sample = {}

        # RAM and swap
        sample.update(get_memory_metrics())

        # CPU utilization
        sample.update(get_cpu_metrics())

        # Power metrics from Raspberry Pi
        with _power_lock:
            sample.update(_power_metrics)

        # Temperature metrics from Raspberry Pi
        with _temp_lock:
            sample.update(_temp_metrics)

        sample["timestamp"] = time.time()

        samples.append(sample)

        stop_event.wait(1.0)

    return samples
