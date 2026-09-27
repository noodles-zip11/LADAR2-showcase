//
// Created by project_author on 2026/3/11.
//

#include "luna.h"
#include "luna_protocol.h"
#include "diag.h"
#include "main.h"
#include "FreeRTOS.h"
#include "queue.h"




static volatile int32_t g_zero_offset_count32 = 0;
static volatile uint8_t g_zero_offset_valid = 0;

typedef struct {
    uint16_t distance_cm;
    uint16_t amp;
    float tmp;
}LunaRawFrame;

typedef struct
{
    uint32_t t_sample_us;
    uint16_t angle_tick;
    uint8_t status;
} LunaPoseEstimate;

typedef enum
{
    LUNA_PARSE_SEARCH_HEADER = 0,
    LUNA_PARSE_VERIFY_FRAME,
    LUNA_PARSE_DECODE_FRAME,
    LUNA_PARSE_OUTPUT_POINT
} LunaParseState;



static float angle_from_tick(uint16_t tick)
{
    const uint32_t counts_per_rev = (uint32_t)(ENC_PPR * GEAR_RATIO * 4.0f);
    uint32_t current_count = tick % counts_per_rev;

    return ((float)current_count / (float)counts_per_rev) * 360.0f;
}


static int32_t fold_count32_to_rev(int32_t count32, int32_t counts_per_rev)
{
    int32_t mod = count32 % counts_per_rev;
    if (mod < 0)
    {
        mod += counts_per_rev;
    }
    return mod;
}

static int32_t floor_div_i32(int32_t num, int32_t den)
{
    int32_t q = num / den;
    int32_t r = num % den;
    if ((r != 0) && ((r > 0) != (den > 0)))
    {
        q--;
    }
    return q;
}

static int32_t rev_id_from_count32(int32_t sample_count32, int32_t zero_offset, int32_t counts_per_rev)
{
    return floor_div_i32(sample_count32 - zero_offset, counts_per_rev);
}


static uint8_t luna_is_frame_header(const uint8_t *buffer,uint16_t index)
{
    return (buffer[index + LUNA_HEADER_0_INDEX] == LUNA_HEADER_0 &&
            buffer[index + LUNA_HEADER_1_INDEX] == LUNA_HEADER_1);
}

static uint8_t luna_checksum_ok(const uint8_t *frame)
{
    uint8_t sum = 0U ;
    for (uint8_t i = 0U; i < LUNA_CHECKSUM_LEN; i++)
    {
        sum += frame[i];
    }
    return sum == frame[LUNA_CHECKSUM_INDEX];
}


static LunaRawFrame luna_decode_raw_frame(const uint8_t *frame)
{
    LunaRawFrame raw;
    raw.distance_cm = (uint16_t)(
        frame[LUNA_DISTANCE_L_INDEX] |
        (frame[LUNA_DISTANCE_H_INDEX] << 8U));
    raw.amp = (uint16_t)(
        frame[LUNA_AMP_L_INDEX] |
        (frame[LUNA_AMP_H_INDEX] << 8U));
    raw.tmp = ((float)(
        frame[LUNA_TEMP_L_INDEX] |
        (frame[LUNA_TEMP_H_INDEX] << 8U)) / 8.0f) - 256.0f;
    return raw;
}

static uint8_t luna_raw_frame_valid(const LunaRawFrame *raw)
{
    if (raw->amp < LUNA_MIN_AMP || raw->amp == LUNA_INVALID_AMP)
    {
        amp_low_cnt++;
        return 0U;
    }
    if (raw->distance_cm < LUNA_MIN_DISTANCE_CM)
    {
        too_near_cnt++;
        return 0U;
    }
    return 1U;
}

