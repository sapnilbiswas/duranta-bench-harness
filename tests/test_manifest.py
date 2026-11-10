"""Tests for platform manifest collection and parsing."""

import json
from pathlib import Path
import pytest

from harness.manifest import (
    parse_os_release,
    parse_meminfo,
    detect_virtualization,
    collect_platform_manifest,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_parse_os_release():
    fixture_path = str(FIXTURES_DIR / "sample_os_release")
    data = parse_os_release(fixture_path)
    assert data["ID"] == "ubuntu"
    assert data["VERSION_ID"] == "24.04"
    assert "Ubuntu 24.04" in data["PRETTY_NAME"]


def test_parse_meminfo():
    fixture_path = str(FIXTURES_DIR / "sample_meminfo")
    data = parse_meminfo(fixture_path)
    assert "MemTotal" in data
    assert "8124776 kB" in data["MemTotal"]
    assert "MemAvailable" in data
    assert "SwapTotal" in data


def test_detect_virtualization_nonempty():
    virt = detect_virtualization()
    assert isinstance(virt, str)
    assert len(virt) > 0


def test_collect_platform_manifest_structure():
    manifest = collect_platform_manifest()
    required_keys = [
        "uname",
        "cpu_arch",
        "lscpu",
        "os_release",
        "kernel_cmdline",
        "cpu_governor",
        "smt_state",
        "turbo_boost",
        "isolated_cpus",
        "memory_info",
        "compiler_version",
        "virtualization",
    ]
    for key in required_keys:
        assert key in manifest, f"Missing required manifest key: {key}"
    assert "sysname" in manifest["uname"]
    assert "machine" in manifest["uname"]

