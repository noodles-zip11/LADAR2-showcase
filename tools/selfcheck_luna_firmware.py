#!/usr/bin/env python3
"""
selfcheck_luna_firmware.py — Compile and run the real Core/Src/luna.c on host
with fake TF-Luna byte frames, validating counter and publish behaviour.

No production firmware files are modified. All generated C files live in a
temporary directory that is removed after the test finishes.
"""

import os
import shutil
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LUNA_C = os.path.join(REPO, "Core", "Src", "luna.c")
CORE_INC = os.path.join(REPO, "Core", "Inc")

# ---------------------------------------------------------------------------
# Stub headers (written into temp dir)
# ---------------------------------------------------------------------------
# Minimal HAL stub so that the real Core/Inc/main.h can include it without
# pulling in the entire STM32 HAL.  Only the types that main.h actually
# references (via stm32f4xx_hal.h) need typedefs here.
STM32F4XX_HAL_H = r"""\
#ifndef __STM32F4xx_HAL_H
#define __STM32F4xx_HAL_H

#include <stdint.h>
#include <stddef.h>

typedef enum { HAL_OK = 0, HAL_ERROR, HAL_BUSY, HAL_TIMEOUT } HAL_StatusTypeDef;

#endif /* __STM32F4xx_HAL_H */
"""

# This stub main.h replaces the real Core/Inc/main.h so we avoid dragging in
# any STM32 hardware headers.  Its struct/define values are copied verbatim
# from the production main.h to stay in sync with luna.c expectations.
MAIN_H = r"""\
#ifndef __MAIN_H
#define __MAIN_H

#include <stdint.h>

typedef struct {
    uint32_t t_sample_us;
    uint16_t angle_tick;
    float    angle_deg;
    uint16_t distance_cm;
    uint8_t  quality;
    uint8_t  status;
    float    tmp;
} lidar_point_t;

typedef struct {
    uint8_t       data[64];
    volatile uint16_t count;
    volatile uint8_t  ready;
    volatile uint32_t luna_chunk_rx_time_us;
    volatile uint16_t luna_rx_encoder_tick16;
    volatile int32_t  luna_rx_encoder_count32;
} LidarChunk;

#define ENC_PPR    7.0f
#define GEAR_RATIO 210.0f

#endif /* __MAIN_H */
"""

FREERTOS_H = r"""\
#ifndef INC_FREERTOS_H
#define INC_FREERTOS_H

#include <stdint.h>
typedef int32_t  BaseType_t;
typedef uint32_t UBaseType_t;
typedef uint32_t TickType_t;

#define pdPASS  1
#define pdFAIL  0

#endif /* INC_FREERTOS_H */
"""

QUEUE_H = r"""\
#ifndef QUEUE_H
#define QUEUE_H

#include "FreeRTOS.h"

typedef void* QueueHandle_t;

BaseType_t   xQueueSend(QueueHandle_t xQueue, const void *pvItemToQueue, TickType_t xTicksToWait);
UBaseType_t  uxQueueMessagesWaiting(QueueHandle_t xQueue);

#endif /* QUEUE_H */
"""

DIAG_H = r"""\
#ifndef LADAR2_DIAG_H
#define LADAR2_DIAG_H

#include "FreeRTOS.h"
#include "queue.h"
#include <stdint.h>

extern QueueHandle_t lidarChunkQueue;
extern QueueHandle_t lidarPointQueue;

extern volatile uint32_t lidar_point_drop_cnt;
extern volatile uint32_t checksum_fail_cnt;
extern volatile uint32_t luna_frame_ok_cnt;
extern volatile uint32_t luna_header_skip_cnt;
extern volatile uint32_t luna_resync_cnt;
extern volatile uint32_t amp_low_cnt;
extern volatile uint32_t too_near_cnt;
extern volatile uint32_t lidar_point_q_hwm;

extern volatile int32_t  g_last_rev_id;
extern volatile uint32_t g_rev_transition_cnt;
extern volatile uint8_t  g_speed_valid;

#endif /* LADAR2_DIAG_H */
"""

