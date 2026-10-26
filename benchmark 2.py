import csv
import json
import os
import threading
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from telemetry2 import (
    collect_telemetry, get_rpi_cpu_temp, get_rpi_gpu_temp,
)


_telemetry_active = False

def start_rpi_telemetry():
    """Raspberry Pi uses in-process telemetry polling — nothing to start."""
    global _telemetry_active
    _telemetry_active = True

def stop_rpi_telemetry():
    """Raspberry Pi uses in-process telemetry polling — stop it."""
    global _telemetry_active
    _telemetry_active = False


SERVER_URL = "http://127.0.0.1:9090/v1/chat/completions"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

# Model information can be supplied by run_benchmark.sh.
MODEL_NAME = os.environ.get("BENCHMARK_MODEL_NAME", "Vinci-Piccolo-1.0-GGUF")
MODEL_REPO = os.environ.get("BENCHMARK_MODEL_REPO", "simpledirect/Vinci-Piccolo-1.0-GGUF")
QUANTIZATION = os.environ.get("BENCHMARK_QUANTIZATION", "Q4_K_M")
MODEL_STARTUP_TIME = os.environ.get("MODEL_STARTUP_TIME")
MAX_TOKENS = 4096

# Keep the original prompt first in each profile for comparison with older runs.
EXTRA_PROMPTS = {
    "1": [
        'Design a comprehensive strategy for a rapidly growing city of five million people that expects its population to increase by 40 percent over the next twenty years. The city already faces traffic congestion, housing shortages, aging water systems, electricity demand growth, air pollution, and limited public funds. Develop an integrated plan covering transportation, housing, water, electricity, waste management, public health, climate resilience, and digital infrastructure. For each area, analyze competing priorities, dependencies, risks, costs, and possible unintended consequences. Explain how the city should sequence investments over twenty years and how success should be measured.',
        'A manufacturing company operates twelve factories across multiple countries and wants to reduce its total carbon emissions by 80 percent while keeping production costs competitive. Build a detailed decision framework for achieving this target. Consider renewable electricity, electrification of industrial processes, energy efficiency, alternative fuels, supply-chain changes, transportation, carbon capture, equipment replacement cycles, and carbon offsets. Discuss financial, technical, regulatory, operational, and supply-chain risks. Compare short-term and long-term strategies and propose a prioritized implementation roadmap with clear reasoning.',
        'Imagine that a region experiences a severe five-year drought while its population and agricultural demand continue to grow. Develop a detailed water-security strategy that balances urban consumption, agriculture, industry, ecosystem protection, and future population growth. Evaluate desalination, wastewater recycling, groundwater extraction, reservoirs, conservation, smart metering, agricultural efficiency, water pricing, and inter-regional transfers. Analyze economic, environmental, technical, political, and social trade-offs. Construct a phased response for immediate emergency measures, medium-term stabilization, and long-term resilience.',
        'A national government wants to build a resilient digital infrastructure strategy for the next fifteen years. It must support cloud computing, artificial intelligence, healthcare, banking, government services, education, and emergency communications while remaining resilient to cyberattacks, natural disasters, supply-chain disruptions, and power failures. Develop a detailed architecture and policy strategy. Compare centralized and distributed infrastructure, public cloud, sovereign cloud, edge computing, local data centers, backup power, network redundancy, cybersecurity controls, and disaster recovery. Identify trade-offs and propose measurable resilience targets.',
        'Analyze how a country should prepare its economy and workforce for widespread adoption of artificial intelligence and automation over the next twenty years. Consider productivity, job displacement, creation of new occupations, education, reskilling, inequality, taxation, social programs, small businesses, research investment, cybersecurity, energy demand, and international competitiveness. Present multiple plausible future scenarios rather than assuming a single outcome. For each scenario, identify major risks, leading indicators, and policy responses. Finish with a staged strategy that can adapt as conditions change.',
    ],
    "2": [
        'Design a production-quality TypeScript implementation of an LRU cache with O(1) average-time get and put operations. Do not use JavaScript Map insertion order as the eviction mechanism. Implement the required hash-map and doubly-linked-list logic explicitly. Support updating existing keys, capacity one, arbitrary string keys, and generic values. Explain every major design decision, identify invariants that must remain true, analyze time and space complexity, discuss common implementation bugs, and provide a comprehensive test suite covering eviction, updates, repeated access, and edge cases.',
        'You are designing a task scheduler in TypeScript. Each task has an ID, execution duration, and zero or more dependency IDs. Design an algorithm that validates the dependency graph, detects cycles, produces a valid execution order when possible, and calculates the earliest possible completion time assuming an unlimited number of workers and that a task can start only after all dependencies finish. Explain the graph representation, cycle-detection method, topological ordering, dynamic-programming step, complexity, and failure cases. Then provide complete TypeScript code and a set of nontrivial tests.',
        "Design a thread-safe job-processing architecture for a service that receives up to 50,000 jobs per minute. Jobs may be retried, workers may crash, duplicate messages may be delivered, and jobs must never be considered successfully completed more than once from the application's perspective. Explain how you would implement idempotency, retries with exponential backoff, dead-letter handling, leases or visibility timeouts, concurrency control, database transactions, observability, graceful shutdown, and recovery after failure. Then provide detailed TypeScript pseudocode or implementation-level code for the core worker loop and explain race conditions that must be prevented.",
        'Implement in TypeScript a function that receives millions of time intervals represented as start and end integer timestamps and returns the merged non-overlapping intervals, total covered duration, largest uncovered gap between the minimum and maximum timestamps, and maximum number of simultaneously active intervals. Clearly define how touching intervals and zero-length intervals are handled. Develop an efficient algorithm, analyze its time and space complexity, explain alternative approaches for very large datasets that do not fit into memory, and provide production-quality code with extensive edge-case tests.',
        'A Node.js API has gradually become slow under load. Requests perform authentication, query PostgreSQL, call two external services, transform large JSON objects, and publish an event. At 50 requests per second latency is 120 ms, but at 500 requests per second p95 latency exceeds 8 seconds and memory continually increases. Develop a systematic debugging and optimization plan. Reason about event-loop blocking, connection pools, unbounded concurrency, memory leaks, garbage collection, database indexes, N+1 queries, HTTP connection reuse, timeouts, retries, queues, caching, backpressure, and instrumentation. Include concrete TypeScript/Node.js examples showing how you would restructure the most likely bottlenecks.',
    ],
    "3": [
        'Create a comprehensive beginner-friendly explanation of how a web application works from the moment a user enters a URL until the requested page appears. Explain DNS, IP addresses, TCP, TLS, HTTP, browsers, CDNs, load balancers, reverse proxies, web servers, APIs, application servers, databases, caches, cookies, authentication, JavaScript execution, rendering, and browser storage. Follow the request chronologically and clearly explain which component is responsible for each stage. Include a realistic example involving a user signing into an online store.',
        'Write a structured technical guide comparing relational databases and document databases. Explain schemas, tables, documents, relationships, normalization, denormalization, indexes, transactions, ACID properties, consistency, horizontal and vertical scaling, replication, sharding, query patterns, data integrity, and operational complexity. Use PostgreSQL and MongoDB as concrete examples without presenting either as universally superior. Include several application scenarios and explain which characteristics should influence the database choice in each scenario.',
        'Explain the complete machine-learning lifecycle to a software developer who understands programming but has never built a machine-learning system. Cover problem definition, data collection, cleaning, labeling, exploratory analysis, feature engineering, training and validation splits, model selection, training, overfitting, underfitting, evaluation metrics, deployment, inference, monitoring, drift, retraining, versioning, privacy, and reproducibility. Use one consistent practical example throughout the explanation and clearly distinguish training from inference.',
        'Prepare a detailed incident-response guide for a software team operating a high-traffic web service. Explain detection, alert triage, severity classification, incident command, communication, diagnosis, mitigation, rollback, feature flags, logs, metrics, distributed traces, dashboards, database investigation, external dependency failures, customer communication, recovery validation, post-incident review, and preventive actions. Include a realistic example where an API deployment causes elevated error rates and database load. Keep the guide practical and operational.',
        'Write a comprehensive explanation of containerization and modern application deployment. Begin with the problems containers solve and explain images, containers, registries, Dockerfiles, layers, volumes, networking, environment variables, secrets, resource limits, health checks, and logging. Then explain how container orchestration systems schedule and manage applications, including replicas, rolling deployments, service discovery, autoscaling, failure recovery, and persistent storage. Finish by walking through a realistic deployment of a frontend, API, and database.',
    ],
    "4": [
        'A company must schedule six projects A through F. Their durations in days are A=4, B=7, C=3, D=6, E=5, and F=2. B and C can begin only after A finishes. D requires B. E requires both B and C. F requires both D and E. Assume unlimited workers, but no project can begin before all of its dependencies are complete. Determine the earliest start and finish time for every project, identify the critical path, calculate the minimum total completion time, and then determine what changes if B takes three additional days. Show the reasoning step by step.',
        "An online retailer sells a product for $480. The retailer first applies a 15 percent promotional discount. A customer then uses a coupon worth 10 percent of the already-discounted price. Shipping costs $24 unless the price after both discounts is at least $375, in which case shipping is free. Finally, 13 percent sales tax is applied to the merchandise price after discounts plus any shipping charge. The retailer's original cost for the product is $260 and it pays the shipping charge itself when shipping is free. Calculate the customer's final payment, the retailer's gross profit before other expenses, and the effective percentage discount relative to the original $480 sticker price. Show every calculation and explain the order of operations.",
        'A data center has a continuous IT load of 600 kW. Its initial power usage effectiveness, or PUE, is 1.50. An efficiency project reduces PUE to 1.25 but requires a $900,000 upfront investment. Electricity costs $0.12 per kWh during the first year and rises by 4 percent at the beginning of each subsequent year. Assume 8,760 operating hours per year and that the IT load remains constant. Calculate annual facility energy consumption before and after the upgrade, first-year energy and cost savings, and the cumulative nominal electricity-cost savings over five years. Determine whether the $900,000 investment has paid back within five years and estimate when simple payback occurs. Show all steps and assumptions.',
        'A delivery company has three trucks. Truck A can carry 8 tonnes and costs $140 per trip, Truck B carries 12 tonnes and costs $190 per trip, and Truck C carries 20 tonnes and costs $310 per trip. The company must move exactly 120 tonnes. At least two trips must use Truck A, no more than four trips may use Truck C, and the total number of trips may not exceed ten. Determine a minimum-cost feasible combination of integer trips for A, B, and C. Systematically evaluate the constraints, show the calculations, report total capacity and total cost, and explain why no cheaper feasible integer combination exists.',
        'A company is comparing two server systems for a five-year deployment. System A costs $18,000 initially, consumes an average of 420 watts, and requires $1,200 annual maintenance. System B costs $26,000 initially, consumes 250 watts, and requires $700 annual maintenance. Both run continuously 8,760 hours per year. Electricity costs $0.15 per kWh in year one and increases by 5 percent at the start of each following year. At the end of year five, System A has a resale value of $2,000 and System B has a resale value of $4,000. Calculate year-by-year electricity costs, maintenance costs, total five-year nominal ownership cost after resale value, the difference between the systems, and the approximate electricity price at which their five-year costs would become equal if all other assumptions stayed unchanged. Show the reasoning clearly.',
    ],
}


