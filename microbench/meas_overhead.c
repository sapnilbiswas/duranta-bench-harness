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
 * Uses N iterations (default 1,000,000) and reports min, median, p99, and max.
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

/* Architecture-specific CPU tick counter */
#if defined(__x86_64__) || defined(__i386__)
#define HAS_CPU_TICKS 1
static inline uint64_t read_cpu_ticks(void)
{
    unsigned int lo, hi;
    __asm__ volatile ("rdtsc" : "=a" (lo), "=d" (hi));
    return ((uint64_t)hi << 32) | lo;
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
static const char *TICK_SRC_NAME = "ARM64 cntvct_el0";
#else
#define HAS_CPU_TICKS 0
static inline uint64_t read_cpu_ticks(void)
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

typedef struct {
    uint64_t count;
    uint64_t min;
    uint64_t median;
    uint64_t p99;
    uint64_t max;
} stats_result_t;

static stats_result_t calculate_stats(uint64_t *samples, size_t n)
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

int main(int argc, char **argv)
{
    size_t iterations = 1000000;
    if (argc > 1) {
        long val = atol(argv[1]);
        if (val > 1000) {
            iterations = (size_t)val;
        }
    }

    uint64_t *samples = (uint64_t *)malloc(iterations * sizeof(uint64_t));
    if (!samples) {
        fprintf(stderr, "Failed to allocate memory for samples\n");
        return 1;
    }

    printf("Running probe-overhead microbenchmark (%zu iterations)...\n", iterations);

    /* 1. Baseline: Empty loop measurement */
    for (size_t i = 0; i < iterations; i++) {
        uint64_t t0 = get_ns_monotonic();
        __asm__ volatile ("" : : : "memory");
        uint64_t t1 = get_ns_monotonic();
        samples[i] = (t1 >= t0) ? (t1 - t0) : 0;
    }
    stats_result_t baseline_stats = calculate_stats(samples, iterations);

    /* 2. Bare clock_gettime(CLOCK_MONOTONIC) pair */
    for (size_t i = 0; i < iterations; i++) {
        struct timespec t0, t1;
        clock_gettime(CLOCK_MONOTONIC, &t0);
        clock_gettime(CLOCK_MONOTONIC, &t1);
        uint64_t diff = ((uint64_t)t1.tv_sec * 1000000000ULL + (uint64_t)t1.tv_nsec) -
                        ((uint64_t)t0.tv_sec * 1000000000ULL + (uint64_t)t0.tv_nsec);
        samples[i] = diff;
    }
    stats_result_t monotonic_stats = calculate_stats(samples, iterations);

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
    stats_result_t monotonic_raw_stats = calculate_stats(samples, iterations);
#endif

    /* 4. OAI time_meas pair: start_meas / stop_meas */
    time_stats_t ts;
    memset(&ts, 0, sizeof(ts));
    for (size_t i = 0; i < iterations; i++) {
        start_meas(&ts);
        stop_meas(&ts);
        samples[i] = (uint64_t)ts.p_time;
    }
    stats_result_t time_meas_stats = calculate_stats(samples, iterations);

    /* 5. CPU tick pair (arch guarded) */
#if HAS_CPU_TICKS
    for (size_t i = 0; i < iterations; i++) {
        uint64_t tick0 = read_cpu_ticks();
        uint64_t tick1 = read_cpu_ticks();
        samples[i] = (tick1 >= tick0) ? (tick1 - tick0) : 0;
    }
    stats_result_t tick_stats = calculate_stats(samples, iterations);
#endif

    free(samples);

    /* Output Results in Human Readable Table */
    printf("\n%-40s | %10s | %10s | %10s | %10s\n", "Benchmark Target", "Min", "Median", "p99", "Max");
    printf("-----------------------------------------+------------+------------+------------+------------\n");
    printf("%-40s | %8" PRIu64 " ns | %8" PRIu64 " ns | %8" PRIu64 " ns | %8" PRIu64 " ns\n",
           "Empty loop (measurement floor)", baseline_stats.min, baseline_stats.median, baseline_stats.p99, baseline_stats.max);
    printf("%-40s | %8" PRIu64 " ns | %8" PRIu64 " ns | %8" PRIu64 " ns | %8" PRIu64 " ns\n",
           "clock_gettime(CLOCK_MONOTONIC)", monotonic_stats.min, monotonic_stats.median, monotonic_stats.p99, monotonic_stats.max);
#ifdef CLOCK_MONOTONIC_RAW
    printf("%-40s | %8" PRIu64 " ns | %8" PRIu64 " ns | %8" PRIu64 " ns | %8" PRIu64 " ns\n",
           "clock_gettime(CLOCK_MONOTONIC_RAW)", monotonic_raw_stats.min, monotonic_raw_stats.median, monotonic_raw_stats.p99, monotonic_raw_stats.max);
#endif
    printf("%-40s | %8" PRIu64 " ns | %8" PRIu64 " ns | %8" PRIu64 " ns | %8" PRIu64 " ns\n",
           "OAI time_meas (start/stop pair)", time_meas_stats.min, time_meas_stats.median, time_meas_stats.p99, time_meas_stats.max);
#if HAS_CPU_TICKS
    char tick_label[64];
    snprintf(tick_label, sizeof(tick_label), "CPU tick counter (%s)", TICK_SRC_NAME);
    printf("%-40s | %7" PRIu64 " tick | %7" PRIu64 " tick | %7" PRIu64 " tick | %7" PRIu64 " tick\n",
           tick_label, tick_stats.min, tick_stats.median, tick_stats.p99, tick_stats.max);
#endif

    /* Output JSON representation */
    printf("\n=== JSON RESULTS ===\n");
    printf("{\n");
    printf("  \"iterations\": %zu,\n", iterations);
    printf("  \"results\": {\n");
    printf("    \"empty_loop_ns\": {\"min\": %" PRIu64 ", \"median\": %" PRIu64 ", \"p99\": %" PRIu64 ", \"max\": %" PRIu64 "},\n",
           baseline_stats.min, baseline_stats.median, baseline_stats.p99, baseline_stats.max);
    printf("    \"clock_monotonic_ns\": {\"min\": %" PRIu64 ", \"median\": %" PRIu64 ", \"p99\": %" PRIu64 ", \"max\": %" PRIu64 "},\n",
           monotonic_stats.min, monotonic_stats.median, monotonic_stats.p99, monotonic_stats.max);
#ifdef CLOCK_MONOTONIC_RAW
    printf("    \"clock_monotonic_raw_ns\": {\"min\": %" PRIu64 ", \"median\": %" PRIu64 ", \"p99\": %" PRIu64 ", \"max\": %" PRIu64 "},\n",
           monotonic_raw_stats.min, monotonic_raw_stats.median, monotonic_raw_stats.p99, monotonic_raw_stats.max);
#endif
    printf("    \"oai_time_meas_ns\": {\"min\": %" PRIu64 ", \"median\": %" PRIu64 ", \"p99\": %" PRIu64 ", \"max\": %" PRIu64 "}%s\n",
           time_meas_stats.min, time_meas_stats.median, time_meas_stats.p99, time_meas_stats.max,
#if HAS_CPU_TICKS
           ","
#else
           ""
#endif
    );
#if HAS_CPU_TICKS
    printf("    \"cpu_ticks\": {\"source\": \"%s\", \"min\": %" PRIu64 ", \"median\": %" PRIu64 ", \"p99\": %" PRIu64 ", \"max\": %" PRIu64 "}\n",
           TICK_SRC_NAME, tick_stats.min, tick_stats.median, tick_stats.p99, tick_stats.max);
#endif
    printf("  }\n");
    printf("}\n");

    return 0;
}
