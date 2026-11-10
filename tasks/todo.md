# Tasks & Checkpoints: Duranta Bench Harness

## Phase 0: Environment Setup & Physim Build
- [x] Task 0.1: Create container build definition (`docker/Dockerfile`) for Ubuntu 24.04 with OAI build prerequisites and test Python environment.
- [x] Task 0.2: Build container image and compile `nr_dlsim` and `nr_ulsim` against the Duranta repo without modifying Duranta source.
- [x] Task 0.3: Execute a smoke test of `nr_dlsim -h` and `nr_ulsim -h` inside the container and document exact build commands and findings.

## Checkpoint: Phase 0
- [x] Container environment is functional on host architecture (aarch64).
- [x] `nr_dlsim` and `nr_ulsim` built successfully without altering the Duranta clone.
- [x] Verified smoke execution of physical simulators.

## Phase 1: Deep Codebase Reading & Gap Analysis
- [x] Task 1.1: Trace existing timing instrumentation: `common/utils/time_meas.{h,c}` and `common/instrumentation.h` (Tracy).
- [x] Task 1.2: Trace L2 test and benchmark locations (NR RLC, PDCP, SDAP, MAC scheduler).
- [x] Task 1.3: Trace L3 ASN.1 encoders/decoders and test suites (F1AP, E1AP, NGAP, NR RRC).
- [x] Task 1.4: Trace CPU tuning and core isolation documentation (`doc/tuning_and_security.md`, `doc/ORAN_FHI7.2_Tutorial.md`).
- [x] Task 1.5: Author `docs/GAP_ANALYSIS.md` (structured deliverable table with exact paths, line numbers, gaps, and proposed approaches) and `docs/NOTES.md`.

## Checkpoint: Phase 1
- [x] Every path and line reference verified against the clone.
- [x] Unverified items documented in `docs/NOTES.md`.
- [x] Complete deliverable mapping covering deliverables (1) through (8).

## Phase 2: Harness v0 Implementation & Verification
- [x] Task 2.1: Implement platform manifest collector in Python (`harness/manifest.py`).
- [x] Task 2.2: Define versioned JSON Schema (`schemas/result.schema.json`).
- [x] Task 2.3: Implement benchmark runner CLI (`harness/runner.py`) supporting taskset pinning, N repetitions, raw output preservation, and `time_meas` metric extraction.
- [x] Task 2.4: Write unit tests with pytest for manifest collection and schema validation using fixtures (`tests/test_manifest.py`, `tests/test_schema.py`) — 8/8 tests passing.
- [x] Task 2.5: Run real physim cases (idle vs loaded background noise floor) and generate real validated JSON results and markdown summary.

## Checkpoint: Phase 2
- [x] Pytest suite passes 100%.
- [x] Real benchmark runs output schema-validated JSON with manifest and raw logs.
- [x] Noise floor idle vs loaded characterisation completed and summarized (`results/NOISE_FLOOR_REPORT.md`).

## Phase 3: Probe-Overhead Microbenchmark (C)
- [x] Task 3.1: Analyze `time_meas.h` / `time_stats_t` API and CPU tick reading capabilities on arm64 vs x86_64.
- [x] Task 3.2: Implement standalone C microbenchmark in `microbench/meas_overhead.c` comparing `time_meas` (start/stop) vs `clock_gettime(CLOCK_MONOTONIC)` vs empty loop baseline, with architectural tick guards.
- [x] Task 3.3: Compile and execute microbenchmark across multiple iterations (1,000,000 iterations), recording median and p99 overhead measurements.

## Checkpoint: Phase 3
- [x] Standalone C microbench compiles and runs cleanly.
- [x] Numbers reported directly with no fabricated metrics (ARM64 cntvct_el0 / clock_gettime median 0 ns, p99 42 ns).

## Final Review & Deliverables
- [x] Plain-language `README.md` complete with honest quickstart, limitations, and reproducible instructions.
- [x] Real benchmark JSON result files generated, validated, and committed.
- [x] All git commits are clean, descriptive, and atomic.
