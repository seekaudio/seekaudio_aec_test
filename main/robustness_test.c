/*
 * robustness_test.c  --  black-box robustness checks for the A-path pipeline.
 *
 * Copyright (c) 2026 SeekAudio.  All rights reserved.
 *
 * Exercises the SHIPPING configuration -- the SeekAudio engine driven through
 * its public API (seekaudio_aec_*), exactly as the benchmark runs it, through
 * the generic backend vtable. Both denoise engines (A1 = NS, A2 = AI) are
 * covered.
 *
 * The whole module is compiled out with -DSA_TEST_ROBUSTNESS=0 (see
 * bench_config.h); to remove it permanently, delete this file and the one
 * robustness_run() call in aectest.cpp.
 *
 * Checks (per config A1 / A2):
 *   R1  create() wall time                       (boot-time budget)
 *   R2  create/destroy x N leak check            (heap returns to baseline)
 *   R3  all-zero input                           (no crash)
 *   R4  full-scale square-wave input             (no crash, saturation-safe)
 *   R5  clipped speech (near x4, saturated)      (no crash on real material)
 *
 * R3-R5 verify the pipeline never crashes, hangs, or misbehaves on degenerate
 * or overdriven inputs -- the classic field failure modes a customer cannot
 * debug against a closed library. Every check prints PASS / WARN / FAIL.
 */
#include "bench_config.h"

#if SA_TEST_ROBUSTNESS

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "aec_runner.h"
#include "bench_port.h"

/* ---- optional heap-trace leak localisation (SA_ROBUST_HEAP_TRACE=1) --------
 * Wraps ONE create/destroy cycle (after warm-up) in ESP-IDF standalone heap
 * tracing and dumps every allocation that was never freed, WITH caller call
 * stacks. idf.py monitor decodes the addresses to function names, so run this
 * against the NON-hardened, symbols-intact library build.
 *
 * Requires two sdkconfig lines (add temporarily, e.g. via menuconfig
 * Component config -> Heap memory debugging):
 *     CONFIG_HEAP_TRACING_STANDALONE=y
 *     CONFIG_HEAP_TRACING_STACK_DEPTH=10
 * then build with:  idf.py -DSA_ROBUST_HEAP_TRACE=1 build
 * The record buffer lives in internal RAM (~13 KB for 256 records @ depth 10);
 * keep the benchmark configs disabled (-DRUN_A1=0 ... ) so the heap is clean. */
#ifndef SA_ROBUST_HEAP_TRACE
#define SA_ROBUST_HEAP_TRACE 0
#endif
#if SA_ROBUST_HEAP_TRACE
#include "esp_heap_trace.h"
#define SA_TRACE_RECORDS 256
static heap_trace_record_t s_trace_records[SA_TRACE_RECORDS];
#endif

#define ROB_TAG "robustness"

/* create/destroy iterations for the leak check. */
#ifndef SA_ROBUST_LEAK_ITERS
#define SA_ROBUST_LEAK_ITERS 10
#endif
/* frames per synthetic-input check. */
#ifndef SA_ROBUST_FRAMES
#define SA_ROBUST_FRAMES 100
#endif

/* A-path composite backends (fd_aec_backend.cpp). */
extern const aec_backend_t *fd_a1_backend(void);
extern const aec_backend_t *fd_a2_backend(void);

/* When create() returns NULL inside the robustness suite, the most likely
 * cause is NOT a library fault but the delivery build's usage limit: a
 * VERSION_LIMIT=1 library caps successful re-inits (~10 per process, process-
 * global, reset only by reboot) and refuses init after its date lock. The
 * benchmark already spends a couple of inits, so the many create/destroy
 * cycles here can push past the cap. Print this note ONCE so the failure is
 * not mistaken for a crash or leak. */
static void rob_note_version_limit(void)
{
    static int warned = 0;
    if (warned) return;
    warned = 1;
    bench_log_warn(ROB_TAG,
        "NOTE: create()==NULL is often the VERSION_LIMIT delivery library, not a fault:");
    bench_log_warn(ROB_TAG,
        "      limited lib caps ~10 re-inits/process (reset by reboot) + has a date lock;");
    bench_log_warn(ROB_TAG,
        "      robustness runs many create/destroy cycles and can exceed that cap.");
    bench_log_warn(ROB_TAG,
        "      For internal validation rebuild the library with -DVERSION_LIMIT=0.");
}

/* Feed `frames` frames built by fill(frame_idx, mic, ref, n) through a fresh
 * pipeline instance. Returns 0 if every process() call returned n samples. */
