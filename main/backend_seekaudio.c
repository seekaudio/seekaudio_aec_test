/*
 * backend_seekaudio.c  --  aec_runner vtable for the SeekAudio prebuilt engine.
 *
 * Copyright (c) 2026 SeekAudio.  All rights reserved.
 *
 * Adapts the public seekaudio_aec_* API (the ONLY symbols the closed-source
 * library exposes) to the generic aec_backend_t used by the benchmark driver.
 *
 * `type` selects the denoise engine at runtime -- this is the A1/A2 switch:
 *   type = SEEKAUDIO_AEC_TYPE_NS (0)  -> conventional NS denoise   (config A1)
 *   type = SEEKAUDIO_AEC_TYPE_AI (1)  -> AI denoise (NS + RNN)     (config A2)
 */
#include "aec_runner.h"
#include "seekaudio_aec.h"

/* -------------------------------------------------------------------------
 * Near-end four-state demo hook (OFF by default; -DSA_NEAR_STATE_TEST=1).
 *
 * Calls seekaudio_aec_get_near_state() once after every process() -- exactly
 * how the public API is meant to be used -- and prints a per-state frame tally
 * when the run ends. With the switch at 0 the call is never made, so the
 * classifier allocates nothing and costs nothing.
 * ------------------------------------------------------------------------- */
#ifndef SA_NEAR_STATE_TEST
#define SA_NEAR_STATE_TEST 0
#endif

#if SA_NEAR_STATE_TEST
#include <stdio.h>
static long s_near_counts[4];   /* 0..3 = the four states */
static long s_near_total;
static void sk_near_reset(void)
{
    int i;
    for (i = 0; i < 4; i++) s_near_counts[i] = 0;
    s_near_total = 0;
}
static void sk_near_tally(seekaudio_aec_near_state_t st)
{
    if (st >= SEEKAUDIO_AEC_NEAR_SILENCE && st <= SEEKAUDIO_AEC_NEAR_DOUBLE_TALK) {
        s_near_counts[(int)st]++;
        s_near_total++;
    }
}
static void sk_near_report(void)
{
    long t = s_near_total > 0 ? s_near_total : 1;
    printf("[near-state] frames=%ld  silence=%ld(%.1f%%)  near-single=%ld(%.1f%%)  "
           "far-echo=%ld(%.1f%%)  double-talk=%ld(%.1f%%)\n",
           s_near_total,
           s_near_counts[0], 100.0 * s_near_counts[0] / t,
           s_near_counts[1], 100.0 * s_near_counts[1] / t,
           s_near_counts[2], 100.0 * s_near_counts[2] / t,
           s_near_counts[3], 100.0 * s_near_counts[3] / t);
}
#endif /* SA_NEAR_STATE_TEST */

static void *sk_create(const char *fmt, int flen, int type)
{
    (void)flen;
#if SA_NEAR_STATE_TEST
    sk_near_reset();
#endif
    return (void *)seekaudio_aec_create(fmt, (seekaudio_aec_type_t)type);
}
static size_t sk_process(void *h, const int16_t *in, int16_t *out)
{
    size_t n = seekaudio_aec_process((seekaudio_aec_t *)h, in, out);
#if SA_NEAR_STATE_TEST
    /* Call once per processed frame, as the API requires. First call lazily
     * arms the classifier; valid states follow. */
    sk_near_tally(seekaudio_aec_get_near_state((seekaudio_aec_t *)h));
#endif
    return n;
}
static int sk_chunksize(void *h)
{
    return seekaudio_aec_get_chunksize((seekaudio_aec_t *)h);
}
static void sk_destroy(void *h)
{
#if SA_NEAR_STATE_TEST
    sk_near_report();
#endif
    seekaudio_aec_destroy((seekaudio_aec_t *)h);
}

const aec_backend_t *seekaudio_backend(void)
{
    static const aec_backend_t vt = {
        "SeekAudio AEC",
        sk_create, sk_process, sk_chunksize, sk_destroy
    };
    return &vt;
}
