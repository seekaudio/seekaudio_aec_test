/*
 * fd_aec_backend.cpp  --  aec_runner vtables for the four comparison configs.
 *
 * Copyright (c) 2026 SeekAudio.  All rights reserved.
 *
 * The four configs share the same linear AEC front end and differ only in the
 * post-processing stage, so the comparison isolates the post-stage:
 *
 *   A1 : SeekAudio AEC + NLP + WebRTC NS
 *   A2 : SeekAudio AEC + NLP + AI Noise
 *   B1 : linear AEC + NLP (AGGR) + esp ns_pro      (comparison baseline)
 *   B2 : linear AEC + NLP (AGGR) + esp nsnet2      (comparison baseline)
 *
 * A1 / A2 run entirely through the SeekAudio public API (seekaudio_aec_*): the
 * library performs the whole A-path pipeline internally and this file only
 * forwards create / process / destroy to it (see the A1/A2 vtables below).
 *
 * B1 / B2 are the comparison baselines wired here from esp-sr blocks. Their NS
 * stage frame size differs from the front-end chunk (ns_pro 160 vs the nsnet
 * chunk), so each reblocks through a small FIFO and always emits one chunk per
 * process() call. Startup emits a few zero samples (the reblock latency);
 * harmless for offline compare.
 *
 * B2 (nsnet2) loads its weights from the esp-sr srmodel filesystem, so it
 * requires: a "model" data partition in partitions.csv, CONFIG_SR_NSN_NSNET2=y
 * (packs nsnet2 into srmodels.bin), and srmodels.bin flashed to that partition.
 * If the partition is missing, B2 create() fails and the harness skips it.
 */
#if defined(ESP_PLATFORM)

#include "aec_runner.h"
#include "esp_aec.h"          /* linear AEC front end                          */
#include "esp_aec_nlp.h"      /* NLP level (AGGR)                              */
#include "esp_ns.h"           /* ns_pro_create / ns_process (B1)               */
/* esp-sr's nsnet headers (unlike esp_aec.h) lack extern "C" guards, so a C++
 * TU mangles esp_nsnet_handle_from_name and fails to link against libnsnet.a's
 * C symbol. Include them under extern "C" to force C linkage. */
extern "C" {
#include "esp_nsn_models.h"   /* esp_nsnet_handle_from_name (B2 nsnet2)        */
}
#include "model_path.h"       /* esp_srmodel_init: mmap "model" partition      */
#include "seekaudio_aec.h"    /* SeekAudio public API (A path: create/process)  */
#include "esp_heap_caps.h"
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

/* ----- tunables (identical names and defaults to the source project) ------ */

/* A-path FD linear AEC mode. FD_LOW_COST matches the documented baseline. */
#ifndef FD_AEC_MODE
#define FD_AEC_MODE        AEC_MODE_FD_LOW_COST
#endif
/* B-path (B1/B2) linear AEC mode, kept separate from the A-path so the two can
 * be compared independently. */
#ifndef FD_AEC_MODE_B
#define FD_AEC_MODE_B      AEC_MODE_FD_HIGH_PERF
#endif
#ifndef FD_NLP_LEVEL
#define FD_NLP_LEVEL       AEC_NLP_LEVEL_AGGR
#endif
#ifndef FD_FILTER_LENGTH
#define FD_FILTER_LENGTH   4          /* esp-sr recommends 4 on esp32s3        */
#endif
/* Where the FD AEC puts its internal buffers (the .a code stays in iRAM). */
#ifndef FD_AEC_CAPS
#define FD_AEC_CAPS        (MALLOC_CAP_SPIRAM)
#endif

/* esp ns_pro aggressiveness for B1 (0 Mild / 1 Medium / 2 Aggressive). */
#ifndef FD_NSPRO_MODE
#define FD_NSPRO_MODE      2
#endif
#define NSPRO_FRAME_MS     10                 /* ns_pro supports 10 ms only    */

/* ---- EXPERIMENT: remove the ns_pro NS stage from B1 ---------------------
 * 0 = off (default, normal B1). 1 = B1 WITHOUT the ns_pro module: it is not
 * created (no RAM), not called (no compute), not destroyed. Everything else is
 * identical -- FD linear AEC + NLP + the 160-sample reblock/FIFO plumbing --
 * so the NLP output passes straight through. The delta vs normal B1 is the
 * full cost of the ns_pro module: CPU (per-frame) AND create() internal SRAM.
 * Confirmation when =1: the "WebRtcNs_Create: ... size:23632" line disappears,
 * B1 create() internal SRAM drops, and output CRC differs (NS skipped) -- all
 * expected; this is a cost probe, not a bit-exactness check. */
