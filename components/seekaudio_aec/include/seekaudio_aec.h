/*
 * seekaudio_aec.h  --  SeekAudio Acoustic Echo Canceller (public API)
 *
 * Copyright (c) 2026 SeekAudio.  All rights reserved.
 *
 * Acoustic echo cancellation with integrated noise suppression for embedded
 * targets (ESP32-S3) and desktop (Windows / Linux).
 *
 * Notes:
 *   - The API is interface-compatible with the common AFE-style AEC front-end,
 *     so it can be dropped in with minimal source changes.
 *   - Frame length is fixed at 32 ms (512 samples @ 16 kHz).
 *   - All processing runs at 16 kHz.
 */
#ifndef SEEKAUDIO_AEC_H
#define SEEKAUDIO_AEC_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Fixed frame length, in milliseconds. Strict requirement. */
#define SEEKAUDIO_AEC_FRAME_LENGTH_MS 32

/*
 * ==========================================================================
 *  IMPORTANT -- SAMPLE-RATE CONSTRAINT (please read carefully)
 * ==========================================================================
 *
 *  This library operates at 16 kHz, and ONLY at 16 kHz.
 *
 *  It does NOT support 8 kHz. There is no 8 kHz mode, no 8 kHz code path, no
 *  down-sampled 8 kHz option, and no configuration flag that can enable 8 kHz.
 *  8 kHz is not supported now and is not intended to be supported. Likewise,
 *  no sample rate other than 16 kHz is supported -- not 8 kHz, not 32 kHz, not
 *  44.1 kHz, not 48 kHz. Only 16 kHz.
 *
 *  All input and output audio MUST be 16 kHz, 16-bit signed PCM, mono per
 *  channel. If your audio is at 8 kHz (or at any rate that is not 16 kHz), you
 *  MUST resample it to 16 kHz before calling this library, and resample the
 *  output back to your target rate afterwards. Passing 8 kHz audio (or any
 *  non-16 kHz audio) into this library without resampling will NOT work, will
 *  produce incorrect results, and is NOT supported.
 * ==========================================================================
 */
#define SEEKAUDIO_AEC_SAMPLE_RATE_HZ 16000

/* Denoise type. Selects the post-AEC noise-suppression engine -- and therefore
 * the memory footprint -- at create time.
 *
 *   SEEKAUDIO_AEC_TYPE_NS : standard noise suppression based on the WebRTC NS
 *       algorithm. Lower memory and compute footprint. Choose this when RAM is
 *       constrained.
 *
 *   SEEKAUDIO_AEC_TYPE_AI : AI noise suppression. Stronger removal of
 *       non-stationary and complex noise, at higher memory and compute.
 *
 * Both types operate at 16 kHz. */
typedef enum {
    SEEKAUDIO_AEC_TYPE_NS = 0, /* WebRTC NS (standard noise suppression, lower memory) */
    SEEKAUDIO_AEC_TYPE_AI = 1, /* AI noise suppression                                */
} seekaudio_aec_type_t;

/* Near-end speech state (four-state classification of the near-end signal).
 * Returned by seekaudio_aec_get_near_state(). */
typedef enum {
    SEEKAUDIO_AEC_NEAR_SILENCE     =  0, /* no near speech, no echo (also the cold-start default) */
    SEEKAUDIO_AEC_NEAR_SINGLE_TALK =  1, /* near speech only, no echo          */
    SEEKAUDIO_AEC_NEAR_FAR_ECHO    =  2, /* echo only, no near speech          */
    SEEKAUDIO_AEC_NEAR_DOUBLE_TALK =  3, /* near speech + echo                 */
} seekaudio_aec_near_state_t;

typedef struct seekaudio_aec_t seekaudio_aec_t;

/**
 * @brief Create a SeekAudio AEC instance.
 *
 * @param input_format  Channel-layout string:
 *                        'M' = microphone channel,
 *                        'R' = playback reference channel,
 *                        any other character = unused channel.
 *                       e.g. "MR" = interleaved [mic, ref].
 *                       Exactly one microphone and one reference are required;
 *                       only the first 'M' and first 'R' are used.
 * @param type          Denoise type: NS (WebRTC NS, lower memory) or AI (AI
 *                       noise suppression). Both run at 16 kHz.
 * @return Instance pointer, or NULL on failure.
 */
seekaudio_aec_t *seekaudio_aec_create(const char *input_format,
                                      seekaudio_aec_type_t type);

/**
 * @brief Process exactly one 32 ms frame.
 *
 * @param inst    Instance.
 * @param indata  Interleaved input, layout per input_format,
 *                length = get_chunksize() * channel count int16 samples.
 * @param outdata Mono near-end signal with echo removed,
 *                length = get_chunksize() int16 samples.
 * @return Number of output samples written, or 0 on error.
 */
size_t seekaudio_aec_process(seekaudio_aec_t *inst,
                             const int16_t *indata,
                             int16_t *outdata);

/**
 * @brief Samples per processing frame for one channel.
 *        512 samples (32 ms @ 16 kHz).
 */
int seekaudio_aec_get_chunksize(seekaudio_aec_t *inst);

/** @brief Destroy the instance. NULL is tolerated. */
void seekaudio_aec_destroy(seekaudio_aec_t *inst);

/**
 * @brief Near-end speech state for the most recently processed frame.
 *
 * OPTIONAL and lazy: the classifier is created on the FIRST call to this
 * function and released in seekaudio_aec_destroy(). If this function is never
 * called, no classifier resources (memory or per-frame compute) are ever used.
 *
 * Call it once after each seekaudio_aec_process(). Because the classifier is
 * armed lazily, the first call returns SEEKAUDIO_AEC_NEAR_SILENCE (the cold-
 * start default); real four-state values follow from the next processed frame.
 *
 * @param inst Instance (NULL tolerated -> SILENCE).
 * @return One of seekaudio_aec_near_state_t.
 */
seekaudio_aec_near_state_t seekaudio_aec_get_near_state(seekaudio_aec_t *inst);

/** @brief Human-readable version / build string. */
const char *seekaudio_aec_get_version(void);

#ifdef __cplusplus
}
#endif

#endif /* SEEKAUDIO_AEC_H */