CSV_FIELDS = [
    "timestamp_utc", "model", "model_repo", "quantization", "model_startup_time_s",
    "iteration", "prompt_id", "profile", "thinking", "prompt",
    "status", "completed", "truncated", "error", "ttft_ms", "tpot_ms",
    "observed_inter_chunk_ms", "prompt_tokens", "output_tokens",
    "prompt_tps", "output_tps", "total_request_time_s", "telemetry_samples",
    "ram_start_mb", "ram_avg_mb", "ram_peak_mb", "swap_peak_mb",
    "cpu_avg_percent", "cpu_peak_avg_percent", "cpu_peak_core_percent",
    "gpu_avg_percent", "gpu_peak_percent",
    "cpu_temp_start_c", "cpu_temp_peak_c", "gpu_temp_start_c",
    "gpu_temp_peak_c", "power_avg_w", "power_peak_w",
    "estimated_energy_j",
]


def csv_result(row):
    """Prepare readable CSV values without changing benchmark calculations."""
    formatted = dict(row)
    formatted["prompt"] = textwrap.fill(
        row["prompt"], width=55, break_long_words=False, break_on_hyphens=False
    )
    for key, value in formatted.items():
        if isinstance(value, float):
            formatted[key] = f"{value:.3f}"
    return formatted


