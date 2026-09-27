//
// Created by project_author on 2026/4/26.
//

#ifndef LIDAR_LUNA_PROTOCOL_H
#define LIDAR_LUNA_PROTOCOL_H

#define LUNA_HEADER_0              0x59U
#define LUNA_HEADER_1              0x59U

#define LUNA_FRAME_LEN             9U
#define LUNA_CHECKSUM_LEN          (LUNA_FRAME_LEN - 1U)
#define LUNA_CHECKSUM_INDEX        (LUNA_FRAME_LEN - 1U)

#define LUNA_HEADER_0_INDEX        0U
#define LUNA_HEADER_1_INDEX        1U
#define LUNA_DISTANCE_L_INDEX      2U
#define LUNA_DISTANCE_H_INDEX      3U
#define LUNA_AMP_L_INDEX           4U
#define LUNA_AMP_H_INDEX           5U
#define LUNA_TEMP_L_INDEX          6U
#define LUNA_TEMP_H_INDEX          7U

#define LUNA_MIN_AMP               100U
#define LUNA_INVALID_AMP           65535U
#define LUNA_MIN_DISTANCE_CM       28U

#define LUNA_US_PER_SECOND_F       1000000.0f


#define UART_CHAR_US         87U
#define UART_IDLE_GUARD_US   87U

#endif //LIDAR_LUNA_PROTOCOL_H
