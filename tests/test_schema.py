"""Tests for result schema validation and output parsing."""

import json
from pathlib import Path
import jsonschema
import pytest

from harness.runner import parse_time_meas_output, compute_summary_stats

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "result.schema.json"


@pytest.fixture
def result_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_parse_time_meas_output():
    stdout_file = FIXTURES_DIR / "sample_dlsim_stdout.txt"
    raw_text = stdout_file.read_text()
    metrics = parse_time_meas_output(raw_text)

    assert "phy_proc_tx_us" in metrics
    assert metrics["phy_proc_tx_us"] == 44.86
    assert "dlsch_encoding_time_us" in metrics
    assert metrics["dlsch_encoding_time_us"] == 30.52
    assert "ldpc_encoding_time_us" in metrics
    assert metrics["ldpc_encoding_time_us"] == 24.15
    assert "bler" in metrics
    assert metrics["bler"] == 0.0


def test_compute_summary_stats():
    vals = [40.0, 42.0, 44.0, 46.0, 50.0]
    stats = compute_summary_stats(vals)
    assert stats["count"] == 5
    assert stats["median"] == 44.0
    assert stats["min"] == 40.0
    assert stats["max"] == 50.0
    assert stats["iqr"] > 0


def test_schema_valid_minimal(result_schema):
    valid_doc = {
        "schema_version": "1.0.0",
        "timestamp": "2026-11-11T02:00:00Z",
        "virtualized": True,
        "virtualization_note": "virtualized, not representative of bare metal",
        "duranta_commit": "dfb296ab867050a7bde81b393fa31b757ada2c83",
        "build_flags": ["-DENABLE_PHYSIM_TESTS=ON"],
        "platform_manifest": {
            "uname": {
                "sysname": "Linux",
                "nodename": "test-host",
                "release": "6.6.0",
                "version": "#1",
                "machine": "aarch64",
            },
            "cpu_arch": "aarch64",
            "lscpu": {},
            "os_release": {"ID": "ubuntu"},
            "kernel_cmdline": "not captured",
            "cpu_governor": "not captured",
            "smt_state": "not captured",
            "turbo_boost": "not captured",
            "isolated_cpus": "none",
            "memory_info": {"MemTotal": "8124776 kB"},
            "compiler_version": "gcc 13.3.0",
            "virtualization": "docker",
        },
        "benchmark_runs": [
            {
                "benchmark_name": "nr_dlsim",
                "command": "./nr_dlsim -n1000 -s20 -S20.2 -e15 -b106 -R106 -P",
                "repetition_index": 0,
                "exit_code": 0,
                "status": "success",
                "metrics": {
                    "phy_proc_tx_us": 44.86,
                    "dlsch_encoding_time_us": 30.52,
                },
            }
        ],
    }

    # Should not raise
    jsonschema.validate(instance=valid_doc, schema=result_schema)


def test_schema_invalid_missing_commit(result_schema):
    invalid_doc = {
        "schema_version": "1.0.0",
        "timestamp": "2026-11-11T02:00:00Z",
        "virtualized": True,
        "virtualization_note": "virtualized, not representative of bare metal",
        # missing duranta_commit
        "build_flags": [],
        "platform_manifest": {},
        "benchmark_runs": [],
    }

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=invalid_doc, schema=result_schema)
