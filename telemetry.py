"""
Raspberry Pi 5 telemetry for the SimpleDirect benchmark.

Drop-in replacement for the macOS telemetry module: same public functions,
so benchmark.py needs no import changes.

    collect_telemetry(stop_event)
    start_temperature_monitor() / stop_temperature_monitor()
    start_power_monitor()       / stop_power_monitor()

Sources on Raspberry Pi OS:
    psutil                  -> RAM, swap, CPU utilisation
    vcgencmd measure_temp   -> SoC temperature (CPU and GPU share one sensor)
    vcgencmd measure_clock  -> ARM CPU clock
    vcgencmd pmic_read_adc  -> 5V input voltage/current (Pi 5 PMIC)
    vcgencmd get_throttled  -> undervoltage / thermal throttle flags

No discrete GPU and no powermetrics/macmon equivalent, so gpu_* keys are
None and the GPU columns in the CSV stay empty.
"""

import math
import re
import shutil
import subprocess
import threading
import time

import psutil


VCGENCMD = shutil.which("vcgencmd") or "/usr/bin/vcgencmd"

THROTTLE_BITS = {
    "undervoltage_now": 0,
    "freq_capped_now": 1,
    "throttled_now": 2,
    "soft_temp_limit_now": 3,
    "undervoltage_occurred": 16,
    "freq_capped_occurred": 17,
    "throttled_occurred": 18,
    "soft_temp_limit_occurred": 19,
}


def _vcgencmd(*args, timeout=2):
    try:
        result = subprocess.run(
            [VCGENCMD, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


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
    per_core = psutil.cpu_percent(interval=None, percpu=True)

    if not per_core:
        return {"cpu_avg_percent": None, "cpu_peak_core_percent": None}

    return {
        "cpu_percent_per_core": per_core,
        "cpu_avg_percent": sum(per_core) / len(per_core),
        "cpu_peak_core_percent": max(per_core),
    }


def get_temperature_metrics():
    output = _vcgencmd("measure_temp")
    if not output:
        return {}

    match = re.search(r"temp=([\d.]+)", output)
    if not match:
        return {}

    try:
        value = float(match.group(1))
    except ValueError:
        return {}

    if not math.isfinite(value):
        return {}

    return {"cpu_temp_c": value, "gpu_temp_c": None}


def get_clock_metrics():
    output = _vcgencmd("measure_clock", "arm")
    if not output:
        return {}

    match = re.search(r"frequency\(\d+\)=(\d+)", output)
    if not match:
        return {}

    return {"cpu_freq_mhz": int(match.group(1)) / 1_000_000}


def get_throttle_metrics():
    output = _vcgencmd("get_throttled")
    if not output:
        return {}

    match = re.search(r"throttled=(0x[0-9a-fA-F]+)", output)
    if not match:
        return {}

    flags = int(match.group(1), 16)

    return {
        "throttled_flags": flags,
        "throttle_now": any(
            flags & (1 << THROTTLE_BITS[name])
            for name in (
                "undervoltage_now", "freq_capped_now",
                "throttled_now", "soft_temp_limit_now",
            )
        ),
        "throttle_occurred": any(
            flags & (1 << THROTTLE_BITS[name])
            for name in (
                "undervoltage_occurred", "freq_capped_occurred",
                "throttled_occurred", "soft_temp_limit_occurred",
            )
        ),
    }


def get_power_metrics():
    """Sum of PMIC rail power. Excludes USB and 5V-direct loads."""
    output = _vcgencmd("pmic_read_adc")
    if not output:
        return {}

    amps = {
        name: float(value)
        for name, value in re.findall(
            r"([A-Z0-9_]+)_A current\(\d+\)=([\d.]+)A", output
        )
    }
    volts = {
        name: float(value)
        for name, value in re.findall(
            r"([A-Z0-9_]+)_V volt\(\d+\)=([\d.]+)V", output
        )
    }

    total = sum(volts[rail] * amps[rail] for rail in amps if rail in volts)

    if not total:
        return {}

    return {"power_current_mw": total * 1000.0}


_stop_event = threading.Event()
_monitor_threads = []
_state_lock = threading.Lock()
_latest_sensors = {}
_latest_at = 0.0


def _sensor_reader():
    global _latest_at

    while not _stop_event.wait(1.0):
        sample = {}
        sample.update(get_temperature_metrics())
        sample.update(get_clock_metrics())
        sample.update(get_throttle_metrics())
        sample.update(get_power_metrics())

        if not sample:
            continue

        with _state_lock:
            _latest_sensors.clear()
            _latest_sensors.update(sample)
            _latest_at = time.monotonic()


def _start_monitors():
    global _monitor_threads

    if _monitor_threads:
        return

    if shutil.which("vcgencmd") is None:
        print(
            "WARNING: vcgencmd not found; sensor values will be blank.",
            flush=True,
        )

    _stop_event.clear()

    with _state_lock:
        _latest_sensors.clear()
        _latest_at = 0.0

    thread = threading.Thread(target=_sensor_reader, daemon=True)
    thread.start()
    _monitor_threads.append(thread)

    time.sleep(1.5)


def _stop_monitors():
    global _monitor_threads

    _stop_event.set()
    for thread in _monitor_threads:
        thread.join(timeout=2)
    _monitor_threads = []


def start_temperature_monitor():
    _start_monitors()


def stop_temperature_monitor():
    _stop_monitors()


def start_power_monitor():
    """No sudo required on the Pi."""
    _start_monitors()


def stop_power_monitor():
    _stop_monitors()


def collect_telemetry(stop_event):
    samples = []

    psutil.cpu_percent(interval=None, percpu=True)

    while not stop_event.is_set():
        sample = {}

        sample.update(get_memory_metrics())
        sample.update(get_cpu_metrics())

        with _state_lock:
            if time.monotonic() - _latest_at < 4.0:
                sample.update(_latest_sensors)

        sample.setdefault("cpu_temp_c", None)
        sample.setdefault("gpu_temp_c", None)

        sample["timestamp"] = time.time()
        samples.append(sample)

        stop_event.wait(1.0)

    return samples