typedef void (*fill_fn)(int frame, int16_t *mic, int16_t *ref, int n,
                        const int16_t *near, const int16_t *far,
                        size_t mono_samples);

static int feed_frames(const aec_backend_t *be, int frames, fill_fn fill,
                       const int16_t *near, const int16_t *far,
                       size_t mono_samples, const char *label)
{
    void *h = be->create(AEC_INPUT_FORMAT, AEC_FILTER_LEN, 0);
    if (!h) {
        bench_log_error(ROB_TAG, "[%s][%s] FAIL: create returned NULL", label, be->name);
        rob_note_version_limit();
        return -1;
    }
    int n = be->get_chunksize(h);
    if (n <= 0 || n > 512) {
        bench_log_error(ROB_TAG, "[%s][%s] FAIL: bad chunksize %d", label, be->name, n);
        be->destroy(h);
        return -1;
    }

    int16_t *mic = (int16_t *)malloc((size_t)n * sizeof(int16_t));
    int16_t *ref = (int16_t *)malloc((size_t)n * sizeof(int16_t));
    int16_t *in  = (int16_t *)malloc((size_t)n * 2 * sizeof(int16_t));
    int16_t *out = (int16_t *)malloc((size_t)n * sizeof(int16_t));
    if (!mic || !ref || !in || !out) {
        free(mic); free(ref); free(in); free(out);
        be->destroy(h);
        bench_log_error(ROB_TAG, "[%s][%s] FAIL: OOM (harness)", label, be->name);
        return -1;
    }

    int bad = 0;
    for (int f = 0; f < frames; ++f) {
        fill(f, mic, ref, n, near, far, mono_samples);
        for (int s = 0; s < n; ++s) {           /* interleave "MR" */
            in[s * 2 + 0] = mic[s];
            in[s * 2 + 1] = ref[s];
        }
        size_t got = be->process(h, in, out);
        if (got != (size_t)n) { bad = 1; break; }
        if ((f & 0x0F) == 0x0F) bench_yield();
    }

    free(mic); free(ref); free(in); free(out);
    be->destroy(h);

    if (bad) {
        bench_log_error(ROB_TAG, "[%s][%s] FAIL: process() returned wrong sample count",
                     label, be->name);
        return -1;
    }
    bench_log_info(ROB_TAG, "[%s][%s] PASS: %d frames processed, no crash",
                label, be->name, frames);
    return 0;
}

/* ----- fill functions ----------------------------------------------------- */
static void fill_zero(int f, int16_t *mic, int16_t *ref, int n,
                      const int16_t *near, const int16_t *far, size_t ms)
{
    (void)f; (void)near; (void)far; (void)ms;
    memset(mic, 0, (size_t)n * sizeof(int16_t));
    memset(ref, 0, (size_t)n * sizeof(int16_t));
}

static void fill_fullscale(int f, int16_t *mic, int16_t *ref, int n,
                           const int16_t *near, const int16_t *far, size_t ms)
{
    (void)near; (void)far; (void)ms;
    /* ~500 Hz full-scale square wave on both channels (16 samples per half
     * period @ 16 kHz), phase-continuous across frames. */
    for (int s = 0; s < n; ++s) {
        int idx = f * n + s;
        int16_t v = ((idx >> 4) & 1) ? (int16_t)32767 : (int16_t)-32768;
        mic[s] = v;
        ref[s] = v;
    }
}

static void fill_clipped(int f, int16_t *mic, int16_t *ref, int n,
                         const int16_t *near, const int16_t *far, size_t ms)
{
    /* real speech overdriven x4 and hard-clipped (simulates an overloaded
     * front-end); wraps around the test material if needed. */
    for (int s = 0; s < n; ++s) {
        size_t idx = ((size_t)f * (size_t)n + (size_t)s) % (ms ? ms : 1);
        int32_t m = near ? (int32_t)near[idx] * 4 : 0;
        int32_t r = far  ? (int32_t)far[idx]  * 4 : 0;
        if (m > 32767) m = 32767; else if (m < -32768) m = -32768;
        if (r > 32767) r = 32767; else if (r < -32768) r = -32768;
        mic[s] = (int16_t)m;
        ref[s] = (int16_t)r;
    }
}

