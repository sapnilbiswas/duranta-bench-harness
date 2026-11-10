# Benchmarking Notes, Assumptions, and Verifications

This document tracks all assumptions, verified paths and APIs, unverified items, and environment details for the Duranta-OAI benchmarking harness proof-of-concept.

## Environment & Hardware Manifest Details

- **Host Machine**: Apple Mac (Apple Silicon, ARM64)
- **Container Environment**: Docker Desktop running `ubuntu:24.04` (Ubuntu 24.04.5 LTS Noble Numbat), architecture `aarch64`.
- **Virtualization Notice**: ALL benchmark runs inside this container environment are labeled `virtualized, not representative of bare metal`. Virtualized timers, VM hypervisor scheduling, and container CPU shares do not reflect bare-metal real-time determinism.
- **Duranta Repository**:
  - Source: `https://github.com/duranta-project/openairinterface5g`
  - Base Commit: `dfb296ab867050a7bde81b393fa31b757ada2c83`
  - Commit Date: Fri Nov 6 17:02:49 2026 +0100
  - License: CSSL v1.0 (Zero OAI source code is copied into this harness repo; all builds reference the clone by path).

## Verified Repository Locations and Functions

### 1. Timing and Instrumentation
- `time_meas.h`: Located at `common/utils/time_meas.h` (355 lines).
  - Data structures: `time_stats_t` (lines 161–174), `time_stats_sorted_list_t` (lines 56–61).
  - API functions: `start_meas` (lines 255–276), `stop_meas` (lines 278–294), `reset_meas` (lines 296–305), `merge_meas` (lines 316–330), `get_time_meas_us` (line 197).
  - Clock sources: `clock_gettime_oai()` (lines 231–242) calling `clock_gettime(CLOCK_MONOTONIC_RAW)`.
  - CPU tick counter `rdtsc_oai()`:
    - x86_64 (lines 206–212): inline `rdtsc`
    - aarch64 (lines 213–220): `mrs %0, cntvct_el0`
- `time_meas.c`: Located at `common/utils/time_meas.c`.
- `instrumentation.h`: Located at `common/instrumentation.h` (25 lines).
  - Macros: `TracyCZone`, `TracyCZoneEnd`, `TracyCFrameMark`, `TracyCPlot`.
  - Active only when compiled with `-DTRACY_ENABLE=ON` (`#ifdef TRACY_ENABLE`). Otherwise defined as no-op stubs.
  - Active usage in codebase: Verified only in UE physical layer (`executables/nr-ue.c`, `openair1/SCHED_NR_UE/phy_procedures_nr_ue.c`, `openair1/PHY/NR_UE_ESTIMATION/nr_dl_channel_estimation.c`, `openair1/PHY/NR_UE_TRANSPORT/nr_pbch.c`). No usage in NR RLC, PDCP, SDAP, or GTP-U.

### 2. Physical Simulators (`physims`)
- Source: `openair1/SIMULATION/NR_PHY/dlsim.c` (`nr_dlsim`) and `openair1/SIMULATION/NR_PHY/ulsim.c` (`nr_ulsim`).
- CMake definition: `CMakeLists.txt` lines 1991–2020.
- Output metrics enabled by `-P`:
  - `PHY proc tx` (microseconds)
  - `DLSCH encoding time` (microseconds)
  - `Total PHY proc rx` (microseconds)
  - `ULSCH total decoding time` (microseconds)

### 3. Layer 2 Tests & Benchmarks
- RLC Google Benchmark: `openair2/LAYER2/nr_rlc/tests/benchmark_nr_rlc_am_entity.cpp` (105 lines). Uses Google Benchmark (`benchmark::State`) to measure AM entity SDU input, PDU generation, and packet processing across 100 to 20,000 iterations.
- RLC Unit Tests: `openair2/LAYER2/nr_rlc/tests/test_nr_rlc_am_entity.cpp` and `test.c`.
- PDCP Security Unit Tests: `openair2/LAYER2/nr_pdcp/tests/snow3g_tests.c`. Validates Snow3G encryption/integrity against 3GPP test vectors.
- MAC Scheduler Micro-benchmark: `tests/nrdlbench/dlbench.c` (679 lines). Measures wall-clock time of the standalone DL pipeline (scheduler -> LDPC encode -> modulate -> OFDM) across configurable number of UEs (`-u <num_ues>`).

### 4. Layer 3 ASN.1 Round-Trip Tests
- F1AP: `openair2/F1AP/tests/f1ap_lib_test.c` (lines 30–50: `f1ap_encode_decode` using `asn_check_constraints`, `aper_encode_to_buffer`, `aper_decode`).
- E1AP: `openair2/E1AP/tests/e1ap_lib_test.c` (lines 27–48: `e1ap_encode_decode` using APER encode/decode).
- NGAP: `openair3/NGAP/tests/ngap_lib_test.c` (lines 28–46: `ngap_encode_decode` using APER encode/decode).
- NR RRC: `openair2/RRC/NR/MESSAGES/tests/test_asn1_msg.cpp` (lines 38–49: `encode_and_decode_sib2` using `do_SIB2_NR` and `uper_decode`).

### 5. CPU Tuning & Core Isolation
- `doc/tuning_and_security.md`:
  - Sleep state disabling: `cpupower idle-set -D0` (line 36).
  - Softmodem thread pinning flags: `--L1s.[0].L1_tx_thread_core`, `--L1s.[0].L1_rx_thread_core`, `--thread-pool` (lines 88–93).
  - Multithreading: `--L1s.[0].L1_num_tx_sym_per_thread` (line 99).
- `doc/ORAN_FHI7.2_Tutorial.md`:
  - Kernel cmdline parameters: `isolcpus=domain,4-31 nohz_full=4-31 irqaffinity=0,1,2,3 rcu_nocbs=4-31 hugepagesz=1G hugepages=20 intel_pstate=disable` (and aarch64 variant lines 120–135).

## Unverified Items & Limitations

1. **Bare-metal Core Isolation under Docker / macOS**:
   - `isolcpus`, CPU governor switching (`performance`), and `cpupower` cannot be configured inside an unprivileged Docker Desktop container on macOS because the underlying Linux kernel is managed by the macOS Hypervisor / Docker virtual machine.
   - Any attempt to read `/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor` in this virtual environment may return permission denied or unavailable paths.
   - Status: Marked **unverified on bare metal**; harness will safely report "not captured" or "virtualized" without crashing.

2. **CPU Clock and RAM Speed Scaling**:
   - Dynamic frequency scaling and RAM clock adjustment are not documented in OAI repository docs (`doc/`).
   - Hardware frequency stepping requires bare-metal BIOS access or kernel MSR/cpufreq privileges, which are absent in virtualized container testbeds.
   - Status: Proposed in GAP_ANALYSIS as a deliverable requiring dedicated bare-metal testbed automation (e.g. `turbostat`, `dmidecode`, `cpupower frequency-set`).

## Build & Runtime Incidents Observed

1. **Docker Desktop VM Memory Limit under High Concurrency**:
   - Initial parallel compilation (`ninja -C /build nr_dlsim nr_ulsim` defaulting to `-j 8`) triggered a memory pressure restart of Docker Desktop's Virtualization framework VM (`memoryMiB 8192`) at target 7178/10774, resulting in `error waiting for container: unexpected EOF`.
   - Resolution: Resumed with `-j 4` concurrency (`ninja -j 4 -C /build nr_dlsim nr_ulsim`). Ninja cleanly resumed from the existing build cache in the mounted build directory without re-compiling the 7,177 previously completed object targets.


