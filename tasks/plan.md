# Implementation Plan: Duranta-OAI Benchmarking Proof-of-Concept

## Overview
A lightweight, reproducible benchmarking harness and gap analysis for Duranta-OpenAirInterface5g (LFX Mentorship proposal). Built in a clean repository `duranta-bench-harness` using Python 3.11+, JSON Schema, pytest, and a standalone C probe-overhead microbenchmark, running inside an Ubuntu 24.04 (arm64) Linux container.

## Architecture Decisions
- **Isolation & Licensing**: The Duranta source tree (`openairinterface5g`, CSSL v1.0 license) is mounted read-only or built by path; zero OAI source files are copied into `duranta-bench-harness`.
- **Execution Environment**: Ubuntu 24.04 container matching host architecture (`aarch64`), managed via a dedicated `Dockerfile` and runner script. Every result explicitly labels "virtualized, not representative of bare metal".
- **Manifest Collection**: Captures machine and OS state (`lscpu --json`, `/etc/os-release`, `uname`, `/proc/cmdline`, CPU governor, SMT state, turbo/boost, isolated CPUs, memory info, compiler, Duranta git commit, build flags, virtualization detection via `systemd-detect-virt`). Unprivileged fallbacks cleanly record "not captured".
- **Validation**: Every result conforms to `schemas/result.schema.json` validated via `jsonschema`.
- **Honesty & Verification**: All paths, line numbers, command flags, and metrics are verified directly against the cloned repo and real command outputs. Any unverified items are documented in `docs/NOTES.md`.

## Task List

### Phase 0: Environment Setup & Physim Build
- [ ] Task 0.1: Create container build definition (`docker/Dockerfile`) for Ubuntu 24.04 with OAI build prerequisites and test Python environment.
- [ ] Task 0.2: Build container image and compile `nr_dlsim` and `nr_ulsim` against the Duranta repo without modifying Duranta source.
- [ ] Task 0.3: Execute a smoke test of `nr_dlsim -h` and `nr_ulsim -h` inside the container and document exact build commands and findings.

### Phase 1: Deep Codebase Reading & Gap Analysis
- [ ] Task 1.1: Trace existing timing instrumentation: `common/utils/time_meas.{h,c}` and `common/instrumentation.h` (Tracy).
- [ ] Task 1.2: Trace L2 test and benchmark locations (NR RLC, PDCP, SDAP, MAC scheduler).
- [ ] Task 1.3: Trace L3 ASN.1 encoders/decoders and test suites (F1AP, E1AP, NGAP, NR RRC).
- [ ] Task 1.4: Trace CPU tuning and core isolation documentation (`doc/tuning_and_security.md`, `doc/ORAN_FHI7.2_Tutorial.md`).
- [ ] Task 1.5: Author `docs/GAP_ANALYSIS.md` (structured deliverable table with exact paths, line numbers, gaps, and proposed approaches) and `docs/NOTES.md`.

### Phase 2: Harness v0 Implementation & Verification
- [ ] Task 2.1: Implement platform manifest collector in Python (`harness/manifest.py`).
- [ ] Task 2.2: Define versioned JSON Schema (`schemas/result.schema.json`).
- [ ] Task 2.3: Implement benchmark runner CLI (`harness/runner.py`) supporting taskset pinning, N repetitions, raw output preservation, and `time_meas` metric extraction.
- [ ] Task 2.4: Write unit tests with pytest for manifest collection and schema validation using mocked/sample fixtures (`tests/test_manifest.py`, `tests/test_schema.py`).
- [ ] Task 2.5: Run real physim cases (idle vs loaded background noise floor) and generate real validated JSON results and markdown summary.

### Phase 3: Probe-Overhead Microbenchmark (C)
- [ ] Task 3.1: Analyze `time_meas.h` / `time_stats_t` API and CPU tick reading capabilities on arm64 vs x86_64.
- [ ] Task 3.2: Implement standalone C microbenchmark in `microbench/meas_overhead.c` comparing `time_meas` (start/stop) vs `clock_gettime(CLOCK_MONOTONIC)` vs empty loop baseline, with architectural tick guards.
- [ ] Task 3.3: Compile and execute microbenchmark across multiple iterations, recording median and p99 overhead measurements.

### Phase 4 / Final Polish: Documentation & Commit History
- [ ] Task 4.1: Write plain-language `README.md` covering quickstart, architecture, scope, deliverables, and claims/limitations.
- [ ] Task 4.2: Verify repository cleanliness, ensure no forbidden modifications or licensing breaches, and commit phases cleanly.