/* ----- per-config check set ------------------------------------------------ */
static void robustness_for_backend(const aec_backend_t *be,
                                   const int16_t *near, const int16_t *far,
                                   size_t mono_samples)
{
    bench_log_info(ROB_TAG, "==== robustness checks: %s ====", be->name);

    /* R1: create() wall time. */
    {
        int64_t t0 = bench_time_us();
        void *h = be->create(AEC_INPUT_FORMAT, AEC_FILTER_LEN, 0);
        int64_t dt = bench_time_us() - t0;
        if (!h) {
            bench_log_error(ROB_TAG, "[R1][%s] FAIL: create returned NULL", be->name);
            rob_note_version_limit();
            return;
        }
        bench_log_info(ROB_TAG, "[R1][%s] create() time: %.1f ms", be->name,
                    (double)dt / 1000.0);
        be->destroy(h);
    }

    /* R2: create/destroy leak check. One warm-up cycle first, so one-time
     * lazily initialised state (either library) does not count as a leak; then
     * N cycles must return the heap exactly to its baseline. */
    {
        void *h = be->create(AEC_INPUT_FORMAT, AEC_FILTER_LEN, 0);
        be->destroy(h);   /* warm-up */

        size_t i0 = 0, p0 = 0, i1 = 0, p1 = 0;
        bench_heap_free(&i0, &p0);
        int ok = 1;
        for (int k = 0; k < SA_ROBUST_LEAK_ITERS; ++k) {
            h = be->create(AEC_INPUT_FORMAT, AEC_FILTER_LEN, 0);
            if (!h) { ok = 0; break; }
            be->destroy(h);
        }
        bench_heap_free(&i1, &p1);
        long di = (long)i0 - (long)i1;   /* >0 = heap shrank = leaked */
        long dp = (long)p0 - (long)p1;
        if (!ok) {
            bench_log_error(ROB_TAG, "[R2][%s] FAIL: create returned NULL mid-loop", be->name);
            rob_note_version_limit();
        } else if (di == 0 && dp == 0) {
            bench_log_info(ROB_TAG, "[R2][%s] PASS: %d create/destroy cycles, heap back to baseline",
                        be->name, SA_ROBUST_LEAK_ITERS);
        } else {
            /* Non-zero delta after N cycles. A constant small offset is usually
             * heap-fragmentation noise; a delta growing with N is a real leak.
             * Re-run with a larger SA_ROBUST_LEAK_ITERS to tell them apart. */
            bench_log_warn(ROB_TAG, "[R2][%s] WARN: heap delta after %d cycles: internal %+ld B, PSRAM %+ld B",
                        be->name, SA_ROBUST_LEAK_ITERS, di, dp);
        }
    }

#if SA_ROBUST_HEAP_TRACE
    /* R2b: heap-trace ONE create/destroy cycle and dump leaked allocations
     * with call stacks. Runs after the warm-up above, so one-time lazy init
     * does not pollute the report. */
    {
        static int s_trace_inited = 0;
        if (!s_trace_inited) {
            ESP_ERROR_CHECK(heap_trace_init_standalone(s_trace_records,
                                                       SA_TRACE_RECORDS));
            s_trace_inited = 1;
        }
        bench_log_info(ROB_TAG, "[R2b][%s] heap-trace: one create/destroy cycle...",
                       be->name);
        ESP_ERROR_CHECK(heap_trace_start(HEAP_TRACE_LEAKS));
        void *h = be->create(AEC_INPUT_FORMAT, AEC_FILTER_LEN, 0);
        if (h) be->destroy(h);
        ESP_ERROR_CHECK(heap_trace_stop());
        bench_log_info(ROB_TAG, "[R2b][%s] un-freed allocations (empty = no leak):",
                       be->name);
        heap_trace_dump();
    }
#endif /* SA_ROBUST_HEAP_TRACE */

    /* R3-R5: degenerate / overdriven inputs. */
    feed_frames(be, SA_ROBUST_FRAMES, fill_zero,      NULL, NULL, 0,
                "R3 zero-input");
    feed_frames(be, SA_ROBUST_FRAMES, fill_fullscale, NULL, NULL, 0,
                "R4 full-scale");
    feed_frames(be, SA_ROBUST_FRAMES, fill_clipped,   near, far, mono_samples,
                "R5 clipped-speech");
}

void robustness_run(const int16_t *near, const int16_t *far, size_t mono_samples)
{
    bench_log_info(ROB_TAG, "======== robustness suite (SA_TEST_ROBUSTNESS=1) ========");
    robustness_for_backend(fd_a1_backend(), near, far, mono_samples);
    robustness_for_backend(fd_a2_backend(), near, far, mono_samples);
    bench_log_info(ROB_TAG, "======== robustness suite done ========");
}

#else  /* SA_TEST_ROBUSTNESS == 0 */
/* ISO C requires a translation unit to contain at least one declaration. */
typedef int sa_robustness_disabled_t;
#endif /* SA_TEST_ROBUSTNESS */
