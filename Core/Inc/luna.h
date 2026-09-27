//
// Created by project_author on 2026/3/11.
//

#ifndef LIDAR_LUNA_H
#define LIDAR_LUNA_H

#include "main.h"



enum {
    LIDAR_STATUS_OK = 0x00,
    LIDAR_STATUS_CHECKSUM_ERR = 0x01,
    LIDAR_STATUS_AMP_LOW = 0x02,
    LIDAR_STATUS_TOO_NEAR = 0x04,
    LIDAR_STATUS_ESTIMATED    = 0x08,
};



uint16_t luna_input(uint8_t *buffer, uint16_t size, uint16_t chunk_start_index, const LidarChunk *chunk, float motor_speed_rps);



#endif //LIDAR_LUNA_H