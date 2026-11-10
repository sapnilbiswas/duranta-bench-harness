# Baseline Noise Floor Characterisation Report

This report summarizes real benchmark runs and noise floor characterisation performed with `duranta-bench-harness` using the compiled physical simulators (`nr_dlsim` and `nr_ulsim`) from Duranta-OpenAirInterface5g (commit `dfb296ab867050a7bde81b393fa31b757ada2c83`).

All runs were executed inside an Ubuntu 24.04 container on ARM64 (`aarch64`).
> **Notice**: Virtualized environment; results reflect containerized execution under hypervisor scheduling, not bare-metal real-time determinism.

---

## 1. Summary of Benchmark Runs

| Test Case ID | Simulator | Configuration | Pinned CPU | Target Metric | Idle Median | Loaded Median | Delta ($\Delta$) | Overhead (%) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `dl_40mhz_mcs15` | `nr_dlsim` | 40 MHz (106 PRB), MCS 15, SNR 20 dB, 1 layer | Core 0 | `PHY proc tx` | **49.92 µs** (IQR: 4.79 µs) | **50.94 µs** (IQR: 1.10 µs) | +1.02 µs | **+2.04%** |
| `ul_40mhz_mcs15` | `nr_ulsim` | 40 MHz (106 PRB), MCS 15, SNR 20 dB, 1 layer | Core 0 | `Total PHY proc rx` | **463.52 µs** (IQR: 15.72 µs) | **479.18 µs** (IQR: 26.21 µs) | +15.66 µs | **+3.38%** |
| `dl_100mhz_mcs15` | `nr_dlsim` | 100 MHz (273 PRB), MCS 15, SNR 20 dB, 1 layer | Core 0 | `PHY proc tx` | **80.19 µs** (IQR: 3.19 µs) | **82.38 µs** (IQR: 3.92 µs) | +2.19 µs | **+2.73%** |

---

## 2. Slot Deadline Margin Analysis (30 kHz SCS, $T_{\text{slot}} = 500\text{ µs}$)

For 5G NR numerology $\mu = 1$ (30 kHz subcarrier spacing), the nominal slot deadline is $500\text{ µs}$.

- **Downlink Processing (40 MHz / 106 PRBs)**:
  - TX processing ($49.92\text{ µs}$) consumes **~10.0%** of the slot deadline.
  - Generous deadline margin of $+450.08\text{ µs}$.
- **Downlink Processing (100 MHz / 273 PRBs)**:
  - TX processing ($80.19\text{ µs}$) consumes **~16.0%** of the slot deadline.
  - Deadline margin of $+419.81\text{ µs}$.
- **Uplink Processing (40 MHz / 106 PRBs)**:
  - Total RX processing ($463.52\text{ µs}$) consumes **~92.7%** of the $500\text{ µs}$ slot deadline.
  - Under background load, processing increases to $479.18\text{ µs}$ (**95.8%** of the deadline), leaving only $20.82\text{ µs}$ margin before slot deadline expiration.
  - This demonstrates why core isolation (`isolcpus`), thread pool parallelization (`-C` or `--thread-pool`), and LDPC hardware acceleration are critical for 5G NR uplink reception.

---

## 3. Probe-Overhead Microbenchmark Baseline

From standalone C microbenchmark ([`microbench/meas_overhead.c`](file:///Users/sapnilbiswas/LFX_5G/duranta-bench-harness/microbench/meas_overhead.c), 1,000,000 iterations):

| Probe Type | Min | Median | p99 | Max |
| :--- | :--- | :--- | :--- | :--- |
| `clock_gettime(CLOCK_MONOTONIC)` | 0 ns | 0 ns | 42 ns | 25,208 ns |
| `clock_gettime(CLOCK_MONOTONIC_RAW)` | 0 ns | 0 ns | 42 ns | 22,666 ns |
| `OAI time_meas (start/stop pair)` | 0 ns | 0 ns | 42 ns | 35,000 ns |
| `ARM64 cntvct_el0 counter` | 0 ticks | 0 ticks | 0 ticks | 2 ticks |

- The 42 ns p99 corresponds to 1 tick cycle of the ARM64 system counter ($24\text{ MHz} \to 41.67\text{ ns}$).
- `time_meas` probe overhead (~42 ns) represents less than $0.1\%$ of the $49.92\text{ µs}$ PHY TX processing time, confirming that macroscopic block timing does not heavily perturb L1 measurements.
