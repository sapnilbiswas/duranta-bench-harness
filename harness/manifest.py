#!/usr/bin/env python3
"""Platform manifest collector for Duranta benchmark harness.

Captures hardware, OS, compiler, kernel, and virtualization environment
details without assuming root privileges. Any inaccessible parameter is
recorded cleanly as 'not captured'.
"""

import json
import os
import platform
import shutil
import subprocess
from typing import Any, Dict, List, Optional


def run_cmd(cmd: List[str], timeout: float = 5.0) -> Optional[str]:
    """Execute a command safely and return stripped stdout or None."""
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError, PermissionError):
        pass
    return None


def read_file_or_fallback(path: str, fallback: str = "not captured") -> str:
    """Read file content safely or return fallback."""
    try:
        if os.path.exists(path) and os.access(path, os.R_OK):
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read().strip()
                return content if content else fallback
    except (OSError, PermissionError):
        pass
    return fallback


def parse_os_release(path: str = "/etc/os-release") -> Dict[str, str]:
    """Parse /etc/os-release into a dictionary."""
    data: Dict[str, str] = {}
    content = read_file_or_fallback(path, fallback="")
    if not content:
        return {"raw": "not captured"}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        data[key.strip()] = val.strip().strip('"').strip("'")
    return data


def parse_meminfo(path: str = "/proc/meminfo") -> Dict[str, str]:
    """Extract key metrics from /proc/meminfo."""
    content = read_file_or_fallback(path, fallback="")
    if not content:
        return {"raw": "not captured"}
    info: Dict[str, str] = {}
    target_keys = {
        "MemTotal",
        "MemFree",
        "MemAvailable",
        "Buffers",
        "Cached",
        "SwapTotal",
        "SwapFree",
    }
    for line in content.splitlines():
        parts = line.split(":", 1)
        if len(parts) == 2:
            k = parts[0].strip()
            if k in target_keys:
                info[k] = parts[1].strip()
    return info if info else {"raw": content}


def detect_virtualization() -> str:
    """Detect whether the system is virtualized using systemd-detect-virt or heuristics."""
    if shutil.which("systemd-detect-virt"):
        virt = run_cmd(["systemd-detect-virt"])
        if virt:
            return virt

    # Fallback heuristics
    if os.path.exists("/.dockerenv"):
        return "docker"
    if os.path.exists("/proc/1/cgroup"):
        cgroup = read_file_or_fallback("/proc/1/cgroup", "")
        if "docker" in cgroup or "kubepods" in cgroup or "containerd" in cgroup:
            return "container"

    return "unknown / unverified"


def get_duranta_git_commit(repo_path: str) -> str:
    """Retrieve git commit SHA of the Duranta clone."""
    if os.path.isdir(repo_path) and shutil.which("git"):
        sha = run_cmd(["git", "-C", repo_path, "rev-parse", "HEAD"])
        if sha:
            return sha
    return "unknown"


def collect_platform_manifest(
    duranta_path: str = "/workspace/openairinterface5g",
    build_flags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Collect complete hardware and platform manifest."""
    uname = platform.uname()

    # lscpu
    lscpu_data: Any = None
    if shutil.which("lscpu"):
        lscpu_json_str = run_cmd(["lscpu", "--json"])
        if lscpu_json_str:
            try:
                lscpu_data = json.loads(lscpu_json_str)
            except json.JSONDecodeError:
                lscpu_data = lscpu_json_str
        else:
            lscpu_data = run_cmd(["lscpu"]) or "not captured"
    else:
        lscpu_data = "not captured"

    # CPU governor
    governor = read_file_or_fallback(
        "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
    )

    # SMT state
    smt = read_file_or_fallback(
        "/sys/devices/system/cpu/smt/control",
        read_file_or_fallback("/sys/devices/system/cpu/smt/active"),
    )

    # Turbo / Boost
    turbo = read_file_or_fallback(
        "/sys/devices/system/cpu/intel_pstate/no_turbo",
        read_file_or_fallback("/sys/devices/system/cpu/cpufreq/boost"),
    )

    # Isolated CPUs
    isolated = read_file_or_fallback(
        "/sys/devices/system/cpu/isolated", fallback="none"
    )

    # Compiler
    compiler_ver = "not captured"
    for comp in ["gcc", "cc", "clang"]:
        if shutil.which(comp):
            ver_out = run_cmd([comp, "--version"])
            if ver_out:
                compiler_ver = ver_out.splitlines()[0]
                break

    manifest = {
        "uname": {
            "sysname": uname.system,
            "nodename": uname.node,
            "release": uname.release,
            "version": uname.version,
            "machine": uname.machine,
        },
        "cpu_arch": uname.machine,
        "lscpu": lscpu_data,
        "os_release": parse_os_release(),
        "kernel_cmdline": read_file_or_fallback("/proc/cmdline"),
        "cpu_governor": governor,
        "smt_state": smt,
        "turbo_boost": turbo,
        "isolated_cpus": isolated,
        "memory_info": parse_meminfo(),
        "compiler_version": compiler_ver,
        "virtualization": detect_virtualization(),
    }

    return manifest


if __name__ == "__main__":
    manifest = collect_platform_manifest()
    print(json.dumps(manifest, indent=2))
