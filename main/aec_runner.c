/*
 * aec_runner.c  --  black-box AEC benchmark driver implementation.
 *
 * Copyright (c) 2026 SeekAudio.  All rights reserved.
 *
 * Derived from the in-tree test driver, with all source-level hooks removed:
 * no per-stage cycle counters, no allocator-side accounting -- everything is
 * observed from outside the backend so the driver works against a prebuilt
 * closed-source library exactly as it does against esp-sr.
 *
 * The metric ALGORITHMS (CRC32 polynomial, ERLE definitions, far-active
 * threshold, 2 s convergence buckets, p95) are byte-identical to the source
 * project's driver so numbers remain directly comparable across reports.
 */
#include "aec_runner.h"
#include "bench_port.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* cycles-per-us for the equivalent-MHz derivative (ESP32-S3 @ 240 MHz). */
#ifndef SA_CPU_MHZ
#define SA_CPU_MHZ 240
#endif

#define RUN_TAG "aec_runner"
#define RUN_MAX_FRAME 512   /* 32 ms @ 16 kHz */
#define RUN_MAX_CH    8

static int cmp_double(const void *a, const void *b)
{
    double da = *(const double *)a, db = *(const double *)b;
    return (da < db) ? -1 : (da > db) ? 1 : 0;
}

/* CRC32 (IEEE 802.3, reflected, init 0xFFFFFFFF) over the raw output bytes.
 * Used as a one-number bit-exact check: two builds whose int16 output is
 * identical print the same CRC; any single-sample difference changes it. */
static uint32_t sa_crc32(const void *data, size_t nbytes)
{
    const unsigned char *p = (const unsigned char *)data;
    uint32_t crc = 0xFFFFFFFFu;
    size_t i; int k;
    for (i = 0; i < nbytes; ++i) {
        crc ^= p[i];
        for (k = 0; k < 8; ++k)
            crc = (crc >> 1) ^ (0xEDB88320u & (uint32_t)(-(int32_t)(crc & 1u)));
    }
    return crc ^ 0xFFFFFFFFu;
}

