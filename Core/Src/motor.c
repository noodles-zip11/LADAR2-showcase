//
// Created by project_author on 2026/3/12.
//

#include "motor.h"
#include "gpio.h"
#include "tim.h"




void Motor_Set (int speed)
{
    if (speed > 0) {
        AIN1_SET;
        AIN2_RESET;
    }
    if (speed < 0) {
        AIN2_SET;
        AIN1_RESET;
    }

    if (speed >= 0)
    {
        if (speed > 999)
        {
            speed = 999;
        }
        __HAL_TIM_SET_COMPARE(&htim1,TIM_CHANNEL_1,speed);
    }

    if (speed < 0)
    {
        if (speed < -999)
        {
            speed = -999;
        }
        __HAL_TIM_SET_COMPARE(&htim1,TIM_CHANNEL_1,-speed);
    }
}

float Get_Realtime_Motor_Angle(void)
{
    uint16_t raw_count = (uint16_t)__HAL_TIM_GET_COUNTER(&htim2);
    uint32_t counts_per_rev = (uint32_t)(ENC_PPR * GEAR_RATIO * 4.0f);
    uint32_t current_count = raw_count % counts_per_rev;
    float angle = ((float)current_count / (float)counts_per_rev) * 360.0f;
    return angle;
}
