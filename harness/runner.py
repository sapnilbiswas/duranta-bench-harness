#!/usr/bin/env python3
"""Benchmark runner and noise-floor characterisation for Duranta-OAI physims.

Executes physical simulators (nr_dlsim, nr_ulsim) with CPU pinning via taskset,
captures raw stdout/stderr, parses time_meas metrics, runs idle vs loaded noise
floor sweeps, and outputs schema-validated JSON results.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
from pathlib import Path
import sys
from pathlib import Path

# Ensure harness package is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Any, Dict, List, Optional, Tuple

import jsonschema

from harness.manifest import collect_platform_manifest, get_duranta_git_commit


# Regex parser for time_meas / printDistribution / printStatIndent lines
TIME_MEAS_RE = re.compile(
    r"(?:\|__\s+|\s+)?([A-Za-z0-9_ /()\-]+?)\s+([\d.]+)\s+us\s+\(\s*(\d+)\s+trials\)"
)
STAT_LINE_RE = re.compile(
    r"Statistics\s+std=([\d.]+),\s+min=([\d.]+),\s+q1=([\d.]+),\s+median=([\d.]+),\s+q3=([\d.]+),\s+max=([\d.]+)\s+µs"
)
BLER_RE = re.compile(
    r"(?:SNR\s+([-\d.]+)\s+dB:.*?BLER\s+([-\d.e+]+)|bler\s*=\s*([-\d.e+]+)|BLER\s*=\s*([-\d.e+]+))",
    re.IGNORECASE,
)


def parse_time_meas_output(output: str) -> Dict[str, Any]:
    """Parse time_meas and simulator statistics from raw stdout."""
    metrics: Dict[str, Any] = {}

    for line in output.splitlines():
        # Match primary metric lines
        match = TIME_MEAS_RE.search(line)
        if match:
            raw_name = match.group(1).strip()
            val_us = float(match.group(2))
            # Standardize key names
            norm_key = (
                raw_name.lower()
                .replace(" ", "_")
                .replace("/", "_")
                .replace("-", "_")
                .replace("(", "")
                .replace(")", "")
                + "_us"
            )
            metrics[norm_key] = val_us

        # Check for BLER / SNR
        bler_match = BLER_RE.search(line)
        if bler_match:
            if bler_match.group(1) is not None:
                try:
                    metrics["snr_db"] = float(bler_match.group(1))
                except ValueError:
                    pass
            for grp in [bler_match.group(2), bler_match.group(3), bler_match.group(4)]:
                if grp is not None:
                    try:
                        metrics["bler"] = float(grp)
                    except ValueError:
                        pass

    # Direct mappings for key deliverable metrics
    key_aliases = {
        "phy_proc_tx_us": ["phy_proc_tx_us"],
        "dlsch_encoding_time_us": ["dlsch_encoding_time_us"],
        "total_phy_proc_rx_us": ["total_phy_proc_rx_us"],
        "ulsch_total_decoding_time_us": [
            "ulsch_total_decoding_time_us",
            "ulsch_decoding_time_us",
        ],
    }

    for canonical, aliases in key_aliases.items():
        if canonical not in metrics:
            for alias in aliases:
                if alias in metrics:
                    metrics[canonical] = metrics[alias]
                    break

    return metrics


def compute_summary_stats(values: List[float]) -> Dict[str, Any]:
    """Compute count, median, IQR, min, max for a sequence of values."""
    if not values:
        return {"count": 0, "median": 0.0, "iqr": 0.0, "min": 0.0, "max": 0.0, "values": []}

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    med = statistics.median(sorted_vals)

    if n >= 4:
        # Quantiles calculation (inclusive)
        q1 = statistics.quantiles(sorted_vals, n=4)[0]
        q3 = statistics.quantiles(sorted_vals, n=4)[2]
        iqr = q3 - q1
    else:
        q1 = sorted_vals[0]
        q3 = sorted_vals[-1]
        iqr = q3 - q1

    return {
        "count": n,
        "median": round(med, 2),
        "iqr": round(iqr, 2),
        "min": round(sorted_vals[0], 2),
        "max": round(sorted_vals[-1], 2),
        "values": [round(v, 2) for v in sorted_vals],
    }


def run_single_benchmark(
    cmd: List[str],
    cpu_list: Optional[str] = None,
    timeout: float = 120.0,
) -> Tuple[int, str, str]:
    """Execute a single benchmark run optionally pinned via taskset."""
    full_cmd = list(cmd)
    if cpu_list and shutil.which("taskset"):
        full_cmd = ["taskset", "-c", cpu_list] + full_cmd

    try:
        proc = subprocess.run(
            full_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        return -1, stdout, stderr + "\n[ERROR: Run timed out]"
    except Exception as e:
        return -2, "", f"[ERROR: Execution failed: {e}]"


class BackgroundBurner:
    """Spawns background CPU burn threads on other cores for noise floor testing."""

    def __init__(self, target_cpus: Optional[str] = None):
        self.target_cpus = target_cpus
        self.procs: List[subprocess.Popen] = []

    def start(self, num_procs: int = 2):
        """Start python CPU burner loop processes."""
        burn_code = "while True: pass"
        for _ in range(num_procs):
            cmd = [sys.executable, "-c", burn_code]
            if self.target_cpus and shutil.which("taskset"):
                cmd = ["taskset", "-c", self.target_cpus] + cmd
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.procs.append(p)

    def stop(self):
        """Terminate all background burner processes."""
        for p in self.procs:
            try:
                p.terminate()
                p.wait(timeout=1.0)
            except Exception:
                p.kill()
        self.procs.clear()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


def execute_test_suite(
    executable_path: str,
    args: List[str],
    repetitions: int = 3,
    cpu_list: Optional[str] = None,
    noise_floor: bool = False,
    background_cpus: Optional[str] = None,
    test_case_id: str = "case_1",
    target_metric: str = "phy_proc_tx_us",
    duranta_path: str = "/workspace/openairinterface5g",
    build_flags: Optional[List[str]] = None,
    schema_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute benchmark repetitions under idle and optionally loaded conditions."""
    benchmark_name = Path(executable_path).name
    cmd_base = [executable_path] + args
    cmd_str = " ".join(cmd_base)
    runs: List[Dict[str, Any]] = []

    idle_metric_values: List[float] = []
    loaded_metric_values: List[float] = []

    # 1. Idle condition runs
    for i in range(repetitions):
        code, stdout, stderr = run_single_benchmark(cmd_base, cpu_list=cpu_list)
        metrics = parse_time_meas_output(stdout)
        status = "success" if code == 0 else "failed"

        run_entry = {
            "benchmark_name": benchmark_name,
            "test_case_id": test_case_id,
            "condition": "idle" if noise_floor else "unspecified",
            "command": cmd_str,
            "repetition_index": i,
            "taskset_cpu_list": cpu_list,
            "exit_code": code,
            "status": status,
            "metrics": metrics,
            "raw_stdout": stdout,
            "raw_stderr": stderr,
        }
        runs.append(run_entry)

        if target_metric in metrics and metrics[target_metric] is not None:
            idle_metric_values.append(metrics[target_metric])

    # 2. Loaded condition runs (if noise_floor requested)
    if noise_floor:
        # Determine background burner cores: opposite cores if specified
        burner_cpus = background_cpus
        if not burner_cpus and cpu_list:
            # Simple heuristic: if pinned to 0, burn on 1-3
            burner_cpus = "1-3"

        with BackgroundBurner(target_cpus=burner_cpus):
            for i in range(repetitions):
                code, stdout, stderr = run_single_benchmark(cmd_base, cpu_list=cpu_list)
                metrics = parse_time_meas_output(stdout)
                status = "success" if code == 0 else "failed"

                run_entry = {
                    "benchmark_name": benchmark_name,
                    "test_case_id": test_case_id,
                    "condition": "loaded",
                    "command": cmd_str,
                    "repetition_index": i,
                    "taskset_cpu_list": cpu_list,
                    "exit_code": code,
                    "status": status,
                    "metrics": metrics,
                    "raw_stdout": stdout,
                    "raw_stderr": stderr,
                }
                runs.append(run_entry)

                if target_metric in metrics and metrics[target_metric] is not None:
                    loaded_metric_values.append(metrics[target_metric])

    # Platform manifest
    manifest = collect_platform_manifest(duranta_path=duranta_path)
    commit_sha = get_duranta_git_commit(duranta_path)

    result_doc: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "virtualized": True,
        "virtualization_note": "virtualized, not representative of bare metal",
        "duranta_commit": commit_sha,
        "build_flags": build_flags or ["-DENABLE_PHYSIM_TESTS=ON", "-DSANITIZE_UNDEFINED=OFF", "-DSANITIZE_ADDRESS=OFF"],
        "platform_manifest": manifest,
        "benchmark_runs": runs,
    }

    if noise_floor:
        idle_stats = compute_summary_stats(idle_metric_values)
        loaded_stats = compute_summary_stats(loaded_metric_values)
        diff_med = round(loaded_stats["median"] - idle_stats["median"], 2)
        pct_diff = (
            round((diff_med / idle_stats["median"]) * 100.0, 2)
            if idle_stats["median"] > 0
            else 0.0
        )

        result_doc["noise_floor_analysis"] = {
            "test_case_id": test_case_id,
            "metric_name": target_metric,
            "idle_stats": idle_stats,
            "loaded_stats": loaded_stats,
            "diff_median": diff_med,
            "diff_percentage": pct_diff,
        }

    # Schema validation
    if schema_path and os.path.exists(schema_path):
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.validate(instance=result_doc, schema=schema)

    return result_doc


