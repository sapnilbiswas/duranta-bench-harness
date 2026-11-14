/*
 * meas_overhead.c - Probe-overhead microbenchmark
 *
 * Measures the execution cost of:
 * 1. Empty loop baseline
 * 2. Bare clock_gettime(CLOCK_MONOTONIC) start/stop pair
 * 3. Bare clock_gettime(CLOCK_MONOTONIC_RAW) start/stop pair
 * 4. OAI time_meas start_meas() / stop_meas() pair
 * 5. Architecture-native CPU tick counter pair (rdtsc on x86, cntvct_el0 on ARM64)
 *
 * Supports BOTH:
 * - Single-call timing (1M samples): reveals hardware timer quantization floor.
 * - Batched timing (1,000 batches x 1,000 ops): provides sub-nanosecond amortized cost.
 *
 * Report numbers only; no design judgements.
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <inttypes.h>
#include <time.h>
#include <string.h>

#include "time_meas.h"

int cpu_meas_enabled = 1;

/* Stub required when time_stats_sorted_list is disabled in time_stats_t */
void insert_in_time_stats_sorted_list(time_stats_sorted_list_t *list, oai_cputime_t time)
{
    (void)list;
    (void)time;
}

static inline uint64_t get_ns_monotonic(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

#ifdef CLOCK_MONOTONIC_RAW
static inline uint64_t get_ns_monotonic_raw(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}
#endif

/* Architecture-specific CPU tick counter and frequency */
#if defined(__x86_64__) || defined(__i386__)
#define HAS_CPU_TICKS 1
static inline uint64_t read_cpu_ticks(void)
{
    unsigned int lo, hi;
    __asm__ volatile ("rdtsc" : "=a" (lo), "=d" (hi));
    return ((uint64_t)hi << 32) | lo;
}
static inline uint64_t read_counter_freq(void)
{
    return 0; /* Variable or TSC nominal */
}
static const char *TICK_SRC_NAME = "x86 rdtsc";
#elif defined(__aarch64__)
#define HAS_CPU_TICKS 1
static inline uint64_t read_cpu_ticks(void)
{
    uint64_t val;
    __asm__ volatile("mrs %0, cntvct_el0" : "=r"(val));
    return val;
}
static inline uint64_t read_counter_freq(void)
{
    uint64_t frq = 0;
    __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(frq));
    return frq;
}
static const char *TICK_SRC_NAME = "ARM64 cntvct_el0";
#else
#define HAS_CPU_TICKS 0
static inline uint64_t read_cpu_ticks(void)
{
    return 0;
}
static inline uint64_t read_counter_freq(void)
{
    return 0;
}
static const char *TICK_SRC_NAME = "unsupported arch";
#endif

static int compare_u64(const void *a, const void *b)
{
    uint64_t arg1 = *(const uint64_t *)a;
    uint64_t arg2 = *(const uint64_t *)b;
    if (arg1 < arg2) return -1;
    if (arg1 > arg2) return 1;
    return 0;
}

static int compare_double(const void *a, const void *b)
{
    double arg1 = *(const double *)a;
    double arg2 = *(const double *)b;
    if (arg1 < arg2) return -1;
    if (arg1 > arg2) return 1;
    return 0;
}

typedef struct {
    uint64_t count;
    uint64_t min;
    uint64_t median;
    uint64_t p99;
    uint64_t max;
} stats_result_t;

typedef struct {
    size_t count;
    double min;
    double median;
    double p99;
    double max;
} batch_stats_result_t;

static stats_result_t calculate_stats_u64(uint64_t *samples, size_t n)
{
    stats_result_t r;
    r.count = (uint64_t)n;
    if (n == 0) {
        memset(&r, 0, sizeof(r));
        return r;
    }
    qsort(samples, n, sizeof(uint64_t), compare_u64);
    r.min = samples[0];
    r.median = samples[n / 2];
    r.p99 = samples[(size_t)((double)n * 0.99)];
    r.max = samples[n - 1];
    return r;
}

static batch_stats_result_t calculate_stats_double(double *samples, size_t n)
{
    batch_stats_result_t r;
    r.count = n;
    if (n == 0) {
        memset(&r, 0, sizeof(r));
        return r;
    }
    qsort(samples, n, sizeof(double), compare_double);
    r.min = samples[0];
    r.median = samples[n / 2];
    r.p99 = samples[(size_t)((double)n * 0.99)];
    r.max = samples[n - 1];
    return r;
}