int aec_run(const aec_backend_t *backend,
            const char *input_format, int filter_length, int type,
            const int16_t *near, const int16_t *far,
            size_t mono_samples, int sample_rate,
            int16_t *out_buf, size_t *out_samples,
            aec_run_stats_t *stats)
{
    void   *inst;
    int     frame_samples, total_ch, mic_idx, ref_idx;
    size_t  total_frames, f, proc_samples;
    int16_t interleaved[RUN_MAX_FRAME * RUN_MAX_CH];
    int16_t frame_out[RUN_MAX_FRAME];
    double *frame_us = NULL;
    double  sum_us = 0.0, max_us = 0.0;
    /* Per-frame energies for ERLE / convergence (computed outside timed region). */
    double *mic_e = NULL, *out_e = NULL, *far_e = NULL;
    /* Heap snapshots for the black-box footprint (see aec_runner.h). */
    size_t  free_i0 = 0, free_p0 = 0;   /* before create()                 */
    size_t  free_i1 = 0, free_p1 = 0;   /* after create() = run baseline   */
    size_t  min_i = 0, min_p = 0;       /* minimum free seen during run    */

    if (!backend || !near || !far || !out_buf || !stats) {
        return -1;
    }
    memset(stats, 0, sizeof(*stats));

    /* create() footprint + wall time, measured from the outside. */
    bench_heap_free(&free_i0, &free_p0);
    {
        int64_t c0 = bench_time_us();
        inst = backend->create(input_format, filter_length, type);
        stats->create_us = (double)(bench_time_us() - c0);
    }
    if (!inst) {
        bench_log_error(RUN_TAG, "%s: create failed", backend->name);
        return -1;
    }
    bench_heap_free(&free_i1, &free_p1);
    stats->create_internal_bytes = (free_i0 > free_i1) ? free_i0 - free_i1 : 0;
    stats->create_psram_bytes    = (free_p0 > free_p1) ? free_p0 - free_p1 : 0;
    min_i = free_i1;
    min_p = free_p1;

    bench_log_info(RUN_TAG, "backend         : %s", backend->name);

    frame_samples = backend->get_chunksize(inst);
    if (frame_samples <= 0 || frame_samples > RUN_MAX_FRAME) {
        bench_log_error(RUN_TAG, "%s: bad chunksize %d", backend->name, frame_samples);
        backend->destroy(inst);
        return -1;
    }

    /* Layout indices from the same format string (mic + ref). */
    total_ch = 0; mic_idx = 0; ref_idx = 1;
    {
        int i, m = -1, r = -1;
        for (i = 0; input_format && input_format[i]; ++i) {
            if ((input_format[i] == 'M' || input_format[i] == 'm') && m < 0) m = i;
            if ((input_format[i] == 'R' || input_format[i] == 'r') && r < 0) r = i;
            total_ch++;
        }
        if (total_ch < 1 || total_ch > RUN_MAX_CH || m < 0 || r < 0) {
            bench_log_error(RUN_TAG, "bad input_format \"%s\"", input_format);
            backend->destroy(inst);
            return -1;
        }
        mic_idx = m; ref_idx = r;
    }

    total_frames = mono_samples / (size_t)frame_samples;
    proc_samples = total_frames * (size_t)frame_samples;

    frame_us = (double *)malloc(total_frames * sizeof(double));
    mic_e    = (double *)malloc(total_frames * sizeof(double));
    out_e    = (double *)malloc(total_frames * sizeof(double));
    far_e    = (double *)malloc(total_frames * sizeof(double));
    if (!frame_us || !mic_e || !out_e || !far_e) {
        free(frame_us); free(mic_e); free(out_e); free(far_e);
        backend->destroy(inst);
        return -1;
    }

    for (f = 0; f < total_frames; ++f) {
        const int16_t *near_ptr = near + f * frame_samples;
        const int16_t *far_ptr  = far  + f * frame_samples;
        int s;
        int64_t t0, t1;
        double  us;

        /* The interleave is part of the per-call cost a production caller
         * would also pay, but file I/O is excluded entirely. We time only
         * the process() call to isolate algorithm compute. */
        for (s = 0; s < frame_samples; ++s) {
            interleaved[s * total_ch + mic_idx] = near_ptr[s];
            interleaved[s * total_ch + ref_idx] = far_ptr[s];
        }

        t0 = bench_time_us();
        backend->process(inst, interleaved, frame_out);
        t1 = bench_time_us();

        memcpy(out_buf + f * frame_samples, frame_out,
               (size_t)frame_samples * sizeof(int16_t));

        us = (double)(t1 - t0);
        frame_us[f] = us;
        sum_us += us;
        if (us > max_us) max_us = us;

        /* Per-frame energies (mic = near, residual = out, reference = far) for
         * ERLE and the convergence curve. Outside the timed region above. */
        {
            double me = 0.0, oe = 0.0, fe = 0.0;
            for (s = 0; s < frame_samples; ++s) {
                double m = (double)near_ptr[s];
                double o = (double)frame_out[s];
                double r = (double)far_ptr[s];
                me += m * m; oe += o * o; fe += r * r;
            }
            mic_e[f] = me; out_e[f] = oe; far_e[f] = fe;
        }

        /* Transient-heap low-water tracking. Outside the timed region, so it
         * never affects the compute measurement; catches per-frame temporary
         * allocations that a create()-only delta would miss. */
        {
            size_t fi = 0, fp = 0;
            bench_heap_free(&fi, &fp);
            if (fi < min_i) min_i = fi;
            if (fp < min_p) min_p = fp;
        }

        /* Periodically yield so the idle / watchdog tasks on this core get to
         * run during this flat-out batch loop. Outside the timed region. */
        if ((f & 0x0F) == 0x0F) {
            bench_yield();
        }
    }

    /* Stats. */
    stats->backend_name      = backend->name;
    stats->sample_rate       = sample_rate;
    stats->frames            = total_frames;
    stats->processed_samples = proc_samples;
    stats->out_crc32         = sa_crc32(out_buf, proc_samples * sizeof(int16_t));
    stats->audio_sec         = (double)proc_samples / (double)sample_rate;
    stats->process_sec       = sum_us / 1e6;
    stats->rtf               = (stats->process_sec > 0.0)
                                   ? stats->audio_sec / stats->process_sec : 0.0;
    stats->per_frame_avg_us  = (total_frames > 0) ? sum_us / (double)total_frames : 0.0;
    stats->per_frame_max_us  = max_us;
    stats->per_frame_max_idx = 0;
    stats->outliers_over_2p95 = 0;
    stats->first_frame_us    = (total_frames > 0) ? frame_us[0] : 0.0;

    /* Customer-facing derivatives. */
    {
        double frame_period_us = 1e6 * (double)frame_samples / (double)sample_rate;
        if (frame_period_us > 0.0) {
            stats->cpu_load_pct  = 100.0 * stats->per_frame_avg_us / frame_period_us;
            stats->cpu_equiv_mhz = stats->cpu_load_pct / 100.0 * (double)SA_CPU_MHZ;
        }
    }

    if (total_frames > 0) {
        /* Worst-frame index in ORIGINAL order (qsort below destroys the order).
         * Lets the report say whether the max is frame #0 (cold start) or a
         * mid-run frame (scheduling / PSRAM paging). */
        size_t mi = 0; double mv = frame_us[0];
        for (size_t k = 1; k < total_frames; ++k)
            if (frame_us[k] > mv) { mv = frame_us[k]; mi = k; }
        stats->per_frame_max_idx = mi;

        qsort(frame_us, total_frames, sizeof(double), cmp_double);
        size_t idx = (size_t)(0.95 * (double)(total_frames - 1));
        stats->per_frame_p95_us = frame_us[idx];
        {
            double frame_period_us = 1e6 * (double)frame_samples / (double)sample_rate;
            if (frame_period_us > 0.0) {
                stats->cpu_load_peak_pct =
                    100.0 * stats->per_frame_p95_us / frame_period_us;
                stats->cpu_load_max_pct =
                    100.0 * stats->per_frame_max_us / frame_period_us;
            }
        }

        /* Count of frames slower than 2x p95 (order-independent on sorted data).
         * 1 outlier that is also frame #0 => cold start; >1 or non-zero index
         * elsewhere => a recurring stall worth chasing. */
        double thr2 = 2.0 * stats->per_frame_p95_us;
        for (size_t k = 0; k < total_frames; ++k)
            if (frame_us[k] > thr2) stats->outliers_over_2p95++;
    }

    /* ---- Quality metrics: ERLE + convergence curve (two passes over energy). ---- */
    {
        double max_far = 0.0, thr;
        double mic_all = 0.0, out_all = 0.0;
        double mic_act = 0.0, out_act = 0.0;
        double mic_fin = 0.0, out_fin = 0.0;
        size_t i, q0, bucket_frames, b;
        int active = 0;

        for (i = 0; i < total_frames; ++i) if (far_e[i] > max_far) max_far = far_e[i];
        thr = max_far * 0.01;   /* echo "present" when far within ~20 dB of peak */
        q0  = (total_frames * 3) / 4;

        for (i = 0; i < total_frames; ++i) {
            mic_all += mic_e[i]; out_all += out_e[i];
            if (far_e[i] > thr) {
                mic_act += mic_e[i]; out_act += out_e[i]; active++;
                if (i >= q0) { mic_fin += mic_e[i]; out_fin += out_e[i]; }
            }
        }
        if (max_far <= 0.0) {
            bench_log_warn(RUN_TAG,
                "far-end signal is ALL ZERO -- no echo present, ERLE/convergence "
                "metrics are meaningless. Check far.wav in the littlefs image.");
        }
        stats->erle_overall_db = (out_all > 0.0) ? 10.0 * log10(mic_all / out_all) : 0.0;
        stats->erle_active_db  = (out_act > 0.0) ? 10.0 * log10(mic_act / out_act) : 0.0;
        stats->erle_final_db   = (out_fin > 0.0) ? 10.0 * log10(mic_fin / out_fin) : 0.0;
        stats->active_frames   = active;

        /* Convergence: far-active ERLE per ~2 s bucket. */
        stats->bucket_sec = 2.0;
        bucket_frames = (size_t)(stats->bucket_sec * sample_rate / frame_samples);
        if (bucket_frames == 0) bucket_frames = 1;
        stats->bucket_count = 0;
        for (b = 0; b < AEC_ERLE_BUCKETS; ++b) {
            size_t start = b * bucket_frames, end = start + bucket_frames;
            double bm = 0.0, bo = 0.0;
            if (start >= total_frames) break;
            if (end > total_frames) end = total_frames;
            for (i = start; i < end; ++i) {
                if (far_e[i] > thr) { bm += mic_e[i]; bo += out_e[i]; }
            }
            stats->erle_bucket_db[b] = (bo > 0.0) ? 10.0 * log10(bm / bo) : -999.0;
            stats->bucket_count = (int)(b + 1);
        }
    }

    /* Transient peak = run baseline minus lowest free seen. */
    stats->run_peak_internal_bytes = (free_i1 > min_i) ? free_i1 - min_i : 0;
    stats->run_peak_psram_bytes    = (free_p1 > min_p) ? free_p1 - min_p : 0;

    stats->stack_min_free_bytes = bench_min_free_stack();

    *out_samples = proc_samples;
    free(frame_us); free(mic_e); free(out_e); free(far_e);
    backend->destroy(inst);
    return 0;
}

