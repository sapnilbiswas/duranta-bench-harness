# Section 14: Prototype Results Summary

This document summarizes the verified benchmark results from `duranta-bench-harness` corresponding to Section 14 ("Prototype so far") of the mentorship deliverables.

Repository: https://github.com/sapnilbiswas/duranta-bench-harness

---

## 1. Prototype Scope and Status

The harness provides:
- Platform manifest collector (`harness/manifest.py`)
- Versioned JSON result schema (`schemas/result.schema.json`)
- Simulator runner with CPU core pinning (`taskset -c 0`) and repeat runs (`harness/runner.py`)
- Idle vs background-loaded noise-floor characterisation engine
- Standalone probe-overhead microbenchmark in C building against `time_meas.h` by path (`microbench/meas_overhead.c`)
- Gap analysis against the mentorship deliverables (`docs/GAP_ANALYSIS.md`)
- Control-plane procedure latency extractor using tshark (`scripts/control_plane_latency.py`)
- 12/12 automated unit and integration tests (`tests/`)

*Environment Note*: All runs execute inside an Ubuntu 24.04 container on ARM64 virtualized hardware. Outputs are explicitly tagged `"virtualized, not representative of bare metal"`.

---

## 2. Probe-Overhead Microbenchmark (Single-Call vs Batched Timing)

On the ARM64 virtual machine, the system counter (`cntfrq_el0`) runs at 24.00 MHz, giving a physical clock resolution floor of **41.67 ns**. In the initial unbatched test (1,000,000 single iterations), individual invocations taking less than 41.67 ns fell into the same clock tick, reporting an apparent median of 0 ns.

To overcome clock quantization, batched timing was implemented measuring 1,000 batches of 1,000 operations each (1,000,000 total operations) to calculate true amortized cost per call:

| Measurement Target | Single-Call Median (Quantized) | Batched Amortized Median | Batched p99 | Batched Max |
| :--- | :---: | :---: | :---: | :---: |
| **Empty loop baseline** | 0 ns | 0.33 ns | 0.33 ns | 0.38 ns |
| **Bare `clock_gettime(CLOCK_MONOTONIC)`** | 0 ns | 16.29 ns | 23.58 ns | 29.79 ns |
| **Bare `clock_gettime(CLOCK_MONOTONIC_RAW)`** | 0 ns | 16.58 ns | 23.88 ns | 39.83 ns |
| **OAI `time_meas` (`start_meas` / `stop_meas`)** | 0 ns | **39.46 ns** | 53.96 ns | 67.46 ns |
| **ARM64 `cntvct_el0` tick read** | 0 ticks | 0.33 ns | 0.50 ns | 0.58 ns |

*Finding*: An OAI `start_meas` / `stop_meas` pair incurs two `clock_gettime(CLOCK_MONOTONIC_RAW)` invocations (~16.6 ns each) plus struct accounting, totaling **39.46 ns**. Against a ~48 µs PHY transmission, this represents **0.08% probe overhead**, confirming that `time_meas` introduces negligible perturbation for macroscopic L1 block timings.

---

## 3. Physical Simulator Benchmarks & Noise Floor (30 Repetitions Each, $N = 30$)

Simulator benchmarks were evaluated under both single-core execution and multi-threaded worker pool configurations:

| Test Case | Configuration & Threading | Pinned CPU | Metric | Idle Median (IQR) | Loaded Median (IQR) | Shift (Δ) | % Shift | 500 µs Slot Budget |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Case 1: DL 40 MHz** (106 PRB, MCS 15) | Single-thread (`nr_dlsim`) | Core 0 | `phy_proc_tx_us` | 48.26 µs (1.17) | 49.80 µs (0.89) | +1.54 µs | +3.19% | 9.65% → 9.96% |
| **Case 2a: UL 40 MHz** (106 PRB, MCS 15) | Single-thread (`threadCnt=0`) | Core 0 | `total_phy_proc_rx_us` | 392.00 µs (6.89) | 405.64 µs (7.56) | +13.64 µs | +3.48% | **78.40% → 81.13%** |
| **Case 2b: UL 40 MHz** (106 PRB, MCS 15) | Multi-thread (`-C8` worker pool) | Floating (Cores 0–7) | `total_phy_proc_rx_us` | 300.00 µs (20.59) | 398.45 µs (101.18) | +98.45 µs | +32.82% | **60.00% → 79.69%** |
| **Case 3: DL 100 MHz** (273 PRB, MCS 15) | Single-thread (`nr_dlsim`) | Core 0 | `phy_proc_tx_us` | 77.69 µs (1.65) | 79.79 µs (1.32) | +2.10 µs | +2.70% | 15.54% → 15.96% |

### Clarification on Threading and Pinning in Case 2
- **Single-Core Baseline (Case 2a)**: Ran with `threadCnt = 0` (no `-C` flag) pinned to Core 0 (`taskset -c 0`). No worker threads were spawned, so the 392.00 µs figure reflects pure sequential execution on a single core (sequential LDPC decoding alone took ~356 µs).
- **Multi-Threaded Worker Pool (Case 2b)**: Matches `doc/kpi.md` line 222 (`-C8`). Spawning 8 floating worker threads parallelizes LDPC decoding, reducing idle execution time to **300.00 µs** (60.0% of slot budget). However, because worker threads float across cores, applying background contention on cores 4–7 causes thread descheduling and cache thrashing, increasing latency by **+32.8% to 398.45 µs**.
- If `-C8` is passed while the entire process is pinned to Core 0 (`taskset -c 0`), all 8 worker threads and the main thread time-slice on that single core, inflating processing time to **458.16 µs**. This demonstrates why explicit thread affinity (`-Y`) and core isolation (`isolcpus`) are vital in Deliverable 6.

---

## 4. Control-Plane Procedure Latency (`scripts/control_plane_latency.py`)

Executed over 30 repeated F1Setup procedure transactions:
- **Completed Transactions**: 30 / 30 (100% success rate, 0 unmatched/timeouts)
- **Round-Trip Latency**: Min 3.041 ms | **Median 3.568 ms** | Mean 3.572 ms | Max 4.168 ms | IQR 0.552 ms

*Capture Source Clarification*: These 30 F1Setup transactions were extracted from a **scripted validation PCAP fixture (`tests/fixtures/f1ap_30reps.pcapng`)** generated with `text2pcap` using verified 3GPP APER hex vectors from Duranta's `f1ap_lib_test.c`. This verifies that the tshark extractor correctly parses SCTP PPID 62, identifies procedure codes, matches request-response pairs, detects timeouts, and computes percentile statistics. **It does not represent Duranta's live CU/DU over-the-wire latency.** Live characterization over live SCTP links is one of the primary deliverables of the mentorship itself (Deliverable 4).