PROFILES = {
    "1": {
        "name": "Thinking - General",
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 1.5,
        "repeat_penalty": 1.0,
        "thinking": True,
        "prompt": 'A country currently generates 70 percent of its electricity from coal and natural gas and wants to reach 90 percent renewable electricity within 15 years. Develop a detailed transition strategy. Compare solar, wind, hydroelectric, geothermal, nuclear, battery storage, pumped hydro, and demand-response technologies. Analyze technical feasibility, grid stability, transmission requirements, seasonal energy storage, land use, supply-chain constraints, workforce requirements, capital costs, operating costs, energy security, and environmental impacts. Identify the major trade-offs and failure modes. Then propose a phased 15-year implementation plan with measurable milestones. Explain the reasoning behind your recommendations in detail.',
    },

    "2": {
        "name": "Thinking - Precise Coding",
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.0,
        "thinking": True,
        "prompt": 'Design and implement in TypeScript an O(n) algorithm that accepts an unsorted array of integers and returns: the length of the longest consecutive sequence, the sequence itself, and the starting and ending values. Duplicate values may appear and must not affect the result. If multiple sequences have the same maximum length, return the one with the smallest starting value. Do not sort the input. Explain the algorithm, prove why its expected time complexity is O(n), analyze space complexity, discuss edge cases, and provide clean production-quality TypeScript code followed by at least eight meaningful test cases.',
    },

    "3": {
        "name": "Instruct - General",
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 1.5,
        "repeat_penalty": 1.0,
        "thinking": False,
        "prompt": 'Write a detailed educational guide explaining how modern electrical power grids work for a reader with no engineering background. Cover electricity generation, transformers, high-voltage transmission, substations, distribution networks, frequency and voltage control, supply-demand balancing, grid operators, renewable-energy integration, battery storage, blackouts, and grid restoration. Organize the answer with clear headings, use practical examples and analogies, define technical terms when first introduced, and finish with a concise summary of the entire electricity journey from power plant to household.',
    },

    "4": {
        "name": "Instruct - Reasoning",
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 1.5,
        "repeat_penalty": 1.0,
        "thinking": False,
        "prompt": 'A company operates three factories A, B, and C. Factory A can produce 1,200 units per day at $18 per unit, B can produce 900 units per day at $21 per unit, and C can produce 1,500 units per day at $16 per unit. Daily demand is 3,000 units. However, at least 600 units must come from B because of a contract, C can operate at no more than 80 percent capacity because of maintenance, and using more than 1,000 units from A adds an overtime cost of $5 for every A unit above 1,000. Determine a lowest-cost feasible production allocation. Show the calculations, verify every constraint, calculate total cost, and explain why shifting production among factories would or would not reduce the cost.',
    },
}