int main(int argc, char **argv)
{
    size_t iterations = 1000000;
    if (argc > 1) {
        long val = atol(argv[1]);
        if (val > 1000) {
            iterations = (size_t)val;
        }
    }

    uint64_t counter_freq = read_counter_freq();
    double tick_resolution_ns = (counter_freq > 0) ? (1e9 / (double)counter_freq) : 0.0;

    printf("================================================================================\n");
    printf("Duranta-OAI Probe-Overhead Microbenchmark\n");
    printf("Total Iterations: %zu\n", iterations);
    if (counter_freq > 0) {
        printf("Hardware Counter Frequency (%s): %" PRIu64 " Hz (%.2f MHz)\n", TICK_SRC_NAME, counter_freq, counter_freq / 1e6);
        printf("Hardware Tick Resolution Floor: %.2f ns\n", tick_resolution_ns);
    }
    printf("================================================================================\n\n");

    /* ========================================================================
     * PART 1: Single-call timing (Direct unbatched measurement)
     * Demonstrates clock resolution quantization.
     * ======================================================================== */
    uint64_t *samples = (uint64_t *)malloc(iterations * sizeof(uint64_t));
    if (!samples) {
        fprintf(stderr, "Failed to allocate memory for single-call samples\n");
        return 1;
    }

    /* 1. Empty loop baseline */
    for (size_t i = 0; i < iterations; i++) {
        uint64_t t0 = get_ns_monotonic();
        __asm__ volatile ("" : : : "memory");
        uint64_t t1 = get_ns_monotonic();
        samples[i] = (t1 >= t0) ? (t1 - t0) : 0;
    }
    stats_result_t sc_baseline = calculate_stats_u64(samples, iterations);

    /* 2. Bare clock_gettime(CLOCK_MONOTONIC) pair */
    for (size_t i = 0; i < iterations; i++) {
        struct timespec t0, t1;
        clock_gettime(CLOCK_MONOTONIC, &t0);
        clock_gettime(CLOCK_MONOTONIC, &t1);
        uint64_t diff = ((uint64_t)t1.tv_sec * 1000000000ULL + (uint64_t)t1.tv_nsec) -
                        ((uint64_t)t0.tv_sec * 1000000000ULL + (uint64_t)t0.tv_nsec);
        samples[i] = diff;
    }
    stats_result_t sc_monotonic = calculate_stats_u64(samples, iterations);

    /* 3. Bare clock_gettime(CLOCK_MONOTONIC_RAW) pair */
#ifdef CLOCK_MONOTONIC_RAW
    for (size_t i = 0; i < iterations; i++) {
        struct timespec t0, t1;
        clock_gettime(CLOCK_MONOTONIC_RAW, &t0);
        clock_gettime(CLOCK_MONOTONIC_RAW, &t1);
        uint64_t diff = ((uint64_t)t1.tv_sec * 1000000000ULL + (uint64_t)t1.tv_nsec) -
                        ((uint64_t)t0.tv_sec * 1000000000ULL + (uint64_t)t0.tv_nsec);
        samples[i] = diff;
    }
    stats_result_t sc_monotonic_raw = calculate_stats_u64(samples, iterations);
#endif

    /* 4. OAI time_meas start_meas / stop_meas pair */
    time_stats_t ts;
    memset(&ts, 0, sizeof(ts));
    for (size_t i = 0; i < iterations; i++) {
        start_meas(&ts);
        stop_meas(&ts);
        samples[i] = (uint64_t)ts.p_time;
    }
    stats_result_t sc_time_meas = calculate_stats_u64(samples, iterations);

    /* 5. CPU tick pair */
#if HAS_CPU_TICKS
    for (size_t i = 0; i < iterations; i++) {
        uint64_t tick0 = read_cpu_ticks();
        uint64_t tick1 = read_cpu_ticks();
        samples[i] = (tick1 >= tick0) ? (tick1 - tick0) : 0;
    }
    stats_result_t sc_ticks = calculate_stats_u64(samples, iterations);
#endif
    free(samples);

    /* ========================================================================
     * PART 2: Batched timing (1,000 batches of 1,000 ops = 1M operations)
     * Overcomes clock quantization to reveal sub-nanosecond amortized cost.
     * ======================================================================== */
    size_t batch_size = 1000;
    size_t batch_count = (iterations >= batch_size) ? (iterations / batch_size) : 1000;
    double *b_samples = (double *)malloc(batch_count * sizeof(double));
    if (!b_samples) {
        fprintf(stderr, "Failed to allocate memory for batch samples\n");
        return 1;
    }

    /* 1. Empty loop */
    for (size_t b = 0; b < batch_count; b++) {
        uint64_t t0 = get_ns_monotonic();
        for (size_t k = 0; k < batch_size; k++) {
            __asm__ volatile ("" : : : "memory");
        }
        uint64_t t1 = get_ns_monotonic();
        b_samples[b] = (double)(t1 - t0) / (double)batch_size;
    }
    batch_stats_result_t b_baseline = calculate_stats_double(b_samples, batch_count);

    /* 2. Bare clock_gettime(CLOCK_MONOTONIC) */
    for (size_t b = 0; b < batch_count; b++) {
        struct timespec d;
        uint64_t t0 = get_ns_monotonic();
        for (size_t k = 0; k < batch_size; k++) {
            clock_gettime(CLOCK_MONOTONIC, &d);
        }
        uint64_t t1 = get_ns_monotonic();
        b_samples[b] = (double)(t1 - t0) / (double)batch_size;
    }
    batch_stats_result_t b_monotonic = calculate_stats_double(b_samples, batch_count);

    /* 3. Bare clock_gettime(CLOCK_MONOTONIC_RAW) */
#ifdef CLOCK_MONOTONIC_RAW
    for (size_t b = 0; b < batch_count; b++) {
        struct timespec d;
        uint64_t t0 = get_ns_monotonic();
        for (size_t k = 0; k < batch_size; k++) {
            clock_gettime(CLOCK_MONOTONIC_RAW, &d);
        }
        uint64_t t1 = get_ns_monotonic();
        b_samples[b] = (double)(t1 - t0) / (double)batch_size;
    }
    batch_stats_result_t b_monotonic_raw = calculate_stats_double(b_samples, batch_count);
#endif

    /* 4. OAI time_meas start_meas / stop_meas pair */
    memset(&ts, 0, sizeof(ts));
    for (size_t b = 0; b < batch_count; b++) {
        uint64_t t0 = get_ns_monotonic();
        for (size_t k = 0; k < batch_size; k++) {
            start_meas(&ts);
            stop_meas(&ts);
        }
        uint64_t t1 = get_ns_monotonic();
        b_samples[b] = (double)(t1 - t0) / (double)batch_size;
    }
    batch_stats_result_t b_time_meas = calculate_stats_double(b_samples, batch_count);

    /* 5. CPU ticks per read */
#if HAS_CPU_TICKS
    for (size_t b = 0; b < batch_count; b++) {
        uint64_t t0 = get_ns_monotonic();
        for (size_t k = 0; k < batch_size; k++) {
            volatile uint64_t v = read_cpu_ticks();
            (void)v;
        }
        uint64_t t1 = get_ns_monotonic();
        b_samples[b] = (double)(t1 - t0) / (double)batch_size;
    }
    batch_stats_result_t b_ticks = calculate_stats_double(b_samples, batch_count);
#endif
    free(b_samples);

    /* Print Formatted Tables */
    printf("--- 1. Single-Call Unbatched Results (Direct Measurement, Subject to Timer Quantization) ---\n");
    printf("%-40s | %10s | %10s | %10s | %10s\n", "Target", "Min", "Median", "p99", "Max");
    printf("-----------------------------------------+------------+------------+------------+------------\n");
    printf("%-40s | %8" PRIu64 " ns | %8" PRIu64 " ns | %8" PRIu64 " ns | %8" PRIu64 " ns\n",
           "Empty loop (baseline)", sc_baseline.min, sc_baseline.median, sc_baseline.p99, sc_baseline.max);
    printf("%-40s | %8" PRIu64 " ns | %8" PRIu64 " ns | %8" PRIu64 " ns | %8" PRIu64 " ns\n",
           "clock_gettime(CLOCK_MONOTONIC)", sc_monotonic.min, sc_monotonic.median, sc_monotonic.p99, sc_monotonic.max);
#ifdef CLOCK_MONOTONIC_RAW
    printf("%-40s | %8" PRIu64 " ns | %8" PRIu64 " ns | %8" PRIu64 " ns | %8" PRIu64 " ns\n",
           "clock_gettime(CLOCK_MONOTONIC_RAW)", sc_monotonic_raw.min, sc_monotonic_raw.median, sc_monotonic_raw.p99, sc_monotonic_raw.max);
#endif
    printf("%-40s | %8" PRIu64 " ns | %8" PRIu64 " ns | %8" PRIu64 " ns | %8" PRIu64 " ns\n",
           "OAI time_meas (start/stop pair)", sc_time_meas.min, sc_time_meas.median, sc_time_meas.p99, sc_time_meas.max);
#if HAS_CPU_TICKS
    char tick_label[64];
    snprintf(tick_label, sizeof(tick_label), "CPU tick counter (%s)", TICK_SRC_NAME);
    printf("%-40s | %7" PRIu64 " tick | %7" PRIu64 " tick | %7" PRIu64 " tick | %7" PRIu64 " tick\n",
           tick_label, sc_ticks.min, sc_ticks.median, sc_ticks.p99, sc_ticks.max);
#endif

    printf("\n--- 2. Batched Timing Results (Amortized per Operation across %zu Batches of %zu Ops) ---\n",
           batch_count, batch_size);
    printf("%-40s | %10s | %10s | %10s | %10s\n", "Target", "Min", "Median", "p99", "Max");
    printf("-----------------------------------------+------------+------------+------------+------------\n");
    printf("%-40s | %7.2f ns | %7.2f ns | %7.2f ns | %7.2f ns\n",
           "Empty loop (baseline)", b_baseline.min, b_baseline.median, b_baseline.p99, b_baseline.max);
    printf("%-40s | %7.2f ns | %7.2f ns | %7.2f ns | %7.2f ns\n",
           "clock_gettime(CLOCK_MONOTONIC)", b_monotonic.min, b_monotonic.median, b_monotonic.p99, b_monotonic.max);
#ifdef CLOCK_MONOTONIC_RAW
    printf("%-40s | %7.2f ns | %7.2f ns | %7.2f ns | %7.2f ns\n",
           "clock_gettime(CLOCK_MONOTONIC_RAW)", b_monotonic_raw.min, b_monotonic_raw.median, b_monotonic_raw.p99, b_monotonic_raw.max);
#endif
    printf("%-40s | %7.2f ns | %7.2f ns | %7.2f ns | %7.2f ns\n",
           "OAI time_meas (start/stop pair)", b_time_meas.min, b_time_meas.median, b_time_meas.p99, b_time_meas.max);
#if HAS_CPU_TICKS
    printf("%-40s | %7.2f ns | %7.2f ns | %7.2f ns | %7.2f ns\n",
           tick_label, b_ticks.min, b_ticks.median, b_ticks.p99, b_ticks.max);
#endif

    /* Output JSON representation */
    printf("\n=== JSON RESULTS ===\n");
    printf("{\n");
    printf("  \"total_iterations\": %zu,\n", iterations);
    printf("  \"counter_frequency_hz\": %" PRIu64 ",\n", counter_freq);
    printf("  \"counter_resolution_ns\": %.2f,\n", tick_resolution_ns);
    printf("  \"single_call_unbatched\": {\n");
    printf("    \"empty_loop_ns\": {\"min\": %" PRIu64 ", \"median\": %" PRIu64 ", \"p99\": %" PRIu64 ", \"max\": %" PRIu64 "},\n",
           sc_baseline.min, sc_baseline.median, sc_baseline.p99, sc_baseline.max);
    printf("    \"clock_monotonic_ns\": {\"min\": %" PRIu64 ", \"median\": %" PRIu64 ", \"p99\": %" PRIu64 ", \"max\": %" PRIu64 "},\n",
           sc_monotonic.min, sc_monotonic.median, sc_monotonic.p99, sc_monotonic.max);
#ifdef CLOCK_MONOTONIC_RAW
    printf("    \"clock_monotonic_raw_ns\": {\"min\": %" PRIu64 ", \"median\": %" PRIu64 ", \"p99\": %" PRIu64 ", \"max\": %" PRIu64 "},\n",
           sc_monotonic_raw.min, sc_monotonic_raw.median, sc_monotonic_raw.p99, sc_monotonic_raw.max);
#endif
    printf("    \"oai_time_meas_ns\": {\"min\": %" PRIu64 ", \"median\": %" PRIu64 ", \"p99\": %" PRIu64 ", \"max\": %" PRIu64 "}\n",
           sc_time_meas.min, sc_time_meas.median, sc_time_meas.p99, sc_time_meas.max);
    printf("  },\n");
    printf("  \"batched_amortized\": {\n");
    printf("    \"batch_size\": %zu,\n", batch_size);
    printf("    \"batch_count\": %zu,\n", batch_count);
    printf("    \"empty_loop_ns\": {\"min\": %.2f, \"median\": %.2f, \"p99\": %.2f, \"max\": %.2f},\n",
           b_baseline.min, b_baseline.median, b_baseline.p99, b_baseline.max);
    printf("    \"clock_monotonic_ns\": {\"min\": %.2f, \"median\": %.2f, \"p99\": %.2f, \"max\": %.2f},\n",
           b_monotonic.min, b_monotonic.median, b_monotonic.p99, b_monotonic.max);
#ifdef CLOCK_MONOTONIC_RAW
    printf("    \"clock_monotonic_raw_ns\": {\"min\": %.2f, \"median\": %.2f, \"p99\": %.2f, \"max\": %.2f},\n",
           b_monotonic_raw.min, b_monotonic_raw.median, b_monotonic_raw.p99, b_monotonic_raw.max);
#endif
    printf("    \"oai_time_meas_ns\": {\"min\": %.2f, \"median\": %.2f, \"p99\": %.2f, \"max\": %.2f}\n",
           b_time_meas.min, b_time_meas.median, b_time_meas.p99, b_time_meas.max);
    printf("  }\n");
    printf("}\n");

    return 0;
}
