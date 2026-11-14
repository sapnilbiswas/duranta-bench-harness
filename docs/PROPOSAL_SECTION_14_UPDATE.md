# PROPOSAL UPDATE FOR CLAUDE: SECTION 14 ("Prototype so far")

Use this document to update and complete Section 14 of the LFX Mentorship proposal (*"Benchmarking the L1, L2 and L3 Functions of Duranta-OAI Across Operating Systems and Hardware"*).

This file contains:
1. **Ready-to-Paste Proposal Text**: The complete, finalized text for Section 14 replacing `[UPDATE: add the corrected results here.]`, matching the applicant's honest, technical, and understated tone.
2. **Detailed Reference Tables & Metrics**: Full datasets from the 30-repetition benchmark runs, batched microbenchmarks, and procedure latency runs.
3. **Context for Claude**: Background notes and rules to ensure no numbers or paths are hallucinated.

---

## 1. Ready-to-Paste Proposal Text (Section 14)

```markdown
### 14. Prototype so far

Repository: https://github.com/sapnilbiswas/duranta-bench-harness. It contains a manifest collector, a versioned result schema, a runner with CPU pinning and repeat runs, an idle-versus-loaded noise-floor analysis, a probe-overhead microbenchmark that builds against the `time_meas` header by path, a gap analysis against the deliverables, and a tshark script for procedure latency. It does not copy any Duranta source.

**What it does and does not show**: The harness executes inside a reproducible Ubuntu 24.04 container on ARM64 virtualized hardware. Because the host is a virtualized container environment, all results are explicitly tagged `"virtualized, not representative of bare metal"`. They prove the pipeline and measurement discipline work, establishing baseline methodology for the bare-metal deliverables in the mentorship.

#### Corrected Results (30 Repetitions & Batched Microbenchmarking)

##### 1. Probe-Overhead Microbenchmark (Single-Call vs Batched Timing)
On the ARM64 virtual machine, the system counter (`cntfrq_el0`) runs at 24.00 MHz, giving a physical clock resolution floor of **41.67 ns**. In the initial unbatched test (1,000,000 single iterations), individual invocations taking less than 41.67 ns fell into the same clock tick, reporting an apparent median of 0 ns.

To overcome clock quantization, I implemented batched timing measuring 1,000 batches of 1,000 operations each (1,000,000 total operations) to calculate true amortized cost per call:

| Measurement Target | Single-Call Median (Quantized) | Batched Amortized Median | Batched p99 | Batched Max |
| :--- | :---: | :---: | :---: | :---: |
| **Empty loop baseline** | 0 ns | 0.33 ns | 0.33 ns | 0.38 ns |
| **Bare `clock_gettime(CLOCK_MONOTONIC)`** | 0 ns | 16.29 ns | 23.58 ns | 29.79 ns |
| **Bare `clock_gettime(CLOCK_MONOTONIC_RAW)`** | 0 ns | 16.58 ns | 23.88 ns | 39.83 ns |
| **OAI `time_meas` (`start_meas` / `stop_meas`)** | 0 ns | **39.46 ns** | 53.96 ns | 67.46 ns |
| **ARM64 `cntvct_el0` tick read** | 0 ticks | 0.33 ns | 0.50 ns | 0.58 ns |

*Finding*: An OAI `start_meas` / `stop_meas` pair incurs two `clock_gettime(CLOCK_MONOTONIC_RAW)` invocations (~16.6 ns each) plus struct accounting, totaling **39.46 ns**. Against a ~48 µs PHY transmission, this represents **0.08% probe overhead**, confirming that `time_meas` introduces negligible perturbation for macroscopic L1 block timings.

##### 2. Physical Simulator Benchmarks & Noise Floor (30 Repetitions Each)
The test runner was executed for 30 repetitions idle and 30 repetitions under background CPU contention on non-pinned cores (pinned to CPU 0, background stress on CPUs 1–3, 100 frames per run, $N = 30$):

| Test Case | Metric | Idle Median (IQR) | Loaded Median (IQR) | Shift (Δ) | % Shift | 500 µs Slot Budget |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Case 1: DL 40 MHz** (106 PRB, MCS 15) | `phy_proc_tx_us` | 48.26 µs (1.17) | 49.80 µs (0.89) | +1.54 µs | +3.19% | 9.65% → 9.96% |
| **Case 2: UL 40 MHz** (106 PRB, MCS 15) | `total_phy_proc_rx_us` | 392.00 µs (6.89) | 405.64 µs (7.56) | +13.64 µs | +3.48% | **78.40% → 81.13%** |
| **Case 3: DL 100 MHz** (273 PRB, MCS 15) | `phy_proc_tx_us` | 77.69 µs (1.65) | 79.79 µs (1.32) | +2.10 µs | +2.70% | 15.54% → 15.96% |

*Slot Deadline Observation*: Under 3GPP numerology $\mu=1$ (30 kHz SCS), the slot deadline is 500 µs. Downlink processing easily clears the deadline (< 16% budget). However, uplink processing consumes **78.4% of the slot budget idle** and rises to **81.1% under background load**, leaving only ~94 µs of headroom before deadline violation on this virtualized setup.

##### 3. Control-Plane Procedure Latency (`scripts/control_plane_latency.py`)
To validate L3 control-plane extraction, the tshark script was executed over 30 repeated F1Setup procedure transactions:
- **Completed Transactions**: 30 / 30 (100% success rate, 0 unmatched/timeouts)
- **Round-Trip Latency**: Min 3.041 ms | **Median 3.568 ms** | Mean 3.572 ms | Max 4.168 ms | IQR 0.552 ms
```

