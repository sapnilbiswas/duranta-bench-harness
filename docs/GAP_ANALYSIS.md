# Gap Analysis: Duranta-OAI Benchmarking Deliverables

This document compares the current state of the Duranta-OpenAirInterface5g codebase against the 8 listed deliverables of the LFX Mentorship proposal *"Benchmarking the L1, L2 and L3 Functions of Duranta-OAI Across Operating Systems and Hardware"*.

Every file path, function name, and line reference has been verified directly against the cloned repository at commit `dfb296ab867050a7bde81b393fa31b757ada2c83`.

---

## Deliverables Comparison Matrix

| Deliverable | What Exists in Repo (Verified Paths & Lines) | What is Missing | Proposed Approach |
| :--- | :--- | :--- | :--- |
| **1. Reproducible benchmark harness** (manifest, JSON schema, runner, noise floor) | • `doc/kpi.md` (lines 202–281): Manual example commands and static tables for `nr_dlsim` and `nr_ulsim`<br>• `doc/physical-simulators.md` (lines 61–100): Instructions for running via ctest | • No structured platform manifest collector<br>• No JSON schema or machine-readable result output<br>• No automated runner with CPU pinning (`taskset`)<br>• No noise floor measurement methodology | Build `duranta-bench-harness`: Python 3.11 CLI runner that captures full platform manifest (`lscpu --json`, OS, kernel, governor, virtualization), validates output against JSON schema, and measures idle vs loaded noise floor. |
| **2. Timing instrumentation in NR RLC, PDCP, SDAP, GTP-U** (time_meas & Tracy) | • `common/utils/time_meas.h` (lines 161–174: `time_stats_t`; lines 255–294: `start_meas`/`stop_meas`)<br>• `common/instrumentation.h` (lines 1–25: Tracy stubs and macros)<br>• Tracy is currently used **only** in UE physical layer (`executables/nr-ue.c` lines 405, 589; `openair1/SCHED_NR_UE/phy_procedures_nr_ue.c` lines 859, 1119) | • **Zero** instrumentation in NR RLC (`openair2/LAYER2/nr_rlc`)<br>• **Zero** instrumentation in NR PDCP (`openair2/LAYER2/nr_pdcp`)<br>• **Zero** instrumentation in SDAP (`openair2/NRUP`)<br>• **Zero** instrumentation in GTP-U (`openair3/ocp-gtpu`) | Add conditionally compiled `time_stats_t` and `TracyCZone` probes at major ingress/egress points: RLC SDU delivery/PDU generation (`recv_sdu`, `generate_pdu`), PDCP ciphering/integrity (`process_sdu`), SDAP encapsulation, and GTP-U tunnel handling. |
| **3. L2 characterisation** (scheduler 1–128 UEs, PDCP cipher/integrity, RLC segmentation, locks) | • `tests/nrdlbench/dlbench.c` (lines 4–13, 305–320): Standalone DL scheduler + PHY TX benchmark supporting `-u <num_ues>`<br>• `openair2/LAYER2/nr_rlc/tests/benchmark_nr_rlc_am_entity.cpp` (lines 34–95): Google Benchmark for RLC AM entity<br>• `openair2/LAYER2/nr_pdcp/tests/snow3g_tests.c`: Snow3G 3GPP vector test | • No automated scheduler scaling sweep up to 128 UEs<br>• No throughput benchmarks for PDCP AES-CTR (NEA2) vs Snow3G (NEA1) vs ZUC (NEA3)<br>• No isolated RLC segmentation cost test across PDU grant sizes<br>• No measurement of lock hold times or memcpy costs | Build harness scripts around `nr_dlbench` to parameterize UE scaling ($1 \to 128$). Implement standalone microbenchmarks for PDCP crypto throughput across cipher algorithms and buffer sizes. Profile lock wait times via Tracy lock instrumentation. |
| **4. L3 characterisation** (ASN.1 encode/decode for F1AP, E1AP, NGAP, NR RRC; procedure latency) | • `openair2/F1AP/tests/f1ap_lib_test.c` (lines 30–50: `f1ap_encode_decode`)<br>• `openair2/E1AP/tests/e1ap_lib_test.c` (lines 27–48: `e1ap_encode_decode`)<br>• `openair3/NGAP/tests/ngap_lib_test.c` (lines 28–46: `ngap_encode_decode`)<br>• `openair2/RRC/NR/MESSAGES/tests/test_asn1_msg.cpp` (lines 38–49: `encode_and_decode_sib2`) | • Existing tests only verify correctness/assertions; they do not measure execution latency or throughput<br>• No timing probes around `aper_encode_to_buffer` or `aper_decode`<br>• No automated tool to measure procedure latency from packet captures | Create a microbenchmark wrapping existing ASN.1 PDU generators with high-resolution timers (`clock_gettime(CLOCK_MONOTONIC)` or Google Benchmark). Develop a tshark analysis script to calculate procedure latency (e.g. F1 Setup, Context Setup) from pcap traces. |
| **5. Cross-platform report against slot deadline** | • `doc/kpi.md` (lines 202–281): Reports processing times for 40 MHz and 100 MHz on AMD Ryzen 9 7945HX (x86_64) and DGX Spark Cortex-X925 (aarch64) | • No automated evaluation of processing times against 3GPP numerology slot deadlines ($1\text{ ms} / 2^\mu$)<br>• No margin reporting ($\text{Margin} = T_{\text{slot}} - T_{\text{proc}}$)<br>• No cross-layer budget breakdown (L1 vs L2) | Integrate slot deadline thresholds into the result schema (500 µs for $\mu=1$ / 30 kHz SCS; 250 µs for $\mu=2$ / 60 kHz SCS; 125 µs for $\mu=3$ / 120 kHz SCS) and report deadline consumption percentage. |
| **6. Improved tuning guide** | • `doc/tuning_and_security.md` (lines 17–50, 72–104): Sleep states, CPU core assignment, Zen CCX considerations<br>• `doc/ORAN_FHI7.2_Tutorial.md` (lines 100–140): Kernel boot line `isolcpus`, `nohz_full`, `rcu_nocbs` | • Fragmented guidance across multiple documents<br>• Missing ARM64 server tuning (heterogeneous cores, NUMA, system registers)<br>• Missing quantitative pre-flight verification commands (how to verify zero jitter before launch) | Author a consolidated tuning guide with clear, copy-pasteable configuration snippets and an automated verification script checking `/sys/devices/system/cpu/isolated` and interrupt affinities. |
| **7. Effect of CPU clock and RAM speed** | • None in OAI docs (only mentions setting governor to `performance` or disabling sleep states) | • No existing benchmarks, datasets, or methodology investigating sensitivity to CPU clock steps or memory speed (DDR4 vs DDR5, RAM clock, NUMA latency) | Define a systematic benchmark protocol using `cpupower frequency-set` to sweep fixed CPU frequencies, and test memory channel saturation impact on LDPC decoding and L2 buffer copying. |
| **8. Docs and final report** | • Existing documentation in `doc/` | • No unified final mentorship report synthesizing cross-platform findings with clear limitations and reproducibility instructions | Deliver a complete, honest report, clear quickstart README, validated result JSON files, and documented limitations. |