def main():
    parser = argparse.ArgumentParser(description="Duranta Benchmark Runner")
    parser.add_argument("--bin", required=True, help="Path to simulator binary (e.g. /build/nr_dlsim)")
    parser.add_argument("--args", default="", help="Arguments to pass to binary (quoted string)")
    parser.add_argument("-n", "--repetitions", type=int, default=3, help="Repetitions per condition")
    parser.add_argument("--cpu", default=None, help="Pin simulator to CPU core(s), e.g. '0' or '0,1'")
    parser.add_argument("--noise-floor", action="store_true", help="Run noise floor evaluation (idle vs loaded)")
    parser.add_argument("--bg-cpus", default=None, help="Background load core(s), e.g. '2,3'")
    parser.add_argument("--test-id", default="case_default", help="Unique identifier for test case")
    parser.add_argument("--metric", default="phy_proc_tx_us", help="Target metric for noise floor analysis")
    parser.add_argument("--duranta-path", default="/workspace/openairinterface5g", help="Path to Duranta clone")
    parser.add_argument("--schema", default="schemas/result.schema.json", help="Path to JSON Schema")
    parser.add_argument("-o", "--output", default=None, help="Path to save result JSON")
    parser.add_argument("sim_args", nargs="*", help="Direct arguments for simulator")

    parsed, unknown = parser.parse_known_args()

    args_to_use = []
    if parsed.args:
        args_to_use.extend(parsed.args.strip().split())
    if parsed.sim_args:
        args_to_use.extend(parsed.sim_args)
    if unknown:
        args_to_use.extend(unknown)

    results = execute_test_suite(
        executable_path=parsed.bin,
        args=args_to_use,
        repetitions=parsed.repetitions,
        cpu_list=parsed.cpu,
        noise_floor=parsed.noise_floor,
        background_cpus=parsed.bg_cpus,
        test_case_id=parsed.test_id,
        target_metric=parsed.metric,
        duranta_path=parsed.duranta_path,
        schema_path=parsed.schema,
    )

    out_json = json.dumps(results, indent=2)
    if parsed.output:
        os.makedirs(os.path.dirname(os.path.abspath(parsed.output)), exist_ok=True)
        with open(parsed.output, "w", encoding="utf-8") as f:
            f.write(out_json)
        print(f"Results written to: {parsed.output}")
    else:
        print(out_json)


if __name__ == "__main__":
    main()