#ifndef B1_BYPASS_NS
#define B1_BYPASS_NS       0
#endif

/* esp nsnet model name for B2. */
#ifndef FD_NSNET_MODEL
#define FD_NSNET_MODEL     "nsnet2"
#endif

/* esp-sr model partition label (mmap'd to /srmodel by esp_srmodel_init). */
#ifndef FD_SRMODEL_PARTITION
#define FD_SRMODEL_PARTITION "model"
#endif

#define FD_MAX_FRAME       512
#define SA_NS_FRAME        512                 /* max NS block size (samples)   */

/* ----- tiny int16 FIFO --------------------------------------------------- */
typedef struct {
    int16_t *buf;
    int      cap, head, count;
} fifo_t;

static int fifo_init(fifo_t *q, int cap, uint32_t caps)
{
    q->buf = (int16_t *)heap_caps_malloc((size_t)cap * sizeof(int16_t), caps);
    q->cap = cap; q->head = 0; q->count = 0;
    return q->buf ? 0 : -1;
}
static void fifo_free(fifo_t *q) { if (q->buf) { heap_caps_free(q->buf); q->buf = NULL; } }
static void fifo_push(fifo_t *q, const int16_t *src, int n)
{
    int i, w;
    for (i = 0; i < n; ++i) {
        w = (q->head + q->count) % q->cap;
        q->buf[w] = src[i];
        if (q->count < q->cap) q->count++;
        else q->head = (q->head + 1) % q->cap;   /* overwrite-oldest (never hit) */
    }
}
static void fifo_pop(fifo_t *q, int16_t *dst, int n)
{
    int i;
    for (i = 0; i < n; ++i) {
        dst[i] = q->buf[q->head];
        q->head = (q->head + 1) % q->cap;
        q->count--;
    }
}

/* ----- config + context -------------------------------------------------- */
typedef enum { FD_CFG_A1 = 0, FD_CFG_A2, FD_CFG_B1, FD_CFG_B2 } fd_cfg_t;

/* ---- B-path internal-SRAM demonstration toggle ----------------------------
 * B_AEC_INTERNAL_SRAM = 0 (default): B1's and B2's FD linear AEC front-end +
 *   harness buffers stay in PSRAM -- esp-sr's shipped default placement, i.e.
 *   the reference configs are measured exactly as a customer gets them out of
 *   the box, with no manual relocation of the competitor's memory. This is the
 *   honest default for the A-vs-B comparison.
 * B_AEC_INTERNAL_SRAM = 1: BOTH B1 and B2 are placed in internal SRAM instead,
 *   giving them the same on-chip fast memory the A path uses. Purpose -- rebut a
 *   "you handicapped the B configs with slow PSRAM" objection: with the toggle
 *   on, B1/B2 per-frame CPU drops but they STILL lose to A1/A2, while their
 *   internal SRAM balloons far past the A path's (B1 observed ~129 KB vs A1's
 *   ~75 KB; B2 rises similarly). It shows the A-path advantage is algorithmic,
 *   not a memory-placement trick, and that buying the B configs that much
 *   internal SRAM is not worth it.
 * NOTE: only the FD AEC front-end + harness buffers move (what b_caps_for
 *   governs). B2's NSNet2 model weights (~0.5 MB) are loaded by esp-sr into
 *   PSRAM independently and are NOT relocated -- they exceed internal SRAM.
 * Forwarded by main/CMakeLists.txt, so:  idf.py -DB_AEC_INTERNAL_SRAM=1 build
 * (CMake cache vars are sticky: pass =0 or `idf.py fullclean` to turn back off.) */
#ifndef B_AEC_INTERNAL_SRAM
#define B_AEC_INTERNAL_SRAM   0
#endif

/* Heap caps for a B-path config's harness buffers (the FD linear AEC front-end
 * via ac.caps, the reblock FIFOs, and the nsblk scratch). Default: both B1 and
 * B2 in PSRAM (esp-sr shipped placement). With B_AEC_INTERNAL_SRAM=1, both B1
 * and B2 move these to internal SRAM (see the toggle above); B2's NSNet2 model
 * stays in PSRAM regardless. (The A path is placed by the library internally.) */
