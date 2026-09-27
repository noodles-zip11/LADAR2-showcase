#ifndef LADAR2_DIAG_H
#define LADAR2_DIAG_H

#include "FreeRTOS.h"
#include "queue.h"
#include <stdint.h>

extern QueueHandle_t lidarChunkQueue;
extern QueueHandle_t lidarPointQueue;

extern float m1_speed;
extern uint8_t DMA_luna_buffer[64];

extern volatile uint32_t uart_chunk_drop_cnt;
extern volatile uint32_t uart_chunk_oversize_cnt;
extern volatile uint32_t parser_overflow_cnt;
extern volatile uint32_t lidar_point_drop_cnt;
extern volatile uint32_t checksum_fail_cnt;
extern volatile uint32_t amp_low_cnt;
extern volatile uint32_t too_near_cnt;
extern volatile uint32_t lidar_chunk_q_hwm;
extern volatile uint32_t lidar_point_q_hwm;

extern volatile uint32_t encoder_count32_snapshot;
extern volatile int32_t g_encoder_count32;
extern volatile uint16_t g_encoder_last16;
extern volatile uint8_t g_encoder_count32_valid;
extern volatile int32_t g_last_rev_id;
extern volatile uint32_t g_rev_transition_cnt;
extern volatile uint8_t g_speed_valid;

extern volatile uint32_t can_last_error_code;
extern volatile uint32_t can_error_irq_cnt;
extern volatile uint32_t can_bus_off_cnt;
extern volatile uint32_t can_recovery_cnt;
extern volatile uint32_t can_tx_ok_point_cnt;
extern volatile uint32_t can_tx_fail_point_cnt;
extern volatile uint32_t can_tx_fail_frame_cnt;

extern volatile uint32_t g_diag_tick_ms;
extern volatile float g_diag_target_speed_rps;
extern volatile float g_diag_actual_speed_rps;
extern volatile float g_diag_speed_error_rps;
extern volatile float g_diag_pwm_trim;
extern volatile float g_diag_pwm_cmd;

extern volatile uint32_t luna_frame_ok_cnt;
extern volatile uint32_t luna_header_skip_cnt;
extern volatile uint32_t luna_resync_cnt;
#endif