static LunaPoseEstimate luna_estimate_pose(uint16_t frame_index,uint16_t chunk_start_index,const LidarChunk *chunk,float motor_speed_rps,int32_t counts_per_rev)
{
    LunaPoseEstimate pose;
    int32_t sample_count32;

    pose.t_sample_us = 0U;
    pose.angle_tick = 0U;
    pose.status = LIDAR_STATUS_OK;

    if(frame_index >= chunk_start_index && g_speed_valid != 0U )
    {

        uint16_t frame_end_in_chunk = (uint16_t)((frame_index + LUNA_CHECKSUM_INDEX) - chunk_start_index);
        uint32_t bytes_after = (uint32_t)((chunk->count - 1U) - frame_end_in_chunk);
        uint32_t frame_end_us = chunk->luna_chunk_rx_time_us- UART_IDLE_GUARD_US- (bytes_after * UART_CHAR_US);

        pose.t_sample_us = frame_end_us - ((LUNA_FRAME_LEN * UART_CHAR_US) / 2U);


        float ticks_per_us = (motor_speed_rps * (float)counts_per_rev) / LUNA_US_PER_SECOND_F;
        float dt_us = (float)(chunk->luna_chunk_rx_time_us - pose.t_sample_us);
        float backtrack_f = ticks_per_us * dt_us;
        int32_t backtrack_ticks;

        if (backtrack_f >= 0.0f)
        {
            backtrack_ticks = (int32_t)(backtrack_f + 0.5f);
        }
        else
        {
            backtrack_ticks = (int32_t)(backtrack_f - 0.5f);
        }

        sample_count32 = chunk->luna_rx_encoder_count32 - backtrack_ticks;

        if (g_zero_offset_valid == 0U)
        {
            g_zero_offset_count32 = sample_count32;
            g_last_rev_id = 0;
            g_zero_offset_valid = 1U;
        }

        int32_t rev_id = rev_id_from_count32(sample_count32,g_zero_offset_count32,counts_per_rev);

        if (rev_id != g_last_rev_id)
        {
            g_rev_transition_cnt++;
            g_last_rev_id = rev_id;
        }

        pose.angle_tick = (uint16_t)fold_count32_to_rev(sample_count32 - g_zero_offset_count32,counts_per_rev);
        pose.status |= LIDAR_STATUS_ESTIMATED;
    }
    else
    {

        sample_count32 = chunk->luna_rx_encoder_count32;

        if (g_zero_offset_valid == 0U)
        {
            g_zero_offset_count32 = sample_count32;
            g_last_rev_id = 0;
            g_zero_offset_valid = 1U;
        }

        int32_t rev_id = rev_id_from_count32(sample_count32,g_zero_offset_count32,counts_per_rev);

        if (rev_id != g_last_rev_id)
        {
            g_rev_transition_cnt++;
            g_last_rev_id = rev_id;
        }

        pose.t_sample_us = chunk->luna_chunk_rx_time_us - ((LUNA_FRAME_LEN * UART_CHAR_US) / 2U);
        pose.angle_tick = (uint16_t)fold_count32_to_rev(sample_count32 - g_zero_offset_count32,counts_per_rev);
        pose.status |=  LIDAR_STATUS_ESTIMATED;
    }
    return pose;
}


static lidar_point_t luna_make_point(const LunaRawFrame *raw, const LunaPoseEstimate *pose)
{
    lidar_point_t point;
    point.t_sample_us = pose->t_sample_us;
    point.angle_tick = pose->angle_tick;
    point.angle_deg = angle_from_tick(point.angle_tick);
    point.distance_cm = raw->distance_cm;
    point.quality = (raw->amp > 255U) ? 255U : (uint8_t)raw->amp;
    point.status = pose->status;
    point.tmp = raw->tmp;
    return point;
}

static void luna_publish_point(const lidar_point_t *point)
{
    if (xQueueSend(lidarPointQueue, point, 0) != pdPASS)
    {
        lidar_point_drop_cnt++;
    }
    else
    {
        luna_frame_ok_cnt++;
        UBaseType_t depth = uxQueueMessagesWaiting(lidarPointQueue);
        if ((uint32_t)depth > lidar_point_q_hwm)
        {
            lidar_point_q_hwm = (uint32_t)depth;
        }
    }
}



uint16_t luna_input(uint8_t *buffer, uint16_t size, uint16_t chunk_start_index, const LidarChunk *chunk, float motor_speed_rps)
{
    int i = 0;
    LunaParseState state = LUNA_PARSE_SEARCH_HEADER;
    const int32_t counts_per_rev = (int32_t)(ENC_PPR * GEAR_RATIO * 4.0f);

    const uint8_t *frame = NULL ;
    LunaRawFrame raw ;
    LunaPoseEstimate pose;
    lidar_point_t lidar_points;

    while (size >= (uint16_t)(i + LUNA_FRAME_LEN))
    {
        switch (state)
        {
        case LUNA_PARSE_SEARCH_HEADER:
            if (luna_is_frame_header(buffer, (uint16_t)i) == 0U)
            {
                i++;
                luna_header_skip_cnt++;
            }
            else
            {
                frame = &buffer[i];
                state = LUNA_PARSE_VERIFY_FRAME;
            }
            break;

        case LUNA_PARSE_VERIFY_FRAME:
            if (luna_checksum_ok(frame) == 0U)
            {
                checksum_fail_cnt++;
                luna_resync_cnt++;
                i++;
                state = LUNA_PARSE_SEARCH_HEADER;
            }
            else
            {
                state = LUNA_PARSE_DECODE_FRAME;
            }
            break;
        case LUNA_PARSE_DECODE_FRAME:

            raw = luna_decode_raw_frame(frame);

            if (luna_raw_frame_valid(&raw) == 0U)
            {
                i += LUNA_FRAME_LEN;
                state = LUNA_PARSE_SEARCH_HEADER;
            }
            else
            {
                state = LUNA_PARSE_OUTPUT_POINT;
            }
            break;

        case LUNA_PARSE_OUTPUT_POINT:
            pose = luna_estimate_pose((uint16_t)i,chunk_start_index,chunk,motor_speed_rps,counts_per_rev);
            lidar_points = luna_make_point(&raw, &pose);
            luna_publish_point(&lidar_points);
            i += LUNA_FRAME_LEN;
            state = LUNA_PARSE_SEARCH_HEADER;
            break;
        }
    }
    return (uint16_t)i;
}
