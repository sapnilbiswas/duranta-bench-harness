# duranta-bench-harness

A lightweight, reproducible benchmarking harness and gap analysis for **Duranta-OpenAirInterface5g**, built as a proof-of-concept for the LFX Mentorship proposal: *"Benchmarking the L1, L2 and L3 Functions of Duranta-OAI Across Operating Systems and Hardware"*.

---

## 1. Scope and Purpose

The goal of this proof-of-concept is to demonstrate a rigorous, reproducible, and verifiable benchmarking methodology before attempting complex instrumentation across the full Duranta-OAI stack.

### What This Harness Does
- **Platform Manifest Collection**: Automatically captures hardware topology (`lscpu --json`), operating system (`/etc/os-release`), kernel arguments (`/proc/cmdline`), memory metrics (`/proc/meminfo`), compiler version, git commit hash, and virtualization status (`systemd-detect-virt`). Inaccessible metrics (e.g. unprivileged CPU governors) are recorded honestly as `"not captured"`.
- **Standardized Schema**: Validates all benchmark results against a versioned JSON Schema ([`schemas/result.schema.json`](file:///Users/sapnilbiswas/LFX_5G/duranta-bench-harness/schemas/result.schema.json)).
- **Physical Simulator Execution**: Runs 5G NR physical simulators (`nr_dlsim`, `nr_ulsim`) with deterministic CPU core pinning (`taskset`), preserves raw stdout/stderr logs, and parses embedded `time_meas` statistics (`PHY proc tx`, `DLSCH encoding time`, `Total PHY proc rx`, `ULSCH decoding time`).
- **Noise Floor Characterisation**: Executes test cases under both idle and background-loaded conditions on non-pinned cores, calculating median, IQR, min/max, and performance delta.
- **Probe Overhead Microbenchmark**: Measures the cost in nanoseconds and CPU ticks of the OAI `time_meas` API (`start_meas` / `stop_meas`) versus bare `clock_gettime(CLOCK_MONOTONIC)` and empty loop baselines ([`microbench/meas_overhead.c`](file:///Users/sapnilbiswas/LFX_5G/duranta-bench-harness/microbench/meas_overhead.c)).
- **Comprehensive Gap Analysis**: Maps the 8 deliverables from the mentorship proposal against actual source paths, line references, and missing components in Duranta ([`docs/GAP_ANALYSIS.md`](file:///Users/sapnilbiswas/LFX_5G/duranta-bench-harness/docs/GAP_ANALYSIS.md)).

### What This Harness Does NOT Claim
- **Not Bare-Metal Determinism**: When executed inside Docker on macOS or virtual machines, timers and CPU scheduling are subject to hypervisor jitter. All outputs are explicitly tagged `"virtualized, not representative of bare metal"`.
- **Zero Modifications to Duranta**: This harness lives in its own repository and builds against the Duranta clone by path without modifying, branching, or copying Duranta source files (complying with CSSL v1.0).
- **L2/L3 Instrumentation Status**: This harness does not claim that L2 (RLC, PDCP, SDAP) or L3 (RRC, F1AP, NGAP) are already instrumented. As documented in [`docs/GAP_ANALYSIS.md`](file:///Users/sapnilbiswas/LFX_5G/duranta-bench-harness/docs/GAP_ANALYSIS.md), Layer 2 and Layer 3 currently have zero `time_meas` or `Tracy` probes.

---

## 2. Directory Layout

```
duranta-bench-harness/
├── README.md                      # Overview, quickstart, and claims
├── docker/
│   └── Dockerfile                 # Ubuntu 24.04 build & runtime environment
├── docs/
│   ├── GAP_ANALYSIS.md            # Detailed deliverable gap analysis
│   └── NOTES.md                   # Verifications, assumptions, and limitations
├── harness/
│   ├── __init__.py
│   ├── manifest.py                # Platform & hardware metadata collector
│   └── runner.py                  # CLI runner, metric parser, and noise floor engine
├── microbench/
│   ├── Makefile                   # Standalone microbenchmark build
│   └── meas_overhead.c            # Probe overhead measurement (C)
├── results/                       # Validated JSON result outputs
├── schemas/
│   └── result.schema.json         # Draft 2020-12 JSON Schema
└── tests/
    ├── fixtures/                  # Sample output fixtures for offline test suite
    ├── test_manifest.py           # Pytest suite for manifest collection
    └── test_schema.py             # Pytest suite for schema validation & parsing
```

---

## 3. Quickstart

### Prerequisites
- Docker (Docker Desktop or native Linux Docker)
- Duranta-OpenAirInterface5g cloned adjacent to this repository:
  ```bash
  git clone --depth 1 https://github.com/duranta-project/openairinterface5g
  ```

### Step 1: Build Container Image
Build the Ubuntu 24.04 container image containing build tools, `asn1c`, `simde`, and test dependencies:
```bash
docker build -t duranta-bench-image -f docker/Dockerfile docker/
```

### Step 2: Run Unit Tests
Verify the harness manifest collector and schema validator:
```bash
docker run --rm \
  -v $(pwd):/harness \
  duranta-bench-image \
  bash -c "cd /harness && PYTHONPATH=. pytest -v"
```

### Step 3: Run the Probe-Overhead Microbenchmark
Compile and run the standalone C microbenchmark (1,000,000 iterations):
```bash
docker run --rm \
  -v $(pwd)/../openairinterface5g:/workspace/openairinterface5g:ro \
  -v $(pwd):/harness \
  duranta-bench-image \
  bash -c "cd /harness/microbench && make && ./meas_overhead 1000000"
```

### Step 4: Run Physical Simulator Benchmarks & Noise Floor
Build the physical simulators in an isolated build directory (leaving the Duranta source tree read-only):
```bash
mkdir -p build
docker run --rm \
  -v $(pwd)/../openairinterface5g:/workspace/openairinterface5g:ro \
  -v $(pwd)/build:/build \
  duranta-bench-image \
  bash -c "cmake -S /workspace/openairinterface5g -B /build -GNinja -DENABLE_PHYSIM_TESTS=ON && ninja -C /build nr_dlsim nr_ulsim"
```

Execute a DL simulator test case with 5 repetitions, CPU pinning (`taskset -c 0`), and noise floor comparison:
```bash
docker run --rm \
  -v $(pwd)/../openairinterface5g:/workspace/openairinterface5g:ro \
  -v $(pwd)/build:/build \
  -v $(pwd):/harness \
  duranta-bench-image \
  python3 /harness/harness/runner.py \
    --bin /build/nr_dlsim \
    --args "-n100 -s20 -S20.2 -e15 -b106 -R106 -P" \
    --cpu 0 \
    --noise-floor \
    --bg-cpus 1-3 \
    --test-id dl_40mhz_mcs15 \
    --metric phy_proc_tx_us \
    --schema /harness/schemas/result.schema.json \
    --output /harness/results/dl_40mhz_mcs15.json
```