# ---------------------------------------------------------------------------
# Host test harness (C)
# ---------------------------------------------------------------------------
TEST_C = r"""\
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "luna.h"
#include "luna_protocol.h"
#include "diag.h"

/* ---- extern globals that luna.c references ---- */
QueueHandle_t lidarChunkQueue  = NULL;
QueueHandle_t lidarPointQueue  = (QueueHandle_t)1;

volatile uint32_t lidar_point_drop_cnt = 0;
volatile uint32_t checksum_fail_cnt    = 0;
volatile uint32_t luna_frame_ok_cnt    = 0;
volatile uint32_t luna_header_skip_cnt = 0;
volatile uint32_t luna_resync_cnt      = 0;
volatile uint32_t amp_low_cnt          = 0;
volatile uint32_t too_near_cnt         = 0;
volatile uint32_t lidar_point_q_hwm   = 0;

volatile int32_t  g_last_rev_id        = 0;
volatile uint32_t g_rev_transition_cnt = 0;
volatile uint8_t  g_speed_valid        = 0;

/* ---- publish tracking ---- */
static lidar_point_t g_last_published;
static int g_publish_count = 0;

/* ---- FreeRTOS stubs ---- */
BaseType_t xQueueSend(QueueHandle_t xQueue, const void *pvItemToQueue,
                      TickType_t xTicksToWait)
{
    (void)xQueue; (void)xTicksToWait;
    memcpy(&g_last_published, pvItemToQueue, sizeof(lidar_point_t));
    g_publish_count++;
    return pdPASS;
}

UBaseType_t uxQueueMessagesWaiting(QueueHandle_t xQueue)
{
    (void)xQueue;
    return (UBaseType_t)g_publish_count;
}

/* ---- helpers ---- */
static void reset_counters(void)
{
    lidar_point_drop_cnt = 0;
    checksum_fail_cnt    = 0;
    luna_frame_ok_cnt    = 0;
    luna_header_skip_cnt = 0;
    luna_resync_cnt      = 0;
    amp_low_cnt          = 0;
    too_near_cnt         = 0;
    lidar_point_q_hwm   = 0;
    g_last_rev_id        = 0;
    g_rev_transition_cnt = 0;
    g_speed_valid        = 0;
    g_publish_count      = 0;
    memset(&g_last_published, 0, sizeof(g_last_published));
}

enum {
    VALID_DISTANCE_CM = LUNA_MIN_DISTANCE_CM + 72U,
    VALID_AMP = LUNA_MIN_AMP + 100U,
    LOW_AMP = LUNA_MIN_AMP - 1U,
    TOO_NEAR_DISTANCE_CM = LUNA_MIN_DISTANCE_CM - 1U,
    NOISE_PREFIX_LEN = 3U,
};

static void put_u16_le(uint8_t *frame, uint8_t lo_index, uint16_t value)
{
    frame[lo_index] = (uint8_t)(value & 0xFFU);
    frame[lo_index + 1U] = (uint8_t)((value >> 8U) & 0xFFU);
}

/* Build a TF-Luna frame with correct checksum. */
static void make_frame(uint8_t frame[LUNA_FRAME_LEN], uint16_t distance_cm, uint16_t amp)
{
    memset(frame, 0, LUNA_FRAME_LEN);
    frame[LUNA_HEADER_0_INDEX] = LUNA_HEADER_0;
    frame[LUNA_HEADER_1_INDEX] = LUNA_HEADER_1;
    put_u16_le(frame, LUNA_DISTANCE_L_INDEX, distance_cm);
    put_u16_le(frame, LUNA_AMP_L_INDEX, amp);
    frame[LUNA_TEMP_L_INDEX] = 0U;
    frame[LUNA_TEMP_H_INDEX] = 0U;
    uint8_t sum = 0;
    for (int i = 0; i < (int)LUNA_CHECKSUM_LEN; i++)
        sum += frame[i];
    frame[LUNA_CHECKSUM_INDEX] = sum;
}

static LidarChunk make_chunk(const uint8_t *buf, uint16_t len)
{
    LidarChunk c;
    memset(&c, 0, sizeof(c));
    memcpy(c.data, buf, len);
    c.count = len;
    c.ready = 1;
    c.luna_chunk_rx_time_us = 1000000;
    c.luna_rx_encoder_count32 = 0;
    return c;
}

/* ---- test macros ---- */
#define ASSERT_EQ(a, b, msg) do {                                      \
    if ((a) != (b)) {                                                   \
        fprintf(stderr, "FAIL: %s — expected %d, got %d\n",            \
                msg, (int)(b), (int)(a));                                \
        return 1;                                                        \
    }                                                                    \
} while(0)

/* ---- test cases ---- */
static int test_normal_frame(void)
{
    reset_counters();
    uint8_t frame[LUNA_FRAME_LEN];
    make_frame(frame, VALID_DISTANCE_CM, VALID_AMP);

    LidarChunk chunk = make_chunk(frame, LUNA_FRAME_LEN);
    uint16_t consumed = luna_input(frame, LUNA_FRAME_LEN, 0, &chunk, 0.0f);

    ASSERT_EQ(consumed, LUNA_FRAME_LEN, "normal: consumed bytes");
    ASSERT_EQ(g_publish_count,    1, "normal: publish count");
    ASSERT_EQ(luna_frame_ok_cnt,  1, "normal: luna_frame_ok_cnt");
    ASSERT_EQ(checksum_fail_cnt,  0, "normal: checksum_fail_cnt");
    ASSERT_EQ(luna_header_skip_cnt, 0, "normal: luna_header_skip_cnt");
    ASSERT_EQ(luna_resync_cnt,    0, "normal: luna_resync_cnt");
    ASSERT_EQ(amp_low_cnt,        0, "normal: amp_low_cnt");
    ASSERT_EQ(too_near_cnt,       0, "normal: too_near_cnt");
    return 0;
}

static int test_checksum_error(void)
{
    reset_counters();
    uint8_t frame[LUNA_FRAME_LEN];
    make_frame(frame, VALID_DISTANCE_CM, VALID_AMP);
    frame[LUNA_CHECKSUM_INDEX] ^= 0xFF;  /* corrupt checksum */

    LidarChunk chunk = make_chunk(frame, LUNA_FRAME_LEN);
    luna_input(frame, LUNA_FRAME_LEN, 0, &chunk, 0.0f);

    ASSERT_EQ(checksum_fail_cnt,  1, "checksum_err: checksum_fail_cnt");
    ASSERT_EQ(luna_frame_ok_cnt,  0, "checksum_err: luna_frame_ok_cnt");
    ASSERT_EQ(luna_resync_cnt,    1, "checksum_err: luna_resync_cnt");
    ASSERT_EQ(g_publish_count,    0, "checksum_err: publish count");
    return 0;
}

static int test_amp_below_min(void)
{
    reset_counters();
    uint8_t frame[LUNA_FRAME_LEN];
    make_frame(frame, VALID_DISTANCE_CM, LOW_AMP);

    LidarChunk chunk = make_chunk(frame, LUNA_FRAME_LEN);
    luna_input(frame, LUNA_FRAME_LEN, 0, &chunk, 0.0f);

    ASSERT_EQ(amp_low_cnt,     1, "amp_below: amp_low_cnt");
    ASSERT_EQ(luna_frame_ok_cnt, 0, "amp_below: luna_frame_ok_cnt");
    ASSERT_EQ(g_publish_count, 0, "amp_below: publish count");
    return 0;
}

static int test_amp_invalid(void)
{
    reset_counters();
    uint8_t frame[LUNA_FRAME_LEN];
    make_frame(frame, VALID_DISTANCE_CM, LUNA_INVALID_AMP);

    LidarChunk chunk = make_chunk(frame, LUNA_FRAME_LEN);
    luna_input(frame, LUNA_FRAME_LEN, 0, &chunk, 0.0f);

    ASSERT_EQ(amp_low_cnt,     1, "amp_invalid: amp_low_cnt");
    ASSERT_EQ(luna_frame_ok_cnt, 0, "amp_invalid: luna_frame_ok_cnt");
    ASSERT_EQ(g_publish_count, 0, "amp_invalid: publish count");
    return 0;
}

static int test_too_near(void)
{
    reset_counters();
    uint8_t frame[LUNA_FRAME_LEN];
    make_frame(frame, TOO_NEAR_DISTANCE_CM, VALID_AMP);

    LidarChunk chunk = make_chunk(frame, LUNA_FRAME_LEN);
    luna_input(frame, LUNA_FRAME_LEN, 0, &chunk, 0.0f);

    ASSERT_EQ(too_near_cnt,    1, "too_near: too_near_cnt");
    ASSERT_EQ(luna_frame_ok_cnt, 0, "too_near: luna_frame_ok_cnt");
    ASSERT_EQ(g_publish_count, 0, "too_near: publish count");
    return 0;
}

static int test_mixed_buffer(void)
{
    reset_counters();
    uint8_t buf[LUNA_FRAME_LEN * 4U];

    /* frame 0: bad checksum */
    make_frame(buf + (LUNA_FRAME_LEN * 0U), VALID_DISTANCE_CM, VALID_AMP);
    buf[(LUNA_FRAME_LEN * 0U) + LUNA_CHECKSUM_INDEX] ^= 0xFF;

    /* frame 1: low amp */
    make_frame(buf + (LUNA_FRAME_LEN * 1U), VALID_DISTANCE_CM, LOW_AMP);

    /* frame 2: too near */
    make_frame(buf + (LUNA_FRAME_LEN * 2U), TOO_NEAR_DISTANCE_CM, VALID_AMP);

    /* frame 3: valid */
    make_frame(buf + (LUNA_FRAME_LEN * 3U), VALID_DISTANCE_CM, VALID_AMP);

    LidarChunk chunk = make_chunk(buf, LUNA_FRAME_LEN * 4U);
    luna_input(buf, LUNA_FRAME_LEN * 4U, 0, &chunk, 0.0f);

    ASSERT_EQ(checksum_fail_cnt, 1, "mixed: checksum_fail_cnt");
    ASSERT_EQ(luna_resync_cnt,   1, "mixed: luna_resync_cnt");
    ASSERT_EQ(amp_low_cnt,       1, "mixed: amp_low_cnt");
    ASSERT_EQ(too_near_cnt,      1, "mixed: too_near_cnt");
    ASSERT_EQ(g_publish_count,   1, "mixed: publish count");
    ASSERT_EQ(luna_frame_ok_cnt, 1, "mixed: luna_frame_ok_cnt");
    return 0;
}

static int test_noise_prefix_then_valid(void)
{
    reset_counters();
    uint8_t buf[NOISE_PREFIX_LEN + LUNA_FRAME_LEN];
    buf[0] = 0xAA;
    buf[1] = 0xBB;
    buf[2] = 0xCC;
    make_frame(buf + NOISE_PREFIX_LEN, VALID_DISTANCE_CM, VALID_AMP);

    LidarChunk chunk = make_chunk(buf, NOISE_PREFIX_LEN + LUNA_FRAME_LEN);
    uint16_t consumed = luna_input(buf, NOISE_PREFIX_LEN + LUNA_FRAME_LEN, 0, &chunk, 0.0f);

    ASSERT_EQ(g_publish_count, 1, "noise_prefix: publish count");
    ASSERT_EQ(luna_frame_ok_cnt, 1, "noise_prefix: luna_frame_ok_cnt");
    ASSERT_EQ(luna_header_skip_cnt, NOISE_PREFIX_LEN, "noise_prefix: luna_header_skip_cnt");
    ASSERT_EQ(luna_resync_cnt, 0, "noise_prefix: luna_resync_cnt");
    ASSERT_EQ(checksum_fail_cnt, 0, "noise_prefix: checksum_fail_cnt");
    ASSERT_EQ(consumed,       NOISE_PREFIX_LEN + LUNA_FRAME_LEN, "noise_prefix: consumed bytes");
    return 0;
}

static int test_checksum_error_then_valid_resync(void)
{
    reset_counters();
    uint8_t buf[LUNA_FRAME_LEN * 2U];

    make_frame(buf + (LUNA_FRAME_LEN * 0U), VALID_DISTANCE_CM, VALID_AMP);
    buf[LUNA_CHECKSUM_INDEX] ^= 0xFF;
    make_frame(buf + (LUNA_FRAME_LEN * 1U), VALID_DISTANCE_CM, VALID_AMP);

    LidarChunk chunk = make_chunk(buf, LUNA_FRAME_LEN * 2U);
    uint16_t consumed = luna_input(buf, LUNA_FRAME_LEN * 2U, 0, &chunk, 0.0f);

    ASSERT_EQ(checksum_fail_cnt, 1, "checksum_then_valid: checksum_fail_cnt");
    ASSERT_EQ(luna_resync_cnt,   1, "checksum_then_valid: luna_resync_cnt");
    ASSERT_EQ(g_publish_count,   1, "checksum_then_valid: publish count");
    ASSERT_EQ(luna_frame_ok_cnt, 1, "checksum_then_valid: luna_frame_ok_cnt");
    ASSERT_EQ(consumed,          LUNA_FRAME_LEN * 2U, "checksum_then_valid: consumed bytes");
    return 0;
}

static int test_false_header_then_valid_resync(void)
{
    reset_counters();
    uint8_t buf[NOISE_PREFIX_LEN + LUNA_FRAME_LEN];

    buf[0] = LUNA_HEADER_0;
    buf[1] = LUNA_HEADER_1;
    buf[2] = 0x00U;
    make_frame(buf + NOISE_PREFIX_LEN, VALID_DISTANCE_CM, VALID_AMP);

    LidarChunk chunk = make_chunk(buf, NOISE_PREFIX_LEN + LUNA_FRAME_LEN);
    uint16_t consumed = luna_input(buf, NOISE_PREFIX_LEN + LUNA_FRAME_LEN, 0, &chunk, 0.0f);

    ASSERT_EQ(checksum_fail_cnt, 1, "false_header: checksum_fail_cnt");
    ASSERT_EQ(luna_resync_cnt,   1, "false_header: luna_resync_cnt");
    ASSERT_EQ(g_publish_count,   1, "false_header: publish count");
    ASSERT_EQ(luna_frame_ok_cnt, 1, "false_header: luna_frame_ok_cnt");
    ASSERT_EQ(consumed,          NOISE_PREFIX_LEN + LUNA_FRAME_LEN, "false_header: consumed bytes");
    return 0;
}

static int test_split_frame_across_chunks(void)
{
    reset_counters();
    uint8_t frame[LUNA_FRAME_LEN];
    uint8_t parser_buffer[LUNA_FRAME_LEN];
    uint8_t parser_buffer_len = 0U;
    const uint8_t first_chunk_len = 4U;
    const uint8_t second_chunk_len = (uint8_t)(LUNA_FRAME_LEN - first_chunk_len);

    make_frame(frame, VALID_DISTANCE_CM, VALID_AMP);

    memcpy(parser_buffer, frame, first_chunk_len);
    parser_buffer_len = first_chunk_len;

    LidarChunk first_chunk = make_chunk(frame, first_chunk_len);
    uint16_t consumed = luna_input(parser_buffer, parser_buffer_len, 0, &first_chunk, 0.0f);

    ASSERT_EQ(consumed, 0, "split_frame: first chunk consumed bytes");
    ASSERT_EQ(g_publish_count, 0, "split_frame: first chunk publish count");
    ASSERT_EQ(luna_frame_ok_cnt, 0, "split_frame: first chunk luna_frame_ok_cnt");
    ASSERT_EQ(checksum_fail_cnt, 0, "split_frame: first chunk checksum_fail_cnt");
    ASSERT_EQ(luna_resync_cnt, 0, "split_frame: first chunk luna_resync_cnt");

    memcpy(parser_buffer + parser_buffer_len, frame + first_chunk_len, second_chunk_len);
    parser_buffer_len += second_chunk_len;

    LidarChunk second_chunk = make_chunk(frame + first_chunk_len, second_chunk_len);
    consumed = luna_input(parser_buffer, parser_buffer_len, first_chunk_len, &second_chunk, 0.0f);

    ASSERT_EQ(consumed, LUNA_FRAME_LEN, "split_frame: second chunk consumed bytes");
    ASSERT_EQ(g_publish_count, 1, "split_frame: publish count");
    ASSERT_EQ(luna_frame_ok_cnt, 1, "split_frame: luna_frame_ok_cnt");
    ASSERT_EQ(checksum_fail_cnt, 0, "split_frame: checksum_fail_cnt");
    ASSERT_EQ(luna_resync_cnt, 0, "split_frame: luna_resync_cnt");
    ASSERT_EQ(luna_header_skip_cnt, 0, "split_frame: luna_header_skip_cnt");
    return 0;
}

static int test_contiguous_normal_frames(void)
{
    reset_counters();
    uint8_t buf[LUNA_FRAME_LEN * 3U];

    make_frame(buf + (LUNA_FRAME_LEN * 0U), VALID_DISTANCE_CM, VALID_AMP);
    make_frame(buf + (LUNA_FRAME_LEN * 1U), VALID_DISTANCE_CM + 1U, VALID_AMP);
    make_frame(buf + (LUNA_FRAME_LEN * 2U), VALID_DISTANCE_CM + 2U, VALID_AMP);

    LidarChunk chunk = make_chunk(buf, LUNA_FRAME_LEN * 3U);
    uint16_t consumed = luna_input(buf, LUNA_FRAME_LEN * 3U, 0, &chunk, 0.0f);

    ASSERT_EQ(consumed, LUNA_FRAME_LEN * 3U, "contiguous: consumed bytes");
    ASSERT_EQ(g_publish_count, 3, "contiguous: publish count");
    ASSERT_EQ(luna_frame_ok_cnt, 3, "contiguous: luna_frame_ok_cnt");
    ASSERT_EQ(checksum_fail_cnt, 0, "contiguous: checksum_fail_cnt");
    ASSERT_EQ(luna_resync_cnt, 0, "contiguous: luna_resync_cnt");
    ASSERT_EQ(luna_header_skip_cnt, 0, "contiguous: luna_header_skip_cnt");
    return 0;
}

/* ---- runner ---- */
int main(void)
{
    int failures = 0;
    const struct { const char *name; int (*fn)(void); } tests[] = {
        {"normal_frame",             test_normal_frame},
        {"checksum_error",           test_checksum_error},
        {"amp_below_min",            test_amp_below_min},
        {"amp_invalid",              test_amp_invalid},
        {"too_near",                 test_too_near},
        {"mixed_buffer",             test_mixed_buffer},
        {"noise_prefix_then_valid",  test_noise_prefix_then_valid},
        {"checksum_error_then_valid_resync", test_checksum_error_then_valid_resync},
        {"false_header_then_valid_resync", test_false_header_then_valid_resync},
        {"split_frame_across_chunks", test_split_frame_across_chunks},
        {"contiguous_normal_frames", test_contiguous_normal_frames},
    };

    for (int i = 0; i < (int)(sizeof(tests)/sizeof(tests[0])); i++) {
        int rc = tests[i].fn();
        if (rc != 0) {
            fprintf(stderr, "  -> failed test: %s\n", tests[i].name);
            failures++;
        }
    }

    if (failures) {
        fprintf(stderr, "FAIL: %d test(s) failed\n", failures);
        return 1;
    }
    printf("PASS: selfcheck_luna_firmware\n");
    return 0;
}
"""

