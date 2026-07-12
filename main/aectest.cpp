/*
 * aectest.cpp  --  SeekAudio AEC on-device benchmark (ESP32-S3, prebuilt lib).
 *
 * Copyright (c) 2026 SeekAudio.  All rights reserved.
 *
 * Flow: mount littlefs -> load near.wav / far.wav into PSRAM -> run the four
 * comparison configs (A1/A2/B1/B2, see bench_config.h) through the shared
 * aec_runner so timing / memory / quality metrics are measured identically ->
 * write one output WAV per config back to littlefs -> optional robustness
 * suite on the SeekAudio engine.
 *
 * Compute time excludes file I/O (aec_runner times only process()).
 * Read the outputs back over USB/UART with esptool read_flash + littlefs
 * extract (see README.md), then compare offline with tools/aec_quality_report.py.
 */
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "sdkconfig.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_littlefs.h"
#include "esp_heap_caps.h"

#include "wave_file.h"
#include "aec_runner.h"
#include "bench_config.h"
#include "seekaudio_aec.h"     /* SEEKAUDIO_AEC_TYPE_NS / _AI + version string */

static const char *TAG = "AEC_BENCH";

extern "C" const aec_backend_t *fd_a1_backend(void);
extern "C" const aec_backend_t *fd_a2_backend(void);
extern "C" const aec_backend_t *fd_b1_backend(void);
extern "C" const aec_backend_t *fd_b2_backend(void);
extern "C" const aec_backend_t *seekaudio_backend(void);   /* RUN_SA_FULL */
#if SA_TEST_ROBUSTNESS
extern "C" void robustness_run(const int16_t *near, const int16_t *far,
                               size_t mono_samples);
#endif

/* ---------------- LittleFS + WAV load (PSRAM) ----------------------------- */
static esp_err_t init_littlefs(void)
{
    esp_vfs_littlefs_conf_t conf = {};
    conf.base_path = "/littlefs";
    conf.partition_label = "storage";
    conf.format_if_mount_failed = true;
    return esp_vfs_littlefs_register(&conf);
}

static esp_err_t read_wav_psram(const char *path, int16_t **buf,
                                size_t *samples, uint32_t *sr)
{
    WavReader r;
    if (!r.Open(path)) { ESP_LOGE(TAG, "open %s failed", path); return ESP_FAIL; }
    if (r.Channels() != 1 || r.BitsPerSample() != 16 || r.SampleRate() != 16000) {
        ESP_LOGE(TAG, "%s: need mono/16-bit/16k", path); r.Close(); return ESP_FAIL;
    }
    *sr = r.SampleRate();
    size_t n = r.Length();
    *buf = (int16_t *)heap_caps_malloc(n * sizeof(int16_t), MALLOC_CAP_SPIRAM);
    if (!*buf) { r.Close(); return ESP_ERR_NO_MEM; }
    int rd = r.Read(*buf, (int)n);
    r.Close();
    *samples = (rd > 0) ? (size_t)rd : 0;
    /* RMS level at load time: catches silent / wrong test material immediately
     * (a far.wav of digital silence makes every echo metric meaningless). */
    {
        double acc = 0.0;
        for (size_t i = 0; i < *samples; ++i) {
            double v = (double)(*buf)[i];
            acc += v * v;
        }
        double rms = (*samples > 0) ? sqrt(acc / (double)*samples) : 0.0;
        if (rms > 0.0) {
            ESP_LOGI(TAG, "loaded %s: %zu samples @ %u Hz, RMS %.1f dBFS",
                     path, *samples, *sr, 20.0 * log10(rms / 32768.0));
        } else {
            ESP_LOGW(TAG, "loaded %s: %zu samples @ %u Hz, ALL ZERO (silent!)",
                     path, *samples, *sr);
        }
    }
    return ESP_OK;
}

/* ---------------- benchmark config table ---------------------------------- */
typedef struct {
    int          enabled;
    const aec_backend_t *(*backend)(void);
    int          type;          /* passed to backend->create()                */
    const char  *out_path;
} bench_cfg_t;