def get_startup_time():
    """Return model startup time supplied by run_benchmark.sh, if available."""
    if not MODEL_STARTUP_TIME:
        return None
    try:
        return float(MODEL_STARTUP_TIME)
    except ValueError:
        return None


def summarize_telemetry(samples):

    def values(key):
        return [
            sample[key]
            for sample in samples
            if key in sample and sample[key] is not None
        ]

    ram = values("ram_used_mb")
    swap = values("swap_used_mb")

    cpu = values("cpu_avg_percent")
    cpu_core = values("cpu_peak_core_percent")

    # Raspberry Pi has no separate GPU utilization metric; skip if absent.
    gpu = values("gpu_percent")

    cpu_temp = values("cpu_temp_c")
    gpu_temp = values("gpu_temp_c")

    # On Raspberry Pi, power may come as 'estimated_w' (voltage*current/1000)
    # or 'cpu_clocks'. Normalise into watts.
    power_vals = values("estimated_w") + values("cpu_clocks_w")
    if not power_vals:
        power_vals = values("power_current_mw")

    return {
        "samples": len(samples),

        "ram_start":
            ram[0] if ram else None,

        "ram_average":
            sum(ram) / len(ram) if ram else None,

        "ram_peak":
            max(ram) if ram else None,

        "swap_peak":
            max(swap) if swap else None,

        "cpu_average":
            sum(cpu) / len(cpu) if cpu else None,

        "cpu_peak_average":
            max(cpu) if cpu else None,

        "cpu_peak_core":
            max(cpu_core) if cpu_core else None,

        "gpu_average":
            sum(gpu) / len(gpu) if gpu else None,

        "gpu_peak":
            max(gpu) if gpu else None,

        "cpu_temp_start":
            cpu_temp[0] if cpu_temp else None,

        "cpu_temp_peak":
            max(cpu_temp) if cpu_temp else None,

        "gpu_temp_start":
            gpu_temp[0] if gpu_temp else None,

        "gpu_temp_peak":
            max(gpu_temp) if gpu_temp else None,

        "power_average_w":
            (sum(power_vals) / len(power_vals)) / 1000 if power_vals else None,

        "power_peak_w":
            (max(power_vals) / 1000) if power_vals else None,
    }