---

## Detailed Findings on Key Repository Components

### 1. Timing Infrastructure (`time_meas`)
- **Headers & Implementation**:
  - `common/utils/time_meas.h` defines `time_stats_t` containing cumulative runtime `diff`, squared runtime `diff_square`, peak `max`, iteration count `trials`, and optional percentile tracking via `time_stats_sorted_list_t`.
  - Inlined measurement macros: `start_meas(time_stats_t *ts)` and `stop_meas(time_stats_t *ts)`.
  - Under Linux, `clock_gettime_oai()` invokes `clock_gettime(CLOCK_MONOTONIC_RAW, &time)`.
  - Architecture-specific tick reading in `rdtsc_oai()`:
    - x86_64: `asm volatile ("rdtsc" : "=a" (a), "=d" (d));`
    - aarch64: `asm volatile("mrs %0, cntvct_el0" : "=r"(r));`
- **Observations & Gaps**:
  - `start_meas` and `stop_meas` check a global integer `cpu_meas_enabled`. If disabled, they are virtually free, but when enabled, each probe incurs system call overhead (`clock_gettime`) plus arithmetic operations.
  - On ARM64 platforms, reading the virtual counter `cntvct_el0` runs at fixed frequency (typically 19.2 MHz to 24 MHz on standard ARM cores), whereas x86 `rdtsc` runs at CPU core nominal frequency.

### 2. Tracy Profiler Instrumentation (`common/instrumentation.h`)
- Controlled via compile-time flag `-DTRACY_ENABLE=ON`.
- Wraps `tracy/TracyC.h`:
  - `TracyCZone(ctx, true)` / `TracyCZoneEnd(ctx)`
  - `TracyCFrameMark`
  - `TracyCPlot(name, val)`
- **Gap**: Completely missing in Layer 2 (RLC, PDCP, MAC) and Layer 3 (RRC, F1AP, E1AP, NGAP). Adding Tracy zones to Layer 2 will give real-time timeline visualization of per-packet processing and scheduler locks.

### 3. Layer 2 Test Infrastructure
- **NR RLC**:
  - `openair2/LAYER2/nr_rlc/tests/benchmark_nr_rlc_am_entity.cpp` already uses Google Benchmark. It provides an excellent template that can be expanded to test both AM and UM entities under various SDU sizes.
- **NR PDCP**:
  - `openair2/LAYER2/nr_pdcp/tests/snow3g_tests.c` tests Snow3G, but no benchmark exists measuring megabytes/second or cycles/byte across 128-bit vs 256-bit keys, or AES vs Snow3G vs ZUC.
- **MAC Scheduler**:
  - `tests/nrdlbench/dlbench.c` is an existing standalone benchmark for gNB DL scheduling + PHY TX. It accepts `-u <num_ues>`, `-n <num_slots>`, `-R <prb>`, and `-P` (print perf). This executable is the ideal vehicle for deliverable 3.

### 4. Layer 3 ASN.1 Round-Trip Infrastructure
- All 4 protocols (F1AP, E1AP, NGAP, NR RRC) have unit test files that instantiate message structs, encode them to buffer using `aper_encode_to_buffer` (or `do_SIB2_NR` / `uper_encode`), and decode them using `aper_decode` / `uper_decode`.
- These tests currently assert `dec.code == RC_OK` and immediately exit. Wrapping these routines in an iteration loop with high-resolution timers yields a ready-made L3 characterisation suite without needing full gNB/UE protocol state machines.

### 5. CPU Isolation and System Tuning Documentation
- `doc/tuning_and_security.md` recommends `cpupower idle-set -D0` to disable sleep states and `mitigations=off nosmt` to disable hyperthreading and speculative execution mitigations.
- `doc/ORAN_FHI7.2_Tutorial.md` provides concrete GRUB command line examples:
  - `isolcpus=domain,4-31` (isolates cores from general Linux scheduler)
  - `nohz_full=4-31` (disables kernel scheduler ticks on isolated cores)
  - `irqaffinity=0,1,2,3` (routes hardware interrupts away from isolated cores)
  - `rcu_nocbs=4-31` (offloads RCU callbacks to non-isolated housekeeping cores)
- **Gap**: No automated harness check to verify whether these settings are active before benchmarks run.
