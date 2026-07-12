/*
 * bench_port.h  --  benchmark harness platform layer (ESP-IDF).
 *
 * Copyright (c) 2026 SeekAudio.  All rights reserved.
 *
 * The subset of platform services the benchmark harness needs:
 *   - a monotonic microsecond clock (compute-time profiling),
 *   - heap / stack introspection (black-box footprint measurement),
 *   - logging,
 *   - a cooperative yield (keeps idle / watchdog tasks alive during the
 *     flat-out batch loop).
 *
 * Everything here observes the system from the OUTSIDE of the AEC library;
 * nothing depends on library internals, so the same harness measures the
 * SeekAudio prebuilt .a and the Espressif esp-sr backends identically.
 */
#ifndef BENCH_PORT_H
#define BENCH_PORT_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Monotonic time in microseconds. Callers must exclude file I/O themselves. */
int64_t bench_time_us(void);

/* Current free heap split by capability:
 *   *internal = free internal (on-chip) SRAM bytes (MALLOC_CAP_INTERNAL)
 *   *spiram   = free PSRAM bytes                   (MALLOC_CAP_SPIRAM)
 * Snapshot before/after a phase; (before - after) is what that phase consumed,
 * regardless of which allocator it used. This is the black-box replacement for
 * allocator-side accounting: it needs no cooperation from the library. */
void bench_heap_free(size_t *internal, size_t *spiram);

/* Minimum free stack of the current task ever seen, in bytes. */
size_t bench_min_free_stack(void);

/* Logging (ESP_LOGx). */
void bench_log_info(const char *tag, const char *fmt, ...);
void bench_log_warn(const char *tag, const char *fmt, ...);
void bench_log_error(const char *tag, const char *fmt, ...);

/* Cooperative yield (vTaskDelay(1)); call outside any timed region. */
void bench_yield(void);

#ifdef __cplusplus
}
#endif

#endif /* BENCH_PORT_H */