static inline uint32_t b_caps_for(fd_cfg_t cfg)
{
#if B_AEC_INTERNAL_SRAM
    if (cfg == FD_CFG_B1 || cfg == FD_CFG_B2)
        return (uint32_t)(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
#endif
    (void)cfg;
    return (uint32_t)MALLOC_CAP_SPIRAM;
}

typedef struct {
    fd_cfg_t      cfg;
    aec_handle_t *fd;
    int           frame_samples;    /* FD chunk (= aec_get_chunksize)          */
    int           total_ch, mic_idx, ref_idx;

    /* aligned scratch for the FD calls (esp-sr requires 16-byte aligned bufs). */
    int16_t      *mic, *ref, *residual, *nlp;

    /* B1 path: ns_pro reblocked to 160.                                       */
    ns_handle_t   nspro;
    int           nspro_frame;      /* 160 @ 16 k                              */

    /* B2 path: esp nsnet2 (deep NS) reblocked to its own chunksize.           */
    const esp_nsn_iface_t *nsn_if;
    esp_nsn_data_t        *nsn;
    int           nsn_frame;        /* nsnet get_samp_chunksize()              */
    fifo_t        nlp_fifo;

    /* shared output FIFO -> emit exactly one FD chunk per process() call.     */
    fifo_t        out_fifo;
    int16_t      *nsblk_in, *nsblk_out;   /* scratch for one NS-frame block     */
} fd_ctx_t;

/* ----- create ------------------------------------------------------------ */
static void fd_parse_fmt(const char *fmt, int *total_ch, int *mic_idx, int *ref_idx)
{
    int i; int m = -1, r = -1;
    *total_ch = 0;
    for (i = 0; fmt && fmt[i]; ++i) {
        if ((fmt[i] == 'M' || fmt[i] == 'm') && m < 0) m = i;
        if ((fmt[i] == 'R' || fmt[i] == 'r') && r < 0) r = i;
        (*total_ch)++;
    }
    if (*total_ch <= 0) *total_ch = 1;
    *mic_idx = (m < 0) ? 0 : m;
    *ref_idx = (r < 0) ? 1 : r;
}

static int16_t *aligned16(int n)
{
    return (int16_t *)heap_caps_aligned_alloc(
        16, (size_t)n * sizeof(int16_t), MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
}

static void *fd_create_cfg(const char *fmt, int flen, fd_cfg_t cfg)
{
    (void)flen;
    fd_ctx_t *c = (fd_ctx_t *)calloc(1, sizeof(fd_ctx_t));
    if (!c) return NULL;
    c->cfg = cfg;

    int sr = 16000;   /* FD is 16 kHz only */

    /* Heap caps for this config's harness buffers (see B_AEC_INTERNAL_SRAM):
     * default B1 & B2 -> PSRAM (as shipped); with the toggle on, both -> internal. */
    const uint32_t bcap = b_caps_for(cfg);

    /* 1) FD linear AEC create. A path uses FD_AEC_MODE, B path FD_AEC_MODE_B. */
    {
        aec_config_t ac;
        memset(&ac, 0, sizeof(ac));
        ac.mic_num       = 1;
        ac.ref_num       = 1;
        ac.out_num       = 1;
        ac.filter_length = FD_FILTER_LENGTH;
        ac.sample_rate   = sr;
        ac.caps          = (cfg == FD_CFG_B1 || cfg == FD_CFG_B2) ? bcap : FD_AEC_CAPS;
        ac.mode          = (aec_mode_t)((cfg == FD_CFG_B1 || cfg == FD_CFG_B2)
                                         ? FD_AEC_MODE_B : FD_AEC_MODE);
        ac.nlp_level     = (aec_nlp_level_t)FD_NLP_LEVEL;
        c->fd = aec_create_from_config(&ac);
        if (!c->fd) { free(c); return NULL; }
        aec_set_nlp_level(c->fd, (aec_nlp_level_t)FD_NLP_LEVEL);
    }

    fd_parse_fmt(fmt, &c->total_ch, &c->mic_idx, &c->ref_idx);
    c->frame_samples = aec_get_chunksize(c->fd);
    if (c->frame_samples <= 0 || c->frame_samples > FD_MAX_FRAME) {
        aec_destroy(c->fd); free(c); return NULL;
    }

    /* aligned FD scratch */
    c->mic      = aligned16(c->frame_samples);
    c->ref      = aligned16(c->frame_samples);
    c->residual = aligned16(c->frame_samples);
    c->nlp      = aligned16(c->frame_samples);
    if (!c->mic || !c->ref || !c->residual || !c->nlp) goto fail;

    /* shared output FIFO + a one-NS-frame scratch (max of 512 / 160). */
    if (fifo_init(&c->out_fifo, c->frame_samples + SA_NS_FRAME + 16, bcap)) goto fail;
    c->nsblk_in  = (int16_t *)heap_caps_malloc(SA_NS_FRAME * sizeof(int16_t), bcap);
    c->nsblk_out = (int16_t *)heap_caps_malloc(SA_NS_FRAME * sizeof(int16_t), bcap);
    if (!c->nsblk_in || !c->nsblk_out) goto fail;

    if (cfg == FD_CFG_B1) {
        /* B1: esp ns_pro (10 ms), reblock nlp output -> 160. */
        c->nspro_frame = sr / 1000 * NSPRO_FRAME_MS;     /* 160 @ 16 k */
#if !B1_BYPASS_NS
        c->nspro = ns_pro_create(NSPRO_FRAME_MS, FD_NSPRO_MODE, sr);
        if (!c->nspro) goto fail;
        if (fifo_init(&c->nlp_fifo, c->frame_samples + c->nspro_frame + 16, bcap)) goto fail;
#else
        /* probe mode: skip the ns_pro module entirely -- no ns_pro_create (no
         * ~23 KB alloc, no create time) and no 160-sample reblock FIFO.
         * c->nspro and c->nlp_fifo.buf stay NULL (calloc'd); process() emits the
         * NLP output directly and destroy() is already null-guarded. */
        c->nspro = NULL;
#endif
    } else if (cfg == FD_CFG_B2) {
        /* B2: esp nsnet2 (deep NS). The nsnet2 iface loads its weights from the
         * esp-sr srmodel filesystem, so the "model" partition must be mmap'd to
         * /srmodel first. esp_srmodel_init sets a static global that
         * esp_nsnet_handle_from_name() reads; it is refcounted, so calling it
         * once here is safe. */
        static srmodel_list_t *s_srmodels = NULL;
        if (!s_srmodels) {
            s_srmodels = esp_srmodel_init(FD_SRMODEL_PARTITION);
            if (!s_srmodels) {
                /* partition missing / empty -> cannot load nsnet2. */
                goto fail;
            }
        }
        c->nsn_if = esp_nsnet_handle_from_name((char *)FD_NSNET_MODEL);
        if (!c->nsn_if) goto fail;
        c->nsn = c->nsn_if->create((char *)FD_NSNET_MODEL);
        if (!c->nsn) goto fail;
        c->nsn_frame = c->nsn_if->get_samp_chunksize(c->nsn);
        /* nsblk_in/out are sized SA_NS_FRAME; the model frame must fit. */
        if (c->nsn_frame <= 0 || c->nsn_frame > SA_NS_FRAME) goto fail;
        if (fifo_init(&c->nlp_fifo, c->frame_samples + c->nsn_frame + 16, bcap)) goto fail;
    }

    return c;

fail:
    if (c->mic) heap_caps_free(c->mic);
    if (c->ref) heap_caps_free(c->ref);
    if (c->residual) heap_caps_free(c->residual);
    if (c->nlp) heap_caps_free(c->nlp);
    if (c->nsblk_in) heap_caps_free(c->nsblk_in);
    if (c->nsblk_out) heap_caps_free(c->nsblk_out);
    fifo_free(&c->out_fifo); fifo_free(&c->nlp_fifo);
    if (c->nspro) ns_destroy(c->nspro);
    if (c->nsn && c->nsn_if) c->nsn_if->destroy(c->nsn);
    if (c->fd)    aec_destroy(c->fd);
    free(c);
    return NULL;
}

/* ----- process ----------------------------------------------------------- */
static size_t fd_process(void *h, const int16_t *in, int16_t *out)
{
    fd_ctx_t *c = (fd_ctx_t *)h;
    int n = c->frame_samples, s;

    /* de-interleave the MR frame into planar mic / ref for the FD calls. */
    for (s = 0; s < n; ++s) {
        c->mic[s] = in[s * c->total_ch + c->mic_idx];
        c->ref[s] = in[s * c->total_ch + c->ref_idx];
    }

    /* shared FD linear front-end. */
    aec_linear_process(c->fd, c->mic, c->ref, c->residual);

    if (c->cfg == FD_CFG_B1) {
        /* FD NLP: residual -> nlp. */
        memcpy(c->nlp, c->residual, (size_t)n * sizeof(int16_t));
        aec_nlp_process(c->fd, c->nlp);
#if B1_BYPASS_NS
        /* ns_pro skipped entirely (see B1_BYPASS_NS): not created, not called,
         * no 160-sample reblock. Emit the NLP output directly. */
        fifo_push(&c->out_fifo, c->nlp, n);
#else
        /* reblock to ns_pro's 160-sample frames. */
        fifo_push(&c->nlp_fifo, c->nlp, n);
        while (c->nlp_fifo.count >= c->nspro_frame) {
            fifo_pop(&c->nlp_fifo, c->nsblk_in, c->nspro_frame);
            ns_process(c->nspro, c->nsblk_in, c->nsblk_out);
            fifo_push(&c->out_fifo, c->nsblk_out, c->nspro_frame);
        }
#endif
    } else if (c->cfg == FD_CFG_B2) {
        /* FD NLP, then esp nsnet2 deep NS, reblocked to the model chunksize. */
        memcpy(c->nlp, c->residual, (size_t)n * sizeof(int16_t));
        aec_nlp_process(c->fd, c->nlp);
        fifo_push(&c->nlp_fifo, c->nlp, n);
        while (c->nlp_fifo.count >= c->nsn_frame) {
            fifo_pop(&c->nlp_fifo, c->nsblk_in, c->nsn_frame);
            c->nsn_if->process(c->nsn, c->nsblk_in, c->nsblk_out);
            fifo_push(&c->out_fifo, c->nsblk_out, c->nsn_frame);
        }
    }

    /* emit exactly one FD chunk; pad with zeros during the reblock startup. */
    if (c->out_fifo.count >= n) {
        fifo_pop(&c->out_fifo, out, n);
    } else {
        memset(out, 0, (size_t)n * sizeof(int16_t));
    }
    return (size_t)n;
}

static int fd_chunksize(void *h) { return ((fd_ctx_t *)h)->frame_samples; }

static void fd_destroy(void *h)
{
    fd_ctx_t *c = (fd_ctx_t *)h;
    if (!c) return;
    if (c->mic) heap_caps_free(c->mic);
    if (c->ref) heap_caps_free(c->ref);
    if (c->residual) heap_caps_free(c->residual);
    if (c->nlp) heap_caps_free(c->nlp);
    if (c->nsblk_in) heap_caps_free(c->nsblk_in);
    if (c->nsblk_out) heap_caps_free(c->nsblk_out);
    fifo_free(&c->out_fifo); fifo_free(&c->nlp_fifo);
    if (c->nspro) ns_destroy(c->nspro);
    if (c->nsn && c->nsn_if) c->nsn_if->destroy(c->nsn);
    if (c->fd)    aec_destroy(c->fd);
    free(c);
}

/* ----- vtables ------------------------------------------------------------ */
/* A1 / A2 run entirely through the SeekAudio public API (seekaudio_aec_*); the
 * library performs the whole A-path pipeline internally. `type` selects the
 * denoise engine at runtime: NS ("A1") or AI ("A2"). */
static void *sa_a1_create(const char *fmt, int flen, int type)
{ (void)flen; (void)type; return (void *)seekaudio_aec_create(fmt, SEEKAUDIO_AEC_TYPE_NS); }
static void *sa_a2_create(const char *fmt, int flen, int type)
{ (void)flen; (void)type; return (void *)seekaudio_aec_create(fmt, SEEKAUDIO_AEC_TYPE_AI); }
static size_t sa_a_process(void *h, const int16_t *in, int16_t *out)
{ return seekaudio_aec_process((seekaudio_aec_t *)h, in, out); }
static int sa_a_chunksize(void *h)
{ return seekaudio_aec_get_chunksize((seekaudio_aec_t *)h); }
static void sa_a_destroy(void *h)
{ seekaudio_aec_destroy((seekaudio_aec_t *)h); }

static void *b1_create(const char *fmt, int flen, int type)
{ (void)type; return fd_create_cfg(fmt, flen, FD_CFG_B1); }
static void *b2_create(const char *fmt, int flen, int type)
{ (void)type; return fd_create_cfg(fmt, flen, FD_CFG_B2); }

extern "C" const aec_backend_t *fd_a1_backend(void)
{
    static const aec_backend_t vt = {
        "A1: SeekAudio AEC + NLP + WebRTC NS",
        sa_a1_create, sa_a_process, sa_a_chunksize, sa_a_destroy
    };
    return &vt;
}
extern "C" const aec_backend_t *fd_a2_backend(void)
{
    static const aec_backend_t vt = {
        "A2: SeekAudio AEC + NLP + AI Noise",
        sa_a2_create, sa_a_process, sa_a_chunksize, sa_a_destroy
    };
    return &vt;
}
extern "C" const aec_backend_t *fd_b1_backend(void)
{
    static const aec_backend_t vt = {
        "B1: FD-AEC + NLP + ns_pro",
        b1_create, fd_process, fd_chunksize, fd_destroy
    };
    return &vt;
}
extern "C" const aec_backend_t *fd_b2_backend(void)
{
    static const aec_backend_t vt = {
        "B2: FD-AEC + NLP + NSNet2",
        b2_create, fd_process, fd_chunksize, fd_destroy
    };
    return &vt;
}

#endif /* ESP_PLATFORM */
