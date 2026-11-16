# Baseline Noise Floor Characterisation Report

This report summarizes real benchmark runs and noise floor characterisation performed with `duranta-bench-harness` using the compiled physical simulators (`nr_dlsim` and `nr_ulsim`) from Duranta-OpenAirInterface5g (commit `dfb296ab867050a7bde81b393fa31b757ada2c83`).

All runs were executed inside an Ubuntu 24.04 container on ARM64 (`aarch64`).
> **Notice**: Virtualized environment; results reflect containerized execution under hypervisor scheduling, not bare-metal real-time determinism.

---

## 1. Summary of Benchmark Runs (30 Repetitions Each, $N = 30$)

Simulator runs were executed with 30 repetitions idle and 30 repetitions under background CPU load on non-pinned cores (pinned with `taskset -c 0`, background load on cores 1–3, 100 frames per repetition):

| Test Case ID | Simulator | Configuration | Target Metric | Idle Median (IQR) | Loaded Median (IQR) | Delta ($\Delta$) | Shift (%) |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| `dl_case1_40mhz_mcs15_30reps` | `nr_dlsim` | 40 MHz (106 PRB), MCS 15, SNR 20 dB | `phy_proc_tx_us` | **48.26 µs** (1.17 µs) | **49.80 µs** (0.89 µs) | +1.54 µs | **+3.19%** |
| `ul_case2_40mhz_mcs15_30reps` | `nr_ulsim` | 40 MHz (106 PRB), MCS 15, SNR 20 dB | `total_phy_proc_rx_us` | **392.00 µs** (6.89 µs) | **405.64 µs** (7.56 µs) | +13.64 µs | **+3.48%** |
| `ul_case2_40mhz_mcs15_tpool8_30reps` | `nr_ulsim` | 40 MHz (106 PRB), MCS 15, SNR 20 dB, `-C8` (thread pool) | `total_phy_proc_rx_us` | **300.00 µs** (20.59 µs) | **398.45 µs** (101.18 µs) | +98.45 µs | **+32.82%** |
| `dl_case3_100mhz_mcs15_30reps` | `nr_dlsim` | 100 MHz (273 PRB), MCS 15, SNR 20 dB | `phy_proc_tx_us` | **77.69 µs** (1.65 µs) | **79.79 µs** (1.32 µs) | +2.10 µs | **+2.70%** |

*(Reference from initial 5-rep exploratory runs archived in `archive_5rep/`: DL 40 MHz was 49.92 µs / 50.94 µs; UL 40 MHz was 463.52 µs / 479.18 µs; DL 100 MHz was 80.19 µs / 82.38 µs).*

---

## 2. Slot Deadline Margin Analysis (30 kHz SCS, $T_{\text{slot}} = 500\text{ µs}$)

For 5G NR numerology $\mu = 1$ (30 kHz subcarrier spacing), the nominal slot deadline is $500\text{ µs}$.

- **Downlink Processing (40 MHz / 106 PRBs)**:
  - TX processing ($48.26\text{ µs}$) consumes **~9.65%** of the slot deadline.
  - Generous deadline margin of $+451.74\text{ µs}$.
- **Downlink Processing (100 MHz / 273 PRBs)**:
  - TX processing ($77.69\text{ µs}$) consumes **~15.54%** of the slot deadline.
  - Deadline margin of $+422.31\text{ µs}$.
- **Uplink Processing (40 MHz / 106 PRBs, Single-Core Pinning vs Thread Pool)**:
  - In Case 2 (`ul_case2_40mhz_mcs15_30reps`), single-core execution pinned to CPU 0 consumes **$392.00\text{ µs}$** (**78.4%** of the $500\text{ µs}$ slot deadline) idle, shifting to **$405.64\text{ µs}$** (**81.1%**) under background load (+3.48% shift).
  - In Case 2b (`ul_case2_40mhz_mcs15_tpool8_30reps`), instantiating an 8-worker thread pool (`-C8`) offloads LDPC segment decoding across host cores, reducing idle latency to **$300.00\text{ µs}$** (**60.0%** of the deadline).
  - **Caveats for Case 2b**: Because the `-C8` worker threads float across unpinned host cores (0–7), running background load on cores 1–3 causes worker preemption. Under load, median latency rises to **$398.45\text{ µs}$** (+32.82% shift) and the IQR expands from $20.59\text{ µs}$ to $101.18\text{ µs}$, illustrating that thread-pool scaling requires explicit thread-to-core affinity and core isolation to prevent scheduling interference.

---

## 3. Probe-Overhead Microbenchmark (Single-Call vs Batched Timing)

From standalone C microbenchmark ([`microbench/meas_overhead.c`](../microbench/meas_overhead.c), 1,000,000 operations, hardware counter frequency `cntfrq_el0 = 24.00 MHz`, tick resolution floor $41.67\text{ ns}$):

### Single-Call Unbatched (Subject to Timer Quantization)
| Probe Type | Min | Median | p99 | Max |
| :--- | :---: | :---: | :---: | :---: |
| `Empty loop baseline` | 0 ns | 0 ns | 42 ns | 57,417 ns |
| `clock_gettime(CLOCK_MONOTONIC)` | 0 ns | 0 ns | 42 ns | 13,292 ns |
| `clock_gettime(CLOCK_MONOTONIC_RAW)` | 0 ns | 0 ns | 42 ns | 13,083 ns |
| `OAI time_meas (start/stop pair)` | 0 ns | 0 ns | 42 ns | 15,500 ns |

### Batched Amortized Cost (1,000 Batches of 1,000 Ops)
| Probe Type | Min | Median | p99 | Max |
| :--- | :---: | :---: | :---: | :---: |
| `Empty loop baseline` | 0.25 ns | 0.33 ns | 0.33 ns | 0.38 ns |
| `clock_gettime(CLOCK_MONOTONIC)` | 16.21 ns | 16.29 ns | 23.58 ns | 29.79 ns |
| `clock_gettime(CLOCK_MONOTONIC_RAW)` | 16.46 ns | 16.58 ns | 23.88 ns | 39.83 ns |
| `OAI time_meas (start/stop pair)` | 39.33 ns | **39.46 ns** | 53.96 ns | 67.46 ns |

- One `time_meas` start/stop pair (~39.46 ns) is about **0.08%** of the Case 1 transmit time ($48.26\text{ µs}$), but a real run fires many pairs across sub-functions (channel estimation, symbol processing, encoding/decoding), so cumulative instrumentation overhead must be considered when profiling fine-grained routines.

---

## 4. Control-Plane Procedure Latency (30 Repetitions)

From `scripts/control_plane_latency.py` across 30 repeated F1Setup procedure transactions ([`f1ap_30reps_latency.json`](f1ap_30reps_latency.json)):
- **Completed Transactions**: 30 / 30 (100% success rate, 0 unmatched / timeouts)
- **Round-Trip Latency**: Min 3.041 ms | **Median 3.568 ms** | Mean 3.572 ms | Max 4.168 ms | IQR 0.552 ms
