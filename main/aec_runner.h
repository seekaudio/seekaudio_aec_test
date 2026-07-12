/*
 * aec_runner.h  --  black-box AEC benchmark driver (prebuilt-library edition).
 *
 * Copyright (c) 2026 SeekAudio.  All rights reserved.
 *
 * Backend-agnostic frame loop + compute-time profiling. Every metric here is
 * measured from OUTSIDE the backend -- timing wraps the process() call, memory
 * is heap free-size deltas, quality (ERLE/CRC) is computed from the near/out
 * sample buffers -- so the same driver measures the SeekAudio prebuilt .a and
 * the Espressif esp-sr backends identically, with zero access to internals.
 *
 * Measured time EXCLUDES all file I/O: callers load near/far and write output
 * outside the timed region; aec_run() times only the per-frame process() calls.
 */
#ifndef AEC_RUNNER_H
#define AEC_RUNNER_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Generic backend interface. `type` is backend-defined:
 *   SeekAudio backend : seekaudio_aec_type_t (0 = NS denoise, 1 = AI denoise)
 *   ESP FD backend    : ignored (config baked in by the vtable constructor)  */
typedef struct {
    const char *name;
    void  *(*create)(const char *input_format, int filter_length, int type);
    size_t (*process)(void *handle, const int16_t *indata, int16_t *outdata);
    int    (*get_chunksize)(void *handle);
    void   (*destroy)(void *handle);
} aec_backend_t;

/* Convergence curve buckets (segmental ERLE over ~2 s each). */
#define AEC_ERLE_BUCKETS 32

typedef struct {
    const char *backend_name;
    int    sample_rate;
    size_t frames;
    size_t processed_samples;
    double audio_sec;          /* processed audio duration                   */
    double process_sec;        /* total compute time, EXCLUDING file I/O     */
    double rtf;                /* real-time factor = audio_sec / process_sec */
    double per_frame_avg_us;   /* mean per-frame compute time                */
    double per_frame_max_us;   /* worst-case per-frame (real-time headroom)  */
    double per_frame_p95_us;   /* 95th-percentile per-frame                  */
    size_t per_frame_max_idx;  /* frame index of the worst-case frame        */
    size_t outliers_over_2p95; /* # frames slower than 2x p95 (excl. frame 0) */
    double first_frame_us;     /* frame 0 time (cold-start tell)              */

    /* Customer-facing derivatives (frame period = chunksize / sample_rate):
     *   cpu_load_pct      = per_frame_avg_us / frame_period_us * 100
     *   cpu_load_peak_pct = per_frame_p95_us / frame_period_us * 100
     *   cpu_load_max_pct  = per_frame_max_us / frame_period_us * 100 (worst frame)
     *   cpu_equiv_mhz     = cpu_load_pct% of SA_CPU_MHZ                     */
    double cpu_load_pct;
    double cpu_load_peak_pct;
    double cpu_load_max_pct;
    double cpu_equiv_mhz;

    uint32_t out_crc32;        /* CRC32 of the whole int16 output (bit-exact check) */

    /* --- Quality: ERLE (Echo Return Loss Enhancement), 10log10(mic / out). --- */
    double erle_overall_db;    /* all frames (doubletalk drags this down)    */
    double erle_active_db;     /* far-active frames only (echo present)      */
    double erle_final_db;      /* far-active frames in the last quarter      */
    int    active_frames;      /* number of far-active frames used           */

    /* --- Convergence curve: far-active ERLE per bucket over time. --- */
    double bucket_sec;
    int    bucket_count;
    double erle_bucket_db[AEC_ERLE_BUCKETS];  /* -999 = no echo in bucket     */

    /* --- Footprint (black-box: heap free-size deltas + stack watermark). ---
     * create_*    : heap consumed by backend create() (steady-state engine RAM)
     * run_peak_*  : additional transient heap used DURING processing, i.e.
     *               (free after create) - (minimum free seen across the run);
     *               catches per-frame temporary allocations create() misses.  */
    double create_us;               /* create() wall time (boot budget)       */
    size_t create_internal_bytes;   /* internal SRAM consumed by create()     */
    size_t create_psram_bytes;      /* PSRAM consumed by create()             */
    size_t run_peak_internal_bytes; /* transient internal-SRAM peak in run    */
    size_t run_peak_psram_bytes;    /* transient PSRAM peak in run            */
    size_t stack_min_free_bytes;    /* task stack headroom (min free seen)    */
} aec_run_stats_t;

/*
 * Run a backend over mono near/far buffers.
 *
 *  near/far        : mono int16 arrays, mono_samples each.
 *  out_buf         : caller-allocated, >= mono_samples int16 (device: PSRAM).
 *  input_format    : channel layout passed to the backend ("MR").
 *  type            : backend-defined (see aec_backend_t).
 *  Returns 0 on success.
 */
int aec_run(const aec_backend_t *backend,
            const char *input_format, int filter_length, int type,
            const int16_t *near, const int16_t *far,
            size_t mono_samples, int sample_rate,
            int16_t *out_buf, size_t *out_samples,
            aec_run_stats_t *stats);

/* Pretty-print a stats block via the harness logger. */
void aec_run_print_stats(const aec_run_stats_t *s);

#ifdef __cplusplus
}
#endif

#endif /* AEC_RUNNER_H */