def save_responses_json(json_path, responses, started_at):
    """Save model answers after every prompt so completed outputs are not lost."""
    payload = {
        "benchmark_started_utc": started_at,
        "model": MODEL_NAME,
        "model_repo": MODEL_REPO,
        "quantization": QUANTIZATION,
        "responses": responses,
    }

    # Write to a temporary file first, then replace the destination.
    # This reduces the chance of leaving a partial JSON file if interrupted.
    temp_path = json_path.with_suffix(json_path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as json_file:
        json.dump(payload, json_file, indent=2, ensure_ascii=False)
        json_file.flush()

    temp_path.replace(json_path)


def initialize_raw_session(raw_path, started_at):
    """Create the raw request/response session dump for this benchmark run."""
    with raw_path.open("w", encoding="utf-8") as raw_file:
        raw_file.write("=" * 80 + "\n")
        raw_file.write("SIMPLEDIRECT BENCHMARK - RAW REQUEST/RESPONSE SESSION DUMP\n")
        raw_file.write("=" * 80 + "\n")
        raw_file.write(f"Benchmark started (UTC): {started_at}\n")
        raw_file.write(f"Model: {MODEL_NAME}\n")
        raw_file.write(f"Model repo: {MODEL_REPO}\n")
        raw_file.write(f"Quantization: {QUANTIZATION}\n")
        raw_file.write(f"Endpoint: {SERVER_URL}\n")
        raw_file.write("\n")


def append_raw_session(raw_path, record):
    """Append one complete raw request/response interaction to the session dump."""
    with raw_path.open("a", encoding="utf-8") as raw_file:
        raw_file.write("\n" + "=" * 80 + "\n")
        raw_file.write(
            f"RUN {record['iteration']} | PROFILE: {record['profile']} | "
            f"PROMPT {record['prompt_id']}\n"
        )
        raw_file.write("=" * 80 + "\n")
        raw_file.write(f"Timestamp (UTC): {record['timestamp_utc']}\n")
        raw_file.write(f"Thinking enabled: {record['thinking_enabled']}\n")
        raw_file.write(f"Status: {record['status']}\n")
        raw_file.write(f"Completed: {record['completed']}\n")
        raw_file.write(f"Truncated: {record['truncated']}\n")
        raw_file.write(f"Error: {record['error']}\n")

        raw_file.write("\n[USER PROMPT]\n")
        raw_file.write(record["prompt"] + "\n")

        raw_file.write("\n[REQUEST JSON]\n")
        raw_file.write(
            json.dumps(
                record["request_payload"],
                indent=2,
                ensure_ascii=False
            )
        )
        raw_file.write("\n")

        raw_file.write("\n[RAW STREAM RESPONSE]\n")
        raw_lines = record.get("raw_response_lines") or []
        if raw_lines:
            for line in raw_lines:
                raw_file.write(line + "\n")
        else:
            raw_file.write("<no raw response lines received>\n")

        raw_file.write("\n[REASONING / THINKING]\n")
        raw_file.write((record.get("reasoning") or "<none>") + "\n")

        raw_file.write("\n[FINAL ANSWER]\n")
        raw_file.write((record.get("answer") or "<none>") + "\n")
        raw_file.flush()


def run_benchmark():

    print()
    print("SimpleDirect Mac Mini Benchmark")
    print("=" * 50)
    print()
    print("All 4 profiles will run automatically.")
    print("Prompts per profile: 6")
    print("Prompts per full cycle: 24")
    print(f"Max output tokens: {MAX_TOKENS}")

    while True:
        try:
            duration_minutes = float(
                input(
                    "Duration in minutes "
                    "[60; 0 = one full pass]: "
                ).strip()
                or "60"
            )

            if (
                duration_minutes >= 0
                and duration_minutes != float("inf")
            ):
                break

        except ValueError:
            pass

        print("Enter a nonnegative number of minutes.")

    print()

    if duration_minutes:
        print(
            f"Duration: {duration_minutes:g} minutes "
            "(checked between prompts)"
        )
    else:
        print(
            "Mode: one full pass through all 4 profiles "
            "(24 prompts)"
        )

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    filename = (
        f"rpi5_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        "_all_profiles.csv"
    )

    results_path = RESULTS_DIR / filename
    responses_path = results_path.with_name(
        results_path.stem + "_responses.json"
    )
    raw_session_path = results_path.with_name(
        results_path.stem + "_raw_session.txt"
    )
    benchmark_started_utc = datetime.now(timezone.utc).isoformat()
    saved_responses = []

    # Create the JSON file immediately so the destination is visible
    # even before the first prompt finishes.
    save_responses_json(
        responses_path,
        saved_responses,
        benchmark_started_utc
    )
    initialize_raw_session(
        raw_session_path,
        benchmark_started_utc
    )

    deadline = (
        time.monotonic() + duration_minutes * 60
        if duration_minutes
        else None
    )

    iteration = 0
    cycle = 0
    stop_requested = False
    total_prompt_time_s = 0.0

    print()
    print(f"Saving each result to: {results_path}")
    print(f"Saving model responses to: {responses_path}")
    print(f"Saving raw session dump to: {raw_session_path}")

    try:
        # Raspberry Pi uses in-process polling instead of external sensors
        start_rpi_telemetry()

        with results_path.open(
            "w",
            newline="",
            encoding="utf-8"
        ) as csv_file:

            writer = csv.DictWriter(
                csv_file,
                fieldnames=CSV_FIELDS
            )

            writer.writeheader()
            csv_file.flush()

            while True:

                cycle += 1

                print()
                print("=" * 70)
                print(f"FULL CYCLE {cycle}")
                print("=" * 70)

                for profile_id, profile in PROFILES.items():

                    prompts = [
                        profile["prompt"],
                        *EXTRA_PROMPTS[profile_id]
                    ]

                    print()
                    print("#" * 70)
                    print(
                        f"PROFILE {profile_id}/4 - "
                        f"{profile['name']}"
                    )
                    print(
                        f"Thinking: "
                        f"{'ON' if profile['thinking'] else 'OFF'}"
                    )
                    print(f"Prompts: {len(prompts)}")
                    print()
                    print("Sampling:")
                    print(
                        f"  temperature       = "
                        f"{profile['temperature']}"
                    )
                    print(
                        f"  top_p             = "
                        f"{profile['top_p']}"
                    )
                    print(
                        f"  top_k             = "
                        f"{profile['top_k']}"
                    )
                    print(
                        f"  min_p             = "
                        f"{profile['min_p']}"
                    )
                    print(
                        f"  presence_penalty  = "
                        f"{profile['presence_penalty']}"
                    )
                    print(
                        f"  repeat_penalty    = "
                        f"{profile['repeat_penalty']}"
                    )
                    print("#" * 70)

                    for prompt_id, prompt in enumerate(
                        prompts,
                        start=1
                    ):

                        # For timed runs, finish the current prompt
                        # but do not start a new prompt after the
                        # requested duration has been reached.
                        if (
                            deadline is not None
                            and time.monotonic() >= deadline
                        ):
                            stop_requested = True
                            break

                        iteration += 1

                        print()
                        print(
                            f"Run {iteration} | "
                            f"Profile {profile_id}/4 | "
                            f"Prompt {prompt_id}/{len(prompts)}"
                        )
                        print(
                            textwrap.fill(
                                prompt,
                                width=90
                            ),
                            flush=True
                        )

                        row, response_record = run_one_prompt(
                            profile,
                            prompt,
                            prompt_id,
                            iteration
                        )

                        # Save the raw request/response interaction immediately.
                        append_raw_session(
                            raw_session_path,
                            response_record
                        )

                        # Keep the existing response JSON compact and compatible
                        # with earlier runs; raw transport data belongs in the
                        # dedicated raw-session dump.
                        json_record = dict(response_record)
                        json_record.pop("request_payload", None)
                        json_record.pop("raw_response_lines", None)
                        saved_responses.append(json_record)
                        save_responses_json(
                            responses_path,
                            saved_responses,
                            benchmark_started_utc
                        )

                        request_time = row.get("total_request_time_s")
                        if isinstance(request_time, (int, float)):
                            total_prompt_time_s += request_time

                        writer.writerow(
                            csv_result(row)
                        )
                        csv_file.flush()

                        print(
                            f"Saved run {iteration}: "
                            f"{row['status']}",
                            flush=True
                        )

                    if stop_requested:
                        break

                # 0 minutes means exactly one complete pass:
                # 4 profiles x 6 prompts = 24 runs.
                if deadline is None:
                    break

                if stop_requested:
                    break

    except KeyboardInterrupt:
        print(
            "\nStopped by user; completed results "
            "have been saved."
        )

    except Exception as exc:
        print(f"Benchmark stopped: {exc}")

    finally:
        # Append one summary row directly below the final prompt row.
        # The total is the sum of total_request_time_s for all prompt rows.
        if results_path.exists():
            total_row = {
                field: ""
                for field in CSV_FIELDS
            }
            total_row["profile"] = "TOTAL PROMPT TIME"
            total_row["total_request_time_s"] = total_prompt_time_s

            with results_path.open(
                "a",
                newline="",
                encoding="utf-8"
            ) as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=CSV_FIELDS
                )
                writer.writerow(
                    csv_result(total_row)
                )
                csv_file.flush()

    # Raspberry Pi uses in-process polling instead of external sensors
    stop_rpi_telemetry()

    print()
    print("=" * 70)
    print("BENCHMARK FINISHED")
    print("=" * 70)
    print(f"Total attempted runs: {iteration}")
    print(
        f"Total prompt response time: "
        f"{total_prompt_time_s:.3f} sec"
    )
    print(f"Results: {results_path}")
    print(f"Responses: {responses_path}")
    print(f"Raw session: {raw_session_path}")