/* ---------------- app_main ------------------------------------------------ */
extern "C" void app_main(void)
{
    /* ---- license / authorization banner (printed first) ---- */
    ESP_LOGI(TAG, "==========================================================");
    ESP_LOGI(TAG, " SeekAudio AEC - EVALUATION LIBRARY (for testing only)");
    ESP_LOGI(TAG, " This library is provided for evaluation/testing only.");
    ESP_LOGI(TAG, " Commercial use requires authorization. To license for");
    ESP_LOGI(TAG, " commercial use, please contact the vendor.");
    ESP_LOGI(TAG, " Website: https://www.seekaudio.cn/");
    ESP_LOGI(TAG, "==========================================================");

    ESP_LOGI(TAG, "%s", "SeekAudio AEC benchmark start");
    ESP_LOGI(TAG, "library version: %s", seekaudio_aec_get_version());
    ESP_LOGI(TAG, "free PSRAM: %zu, free internal RAM: %zu",
             heap_caps_get_free_size(MALLOC_CAP_SPIRAM),
             heap_caps_get_free_size(MALLOC_CAP_INTERNAL));

    if (init_littlefs() != ESP_OK) { ESP_LOGE(TAG, "littlefs failed"); return; }

    int16_t *near = NULL, *far = NULL, *out = NULL;
    size_t near_n = 0, far_n = 0, out_n = 0;
    uint32_t near_sr = 0, far_sr = 0;
    size_t mono = 0;

    if (read_wav_psram(NEAR_END_FILE, &near, &near_n, &near_sr) != ESP_OK) goto cleanup;
    if (read_wav_psram(FAR_END_FILE,  &far,  &far_n,  &far_sr)  != ESP_OK) goto cleanup;
    if (near_sr != far_sr) { ESP_LOGE(TAG, "sr mismatch"); goto cleanup; }

    mono = (near_n < far_n) ? near_n : far_n;
    out = (int16_t *)heap_caps_malloc(mono * sizeof(int16_t), MALLOC_CAP_SPIRAM);
    if (!out) { ESP_LOGE(TAG, "out alloc failed"); goto cleanup; }

    {
        const bench_cfg_t cfgs[] = {
            { RUN_A1,      fd_a1_backend,     0,            A1_OUTPUT_FILE },
            { RUN_A2,      fd_a2_backend,     0,            A2_OUTPUT_FILE },
            { RUN_B1,      fd_b1_backend,     0,            B1_OUTPUT_FILE },
            { RUN_B2,      fd_b2_backend,     0,            B2_OUTPUT_FILE },
            { RUN_SA_FULL, seekaudio_backend, SA_FULL_TYPE, SA_FULL_OUTPUT_FILE },
        };
        static const char *cfg_names[] = {
            "A1: SeekAudio AEC + NLP + WebRTC NS",
            "A2: SeekAudio AEC + NLP + AI Noise",
            "B1: FD-AEC + NLP + ns_pro",
            "B2: FD-AEC + NLP + NSNet2",
            "SA-FULL: SeekAudio full engine",
        };

        for (int ci = 0; ci < (int)(sizeof(cfgs) / sizeof(cfgs[0])); ++ci) {
            if (!cfgs[ci].enabled) {
                ESP_LOGW(TAG, "%s: disabled (RUN_xx=0), skipped", cfg_names[ci]);
                continue;
            }
            const aec_backend_t *backend = cfgs[ci].backend();
            if (!backend) continue;

            ESP_LOGI(TAG, "================ %s ================", cfg_names[ci]);
            aec_run_stats_t stats;
            out_n = 0;
            if (aec_run(backend, AEC_INPUT_FORMAT, AEC_FILTER_LEN, cfgs[ci].type,
                        near, far, mono, (int)near_sr, out, &out_n, &stats) != 0) {
                /* B2 typically fails here when the "model" partition (nsnet2
                 * weights) is not flashed; the other configs are unaffected. */
                ESP_LOGE(TAG, "aec_run failed: %s (skipped)", cfg_names[ci]);
                continue;
            }
            aec_run_print_stats(&stats);
            ESP_LOGI(TAG, "main_task stack: min free = %u bytes (of %d)",
                     (unsigned)(uxTaskGetStackHighWaterMark(NULL) * sizeof(StackType_t)),
                     CONFIG_ESP_MAIN_TASK_STACK_SIZE);

            WavWriter w;
            if (w.Open(cfgs[ci].out_path, (int)near_sr, 1, 16, FormatTag_PCM)) {
                w.Write(out, (int)out_n);
                w.Close();
                ESP_LOGI(TAG, "saved %s (%zu samples)", cfgs[ci].out_path, out_n);
            } else {
                ESP_LOGE(TAG, "open %s for write failed", cfgs[ci].out_path);
            }
        }
    }

#if SA_TEST_ROBUSTNESS
    robustness_run(near, far, mono);
#endif

cleanup:
    if (near) heap_caps_free(near);
    if (far)  heap_caps_free(far);
    if (out)  heap_caps_free(out);
    esp_vfs_littlefs_unregister("storage");
    ESP_LOGI(TAG, "%s", "SeekAudio AEC benchmark end");
}
