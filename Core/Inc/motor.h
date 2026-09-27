//
// Created by project_author on 2026/3/12.
//

#ifndef LIDAR_MOTOR_H
#define LIDAR_MOTOR_H


#define AIN2_SET HAL_GPIO_WritePin(GPIOC, GPIO_PIN_1, GPIO_PIN_SET);
#define AIN1_SET HAL_GPIO_WritePin(GPIOC, GPIO_PIN_0, GPIO_PIN_SET);

#define AIN2_RESET HAL_GPIO_WritePin(GPIOC, GPIO_PIN_1, GPIO_PIN_RESET);
#define AIN1_RESET HAL_GPIO_WritePin(GPIOC, GPIO_PIN_0, GPIO_PIN_RESET);

void Motor_Set (int speed);
float Get_Realtime_Motor_Angle(void);
#endif //LIDAR_MOTOR_H