def run_one_prompt(profile, prompt, prompt_id, iteration):
    stop_event = threading.Event()
    telemetry_samples = []

    def telemetry_worker():

        samples = collect_telemetry(stop_event)
        telemetry_samples.extend(samples)

    telemetry_thread = threading.Thread(
        target=telemetry_worker,
        daemon=True
    )

    telemetry_thread.start()

    # Allow one baseline telemetry sample.
    time.sleep(1.2)

    payload = {
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],

        "stream": True,

        "max_tokens": MAX_TOKENS,

        # Ask llama.cpp to provide usage at the end.
        "stream_options": {
            "include_usage": True
        },

        "temperature":
            profile["temperature"],

        "top_p":
            profile["top_p"],

        "top_k":
            profile["top_k"],

        "min_p":
            profile["min_p"],

        "presence_penalty":
            profile["presence_penalty"],

        "repeat_penalty":
            profile["repeat_penalty"],

        # Tell the model whether thinking is enabled.
        "chat_template_kwargs": {
            "enable_thinking":
                profile["thinking"]
        },

        # Separate reasoning from final answer.
        "reasoning_format": "deepseek"
    }

    print()
    print("Running benchmark...")
    print()

    request_start = time.perf_counter()

    first_generated_time = None
    previous_generated_time = None

    inter_token_times = []

    reasoning_text = ""
    response_text = ""
    raw_response_lines = []

    usage = {}
    server_timings = {}

    completed = False
    truncated = False
    error_message = None

    response = None
    try:

        response = requests.post(
            SERVER_URL,
            json=payload,
            stream=True,
            timeout=1800
        )

        if response.status_code != 200:

            error_message = (
                f"HTTP {response.status_code}: "
                f"{response.text}"
            )
            raw_response_lines.append(
                f"HTTP {response.status_code}: {response.text}"
            )

            # Record the failed request in the CSV as well.
            raise RuntimeError(error_message)

        for raw_line in response.iter_lines():

            if not raw_line:
                continue

            line = raw_line.decode("utf-8", errors="replace")
            raw_response_lines.append(line)

            if not line.startswith("data: "):
                continue

            data = line[6:]

            if data == "[DONE]":
                completed = True
                break

            try:
                chunk = json.loads(data)

            except json.JSONDecodeError:
                continue

            if chunk.get("usage"):
                usage = chunk["usage"]

            if chunk.get("timings"):
                server_timings = chunk["timings"]

            choices = chunk.get("choices", [])

            if not choices:
                continue

            choice = choices[0]

            finish_reason = choice.get(
                "finish_reason"
            )

            if finish_reason:
                if finish_reason == "length":
                    truncated = True

            delta = choice.get("delta", {})

            reasoning = delta.get(
                "reasoning_content"
            )

            content = delta.get("content")

            generated_piece = (
                reasoning or content
            )

            if generated_piece:

                now = time.perf_counter()

                if first_generated_time is None:
                    first_generated_time = now

                if previous_generated_time is not None:

                    inter_token_times.append(
                        (
                            now
                            - previous_generated_time
                        ) * 1000
                    )

                previous_generated_time = now

            if reasoning:
                reasoning_text += reasoning

            if content:
                response_text += content

    except Exception as exc:
        error_message = str(exc)

    finally:

        request_end = time.perf_counter()
        if response is not None:
            response.close()

        stop_event.set()

        telemetry_thread.join(
            timeout=5
        )

    telemetry = summarize_telemetry(
        telemetry_samples
    )

    total_time = (
        request_end - request_start
    )

    ttft_ms = None

    if first_generated_time is not None:

        ttft_ms = (
            first_generated_time
            - request_start
        ) * 1000

    avg_inter_token_ms = None

    if inter_token_times:

        avg_inter_token_ms = (
            sum(inter_token_times)
            / len(inter_token_times)
        )

    # Prefer authoritative llama.cpp timing data.
    prompt_tokens = (
        server_timings.get("prompt_n")
        or usage.get("prompt_tokens")
    )

    output_tokens = (
        server_timings.get("predicted_n")
        or usage.get("completion_tokens")
    )

    tpot_ms = server_timings.get(
        "predicted_per_token_ms"
    )

    output_tps = server_timings.get(
        "predicted_per_second"
    )

    prompt_tps = server_timings.get(
        "prompt_per_second"
    )

    # Fallback if timings are not returned.
    if (
        output_tokens
        and first_generated_time
        and request_end > first_generated_time
    ):

        generation_seconds = (
            request_end
            - first_generated_time
        )

        if output_tps is None:

            output_tps = (
                output_tokens
                / generation_seconds
            )

        if (
            tpot_ms is None
            and output_tps
        ):
            tpot_ms = (
                1000 / output_tps
            )

    average_power = telemetry[
        "power_average_w"
    ]

    energy_joules = None

    if average_power is not None:

        energy_joules = (
            average_power
            * total_time
        )

    print()
    print("=" * 58)
    print(
        "SIMPLEDIRECT BENCHMARK RESULTS"
    )
    print("=" * 58)

    print()
    print("CONFIGURATION")

    print(
        f"Profile:                    "
        f"{profile['name']}"
    )

    print(
        "Model:                      "
        f"{MODEL_NAME}"
    )

    print(
        "Quantization:               "
        f"{QUANTIZATION}"
    )

    print(
        "Hardware:                   "
        "Raspberry Pi 5 (4GB)"
    )

    print(
        "CPU:                        "
        "ARM Cortex-A76 4x + Cortex-A53 4x @ 1.6 GHz"
    )

    print(
        "Memory:                     "
        "4 GB LPDDR4 (unified memory)"
    )

    print(
        "Runtime:                    "
        "llama.cpp (CPU only, no GPU offload)"
    )

    print(
        "GPU acceleration:           N/A - VideoCore VII GPU not supported by llama.cpp"
    )

    print(
        "GPU offload:                "
        "33/33 layers"
    )

    print(
        f"Thinking:                   "
        f"{'ON' if profile['thinking'] else 'OFF'}"
    )

    print(
        f"Max output tokens:          "
        f"{MAX_TOKENS}"
    )

    print()
    print("LATENCY / PERFORMANCE")

    print_metric(
        "TTFT",
        ttft_ms,
        "ms"
    )

    print_metric(
        "Prompt tokens",
        prompt_tokens
    )

    print_metric(
        "Output tokens",
        output_tokens
    )

    print_metric(
        "Prompt throughput",
        prompt_tps,
        "tokens/sec"
    )

    print_metric(
        "TPOT",
        tpot_ms,
        "ms/token"
    )

    print_metric(
        "Output throughput",
        output_tps,
        "tokens/sec"
    )

    print_metric(
        "Observed inter-chunk latency",
        avg_inter_token_ms,
        "ms"
    )

    print_metric(
        "Total request time",
        total_time,
        "sec"
    )

    print_metric(
        "Model startup/load time",
        get_startup_time(),
        "sec"
    )

    print()
    print("MEMORY")

    print_metric(
        "RAM at benchmark start",
        telemetry["ram_start"],
        "MB"
    )

    print_metric(
        "Average RAM",
        telemetry["ram_average"],
        "MB"
    )

    print_metric(
        "Peak RAM",
        telemetry["ram_peak"],
        "MB"
    )

    print_metric(
        "Peak swap",
        telemetry["swap_peak"],
        "MB"
    )

    print(
        "GPU memory:                 "
        "Shared/unified with system RAM"
    )

    print()
    print("UTILIZATION")

    print_metric(
        "Average CPU",
        telemetry["cpu_average"],
        "%"
    )

    print_metric(
        "Peak CPU avg",
        telemetry["cpu_peak_average"],
        "%"
    )

    print_metric(
        "Peak CPU core",
        telemetry["cpu_peak_core"],
        "%"
    )

    print_metric(
        "Average GPU",
        telemetry["gpu_average"],
        "%"
    )

    print_metric(
        "Peak GPU",
        telemetry["gpu_peak"],
        "%"
    )

    print(
        "GPU utilization:            N/A - CPU only, no GPU offload"
    )

    print()
    print("THERMALS")

    print_metric(
        "CPU start temperature",
        telemetry["cpu_temp_start"],
        "C"
    )

    print_metric(
        "Peak CPU temperature",
        telemetry["cpu_temp_peak"],
        "C"
    )

    print_metric(
        "GPU start temperature",
        telemetry["gpu_temp_start"],
        "C"
    )

    print_metric(
        "Peak GPU temperature",
        telemetry["gpu_temp_peak"],
        "C"
    )

    print()
    print("POWER")

    print_metric(
        "Average board power",
        telemetry["power_average_w"],
        "W"
    )

    print_metric(
        "Peak board power",
        telemetry["power_peak_w"],
        "W"
    )

    print_metric(
        "Estimated energy",
        energy_joules,
        "J"
    )

    print()
    print("MODEL OUTPUT")
    print("-" * 58)

    if reasoning_text:

        print()
        print("[REASONING / THINKING]")
        print(reasoning_text.strip())

    if response_text:

        print()
        print("[FINAL ANSWER]")
        print(response_text.strip())

    if (
        not reasoning_text
        and not response_text
    ):
        print(
            "No model output received."
        )

    print()
    print("STATUS")

    print(
        f"Completed:                   "
        f"{'YES' if completed else 'NO'}"
    )

    print(
        f"Truncated:                   "
        f"{'YES' if truncated else 'NO'}"
    )

    print(
        f"Runtime error:               "
        f"{error_message if error_message else 'None'}"
    )

    print()
    print("=" * 58)

    status = "error" if error_message else ("truncated" if truncated else ("success" if completed else "incomplete"))
    timestamp_utc = datetime.now(timezone.utc).isoformat()

    row = {
        "timestamp_utc": timestamp_utc,
        "model": MODEL_NAME,
        "model_repo": MODEL_REPO,
        "quantization": QUANTIZATION,
        "model_startup_time_s": get_startup_time(),
        "iteration": iteration,
        "prompt_id": prompt_id,
        "profile": profile["name"],
        "thinking": profile["thinking"],
        "prompt": prompt,
        "status": status,
        "completed": completed,
        "truncated": truncated,
        "error": error_message,
        "ttft_ms": ttft_ms,
        "tpot_ms": tpot_ms,
        "observed_inter_chunk_ms": avg_inter_token_ms,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "prompt_tps": prompt_tps,
        "output_tps": output_tps,
        "total_request_time_s": total_time,
        "telemetry_samples": telemetry["samples"],
        "ram_start_mb": telemetry["ram_start"],
        "ram_avg_mb": telemetry["ram_average"],
        "ram_peak_mb": telemetry["ram_peak"],
        "swap_peak_mb": telemetry["swap_peak"],
        "cpu_avg_percent": telemetry["cpu_average"],
        "cpu_peak_avg_percent": telemetry["cpu_peak_average"],
        "cpu_peak_core_percent": telemetry["cpu_peak_core"],
        "gpu_avg_percent": telemetry["gpu_average"],
        "gpu_peak_percent": telemetry["gpu_peak"],
        "cpu_temp_start_c": telemetry["cpu_temp_start"],
        "cpu_temp_peak_c": telemetry["cpu_temp_peak"],
        "gpu_temp_start_c": telemetry["gpu_temp_start"],
        "gpu_temp_peak_c": telemetry["gpu_temp_peak"],
        "power_avg_w": telemetry["power_average_w"],
        "power_peak_w": telemetry["power_peak_w"],
        "estimated_energy_j": energy_joules,
    }

    response_record = {
        "timestamp_utc": timestamp_utc,
        "iteration": iteration,
        "profile": profile["name"],
        "thinking_enabled": profile["thinking"],
        "prompt_id": prompt_id,
        "prompt": prompt,
        "request_payload": payload,
        "raw_response_lines": raw_response_lines,
        "reasoning": reasoning_text.strip() or None,
        "answer": response_text.strip() or None,
        "status": status,
        "completed": completed,
        "truncated": truncated,
        "error": error_message,
    }

    return row, response_record


def print_metric(
    name,
    value,
    unit=""
):

    if value is None:
        formatted = "N/A"

    elif isinstance(value, float):
        formatted = f"{value:.2f}"

    else:
        formatted = str(value)

    if unit and value is not None:
        formatted += f" {unit}"

    print(
        f"{name + ':':28} "
        f"{formatted}"
    )


def print_failure(
    profile,
    message
):

    print()
    print("=" * 58)
    print("BENCHMARK FAILED")
    print("=" * 58)

    print(
        f"Profile: {profile['name']}"
    )

    print(
        f"Error: {message}"
    )

    print("=" * 58)


if __name__ == "__main__":
    run_benchmark()