void aec_run_print_stats(const aec_run_stats_t *s)
{
    bench_log_info(RUN_TAG, "-------- %s --------", s->backend_name);
    bench_log_info(RUN_TAG, "sample rate     : %d Hz", s->sample_rate);
    bench_log_info(RUN_TAG, "frames          : %zu (32 ms each)", s->frames);
    bench_log_info(RUN_TAG, "audio duration  : %.2f s", s->audio_sec);
    bench_log_info(RUN_TAG, "compute time    : %.4f s (excl. file I/O)", s->process_sec);
    bench_log_info(RUN_TAG, "real-time factor: %.2fx", s->rtf);
    bench_log_info(RUN_TAG, "per-frame avg   : %.1f us", s->per_frame_avg_us);
    bench_log_info(RUN_TAG, "per-frame p95   : %.1f us", s->per_frame_p95_us);
    bench_log_info(RUN_TAG, "per-frame max   : %.1f us  at frame #%zu/%zu (real-time vs 32000 us)",
                s->per_frame_max_us, s->per_frame_max_idx, s->frames);
    /* Verdict tiers: (1) max inside the first 8 frames = startup transient
     * (reblocking spreads the cold start over frames 0-3); (2) a mid-run max
     * within 25% of p95 = ordinary scheduler jitter, not a stall; (3) anything
     * above that, or repeated >2x-p95 frames, deserves a look. */
    bench_log_info(RUN_TAG, "  frame#0 (cold) : %.1f us;  frames > 2x p95: %zu  %s",
                s->first_frame_us, s->outliers_over_2p95,
                (s->outliers_over_2p95 > 1)
                    ? "-> recurring stalls: investigate"
                    : (s->per_frame_max_idx < 8)
                        ? "-> max is a startup-transient frame (benign)"
                        : (s->per_frame_max_us <= 1.25 * s->per_frame_p95_us)
                            ? "-> max within normal jitter of p95 (benign)"
                            : "-> single mid-run spike: investigate");
    bench_log_info(RUN_TAG, "CPU load        : %.1f%% avg / %.1f%% p95 / %.1f%% max (frame #%zu)  (~%.0f MHz of %d MHz)",
                s->cpu_load_pct, s->cpu_load_peak_pct, s->cpu_load_max_pct, s->per_frame_max_idx,
                s->cpu_equiv_mhz, (int)SA_CPU_MHZ);

    /* Quality */
    bench_log_info(RUN_TAG, "ERLE overall    : %.2f dB (all frames; doubletalk lowers this)",
                s->erle_overall_db);
    bench_log_info(RUN_TAG, "ERLE echo-active: %.2f dB (%d far-active frames)",
                s->erle_active_db, s->active_frames);
    bench_log_info(RUN_TAG, "ERLE converged  : %.2f dB (last quarter, echo-active)",
                s->erle_final_db);

    /* Convergence curve */
    {
        char line[256];
        int b, n = 0;
        n += snprintf(line + n, sizeof(line) - n, "convergence ERLE/%.0fs:", s->bucket_sec);
        for (b = 0; b < s->bucket_count && n < (int)sizeof(line) - 8; ++b) {
            if (s->erle_bucket_db[b] <= -999.0)
                n += snprintf(line + n, sizeof(line) - n, " --");
            else
                n += snprintf(line + n, sizeof(line) - n, " %.1f", s->erle_bucket_db[b]);
        }
        bench_log_info(RUN_TAG, "%s", line);
    }

    bench_log_info(RUN_TAG, "output CRC32     : 0x%08X (bit-exact check; equal = identical output)",
                (unsigned)s->out_crc32);

    /* Footprint (black-box: heap deltas + stack watermark). */
    bench_log_info(RUN_TAG, "create()        : %.1f ms;  internal SRAM %.1f KB, PSRAM %.1f KB",
                s->create_us / 1000.0,
                (double)s->create_internal_bytes / 1024.0,
                (double)s->create_psram_bytes / 1024.0);
    bench_log_info(RUN_TAG, "run transient   : internal SRAM peak +%.1f KB, PSRAM peak +%.1f KB",
                (double)s->run_peak_internal_bytes / 1024.0,
                (double)s->run_peak_psram_bytes / 1024.0);
    bench_log_info(RUN_TAG, "stack headroom  : %.1f KB (min free during run)",
                (double)s->stack_min_free_bytes / 1024.0);
}