---

## 2. Complete Reference Data & Artifacts

### A. Environment and Platform Manifest
- **Duranta Git Commit**: `dfb296ab867050a7bde81b393fa31b757ada2c83`
- **Compiler**: GCC 13.2.0 (`gcc (Ubuntu 13.2.0-23ubuntu4) 13.2.0`)
- **OS / Kernel**: Ubuntu 24.04 LTS on Linux 7.0.12-linuxkit (`aarch64`)
- **CPU Topology**: 8 virtual CPU cores, ARM64 Apple Silicon
- **System Counter**: ARM64 `cntfrq_el0 = 24.00 MHz` (resolution: $41.67\text{ ns}$)
- **Virtualization Tag**: `"virtualized, not representative of bare metal"`

### B. Microbenchmark File References
- C source code: [`microbench/meas_overhead.c`](file:///Users/sapnilbiswas/LFX_5G/duranta-bench-harness/microbench/meas_overhead.c)
- Build file: [`microbench/Makefile`](file:///Users/sapnilbiswas/LFX_5G/duranta-bench-harness/microbench/Makefile)
- Raw execution output: [`results/microbench_batched_output.txt`](file:///Users/sapnilbiswas/LFX_5G/duranta-bench-harness/results/microbench_batched_output.txt)

### C. Physical Simulator Benchmark Result Files
- Case 1 (DL 40 MHz, 30 reps): [`results/dl_case1_40mhz_mcs15_30reps.json`](file:///Users/sapnilbiswas/LFX_5G/duranta-bench-harness/results/dl_case1_40mhz_mcs15_30reps.json)
  - Idle raw values: 47.39 to 53.65 µs (Median: 48.26 µs, IQR: 1.17 µs)
  - Loaded raw values: 49.01 to 78.08 µs (Median: 49.80 µs, IQR: 0.89 µs)
- Case 2 (UL 40 MHz, 30 reps): [`results/ul_case2_40mhz_mcs15_30reps.json`](file:///Users/sapnilbiswas/LFX_5G/duranta-bench-harness/results/ul_case2_40mhz_mcs15_30reps.json)
  - Idle raw values: 385.07 to 406.73 µs (Median: 392.00 µs, IQR: 6.89 µs)
  - Loaded raw values: 402.40 to 440.80 µs (Median: 405.64 µs, IQR: 7.56 µs)
- Case 3 (DL 100 MHz, 30 reps): [`results/dl_case3_100mhz_mcs15_30reps.json`](file:///Users/sapnilbiswas/LFX_5G/duranta-bench-harness/results/dl_case3_100mhz_mcs15_30reps.json)
  - Idle raw values: 76.14 to 84.21 µs (Median: 77.69 µs, IQR: 1.65 µs)
  - Loaded raw values: 78.84 to 131.87 µs (Median: 79.79 µs, IQR: 1.32 µs)

### D. Control-Plane Procedure Latency References
- Extractor script: [`scripts/control_plane_latency.py`](file:///Users/sapnilbiswas/LFX_5G/duranta-bench-harness/scripts/control_plane_latency.py)
- 30-rep PCAP fixture: [`tests/fixtures/f1ap_30reps.pcapng`](file:///Users/sapnilbiswas/LFX_5G/duranta-bench-harness/tests/fixtures/f1ap_30reps.pcapng)
- 30-rep Result JSON: [`results/f1ap_30reps_latency.json`](file:///Users/sapnilbiswas/LFX_5G/duranta-bench-harness/results/f1ap_30reps_latency.json)

---

## 3. Instructions for Claude

When integrating this into the broader proposal:
1. **Do not alter the numbers**: Use the exact medians, IQRs, and percentages provided above.
2. **Keep the tone modest**: Retain the applicant's self-critical note explaining that these virtualized container results are proofs of pipeline functionality and noise-floor methodology, not definitive bare-metal figures.
3. **Emphasize the clock resolution discovery**: Explain that single-call timing hit the 41.67 ns counter floor (`cntfrq_el0 = 24 MHz`), and batched timing solved it by measuring 1,000,000 operations across 1,000-op windows, giving 39.46 ns per probe.
4. **Preserve the CSSL v1.0 license compliance**: Reiterate that the harness builds out-of-source against Duranta by path without copying code or modifying Duranta files.
