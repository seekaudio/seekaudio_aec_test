/*
 * bench_port.c  --  benchmark harness platform layer, ESP-IDF implementation.
 *
 * Copyright (c) 2026 SeekAudio.  All rights reserved.
 */
#include "bench_port.h"

#include <stdarg.h>
#include <stdio.h>

#include "esp_timer.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

int64_t bench_time_us(void)
{
    return esp_timer_get_time();
}

void bench_heap_free(size_t *internal, size_t *spiram)
{
    if (internal) *internal = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    if (spiram)   *spiram   = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
}

size_t bench_min_free_stack(void)
{
    /* High-water mark = smallest free stack ever; words -> bytes. */
    return (size_t)uxTaskGetStackHighWaterMark(NULL) * sizeof(StackType_t);
}

void bench_log_info(const char *tag, const char *fmt, ...)
{
    char buf[256];
    va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof(buf), fmt, ap); va_end(ap);
    ESP_LOGI(tag, "%s", buf);
}
void bench_log_warn(const char *tag, const char *fmt, ...)
{
    char buf[256];
    va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof(buf), fmt, ap); va_end(ap);
    ESP_LOGW(tag, "%s", buf);
}
void bench_log_error(const char *tag, const char *fmt, ...)
{
    char buf[256];
    va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof(buf), fmt, ap); va_end(ap);
    ESP_LOGE(tag, "%s", buf);
}

void bench_yield(void)
{
    vTaskDelay(1);
}