# ---------------------------------------------------------------------------
# Compiler discovery
# ---------------------------------------------------------------------------
def find_cc():
    """Return a host C compiler command, or abort."""
    def add_runtime_path(cc_path):
        if (sys.platform == "win32" or os.name == "nt") and cc_path:
            cc_dir = os.path.dirname(os.path.abspath(cc_path))
            path_parts = os.environ.get("PATH", "").split(os.pathsep)
            if cc_dir and cc_dir not in path_parts:
                os.environ["PATH"] = cc_dir + os.pathsep + os.environ.get("PATH", "")
        return cc_path

    # 1) Explicit CC env var
    cc = os.environ.get("CC")
    if cc and shutil.which(cc):
        return add_runtime_path(shutil.which(cc) or cc)
    # 2) PATH lookup
    for candidate in ("gcc", "clang", "cc"):
        path = shutil.which(candidate)
        if path:
            return add_runtime_path(path)
    # 3) Probe common MinGW locations on Windows
    if sys.platform == "win32" or os.name == "nt":
        _common_gcc_dirs = [
            r"C:\msys64\mingw64\bin",
            r"C:\mingw64\bin",
            r"C:\MinGW\bin",
            r"C:\TDM-GCC-64\bin",
        ]
        # JetBrains IDEs bundle MinGW
        import glob as _glob
        for p in sorted(_glob.glob(r"C:\Program Files\JetBrains\*\bin\mingw\bin"), reverse=True):
            _common_gcc_dirs.insert(0, p)
        for d in _common_gcc_dirs:
            g = os.path.join(d, "gcc.exe")
            if os.path.isfile(g):
                return add_runtime_path(g)
    print("FAIL: no host C compiler found (tried CC env, gcc, clang, cc)",
          file=sys.stderr)
    print("      Set the CC environment variable to your compiler path.",
          file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    tmpdir = tempfile.mkdtemp(prefix="luna_selfcheck_")
    try:
        # Write stub headers
        with open(os.path.join(tmpdir, "stm32f4xx_hal.h"), "w") as f: f.write(STM32F4XX_HAL_H)
        with open(os.path.join(tmpdir, "main.h"),           "w") as f: f.write(MAIN_H)
        with open(os.path.join(tmpdir, "FreeRTOS.h"),       "w") as f: f.write(FREERTOS_H)
        with open(os.path.join(tmpdir, "queue.h"),          "w") as f: f.write(QUEUE_H)
        with open(os.path.join(tmpdir, "diag.h"),           "w") as f: f.write(DIAG_H)

        # Write test harness
        test_c_path = os.path.join(tmpdir, "luna_host_test.c")
        with open(test_c_path, "w") as f:
            f.write(TEST_C)

        # Output binary
        exe = os.path.join(tmpdir, "luna_selfcheck")

        cc = find_cc()

        cmd = [
            cc,
            "-std=c11",
            "-Wall", "-Wextra", "-Wno-unused-parameter",
            "-I", tmpdir,        # stub headers first (override real ones)
            "-I", CORE_INC,      # then real project headers (luna.h, luna_protocol.h)
            LUNA_C,
            test_c_path,
            "-o", exe,
            "-lm",
        ]

        # Compile
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print("FAIL: compilation error", file=sys.stderr)
            print(result.stdout, file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            sys.exit(1)

        # Run
        result = subprocess.run([exe], capture_output=True, text=True)
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        sys.exit(result.returncode)

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
