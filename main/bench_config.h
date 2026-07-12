/*
 * bench_config.h  --  benchmark configuration (all toggles in one place).
 *
 * Copyright (c) 2026 SeekAudio.  All rights reserved.
 *
 * Every macro can be overridden from the command line, e.g.:
 *   idf.py -DSA_TEST_ROBUSTNESS=0 -DRUN_B2=0 build
 * (idf.py -D sets a CMake cache variable; main/CMakeLists.txt forwards it as a
 *  compile definition. Cache variables are sticky -- pass =1 to re-enable, or
 *  idf.py fullclean.)
 */
#ifndef BENCH_CONFIG_H
#define BENCH_CONFIG_H

/* ==================== comparison configurations ====================
 * The four-config A/B benchmark. All four share the same linear AEC
 * front-end and differ only in the post stage (see fd_aec_backend.cpp). They
 * run sequentially in one boot and write one WAV each; disable individual
 * configs to shorten a run (e.g. B2 needs the srmodels.bin "model" partition
 * -- set RUN_B2=0 if not flashed).
 *
 *   A1  SeekAudio AEC + NLP + WebRTC NS          -> /littlefs/a1.wav
 *   A2  SeekAudio AEC + NLP + AI Noise           -> /littlefs/a2.wav
 *   B1  linear AEC + NLP + ns_pro (baseline)     -> /littlefs/b1.wav
 *   B2  linear AEC + NLP + NSNet2 (baseline)     -> /littlefs/b2.wav
 */
#ifndef RUN_A1
#define RUN_A1 1
#endif
#ifndef RUN_A2
#define RUN_A2 1
#endif
#ifndef RUN_B1
#define RUN_B1 1
#endif
#ifndef RUN_B2
#define RUN_B2 1
#endif

/* ==================== optional: SeekAudio full engine ====================
 * Extra config running the complete SeekAudio engine through the
 * seekaudio_aec_* public API. OFF by default; enable
 * with -DRUN_SA_FULL=1. SA_FULL_TYPE: 0 = NS denoise, 1 = AI denoise.
 */
#ifndef RUN_SA_FULL
#define RUN_SA_FULL 0
#endif
#ifndef SA_FULL_TYPE
#define SA_FULL_TYPE 1
#endif

/* ==================== robustness suite ====================
 * Black-box robustness checks on the SeekAudio engine (create time, leak
 * check, degenerate inputs). 1 = run after the benchmark; 0 = compiled out.
 *
 * DEFAULT 0 (off): the library shipped to customers is a VERSION_LIMIT build,
 * which caps successful re-inits per process (~10, process-global, reset only
 * by reboot) and has a date lock. The robustness suite does many
 * create/destroy cycles and WILL exceed that cap -> create() returns NULL and
 * the checks fail spuriously. Enable it only for INTERNAL validation, against a
 * library rebuilt with -DVERSION_LIMIT=0:  idf.py -DSA_TEST_ROBUSTNESS=1 build
 * To remove permanently: delete robustness_test.c and the one
 * robustness_run() call in aectest.cpp.
 */
#ifndef SA_TEST_ROBUSTNESS
#define SA_TEST_ROBUSTNESS 0
#endif

/* ==================== common parameters ==================== */

/* Adaptive-filter length hint (both engines recommend 4 on esp32s3). */
#ifndef AEC_FILTER_LEN
#define AEC_FILTER_LEN   4
#endif

/* Channel layout: interleaved [mic, ref]. */
#define AEC_INPUT_FORMAT "MR"

/* LittleFS audio paths (fs.img provides near.wav / far.wav). */
#define NEAR_END_FILE "/littlefs/near.wav"
#define FAR_END_FILE  "/littlefs/far.wav"
#define A1_OUTPUT_FILE "/littlefs/a1.wav"
#define A2_OUTPUT_FILE "/littlefs/a2.wav"
#define B1_OUTPUT_FILE "/littlefs/b1.wav"
#define B2_OUTPUT_FILE "/littlefs/b2.wav"
#define SA_FULL_OUTPUT_FILE "/littlefs/sa_full.wav"

#endif /* BENCH_CONFIG_H */
