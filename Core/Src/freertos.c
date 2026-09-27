/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * File Name          : freertos.c
  * Description        : Code for freertos applications
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */

/* Includes ------------------------------------------------------------------*/
#include "FreeRTOS.h"
#include "task.h"
#include "main.h"
#include "cmsis_os.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "diag.h"
#include "luna.h"
#include "string.h"
#include "motor.h"
#include "can.h"
#include "tim.h"
#include "usart.h"
#include "queue.h"
#include <stdio.h>
#include <pid.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */
extern tpid pidMotor1Speed;
extern void CAN_DiagPoll(void);
/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
/* USER CODE BEGIN Variables */

/* USER CODE END Variables */
osThreadId defaultTaskHandle;
osThreadId LidarParseTaskHandle;
osThreadId MotorCtrlTaskHandle;
osThreadId CanTxTaskHandle;
osThreadId DiagLogTaskHandle;

/* Private function prototypes -----------------------------------------------*/
/* USER CODE BEGIN FunctionPrototypes */

/* USER CODE END FunctionPrototypes */

void StartDefaultTask(void const * argument);
void LidarParseTask1(void const * argument);
void MotorCtrlTask1(void const * argument);
void CanTxTask1(void const * argument);
void DiagLogTask1(void const * argument);

void MX_FREERTOS_Init(void); /* (MISRA C 2004 rule 8.1) */

/* GetIdleTaskMemory prototype (linked to static allocation support) */
void vApplicationGetIdleTaskMemory( StaticTask_t **ppxIdleTaskTCBBuffer, StackType_t **ppxIdleTaskStackBuffer, uint32_t *pulIdleTaskStackSize );

/* USER CODE BEGIN GET_IDLE_TASK_MEMORY */
static StaticTask_t xIdleTaskTCBBuffer;
static StackType_t xIdleStack[configMINIMAL_STACK_SIZE];

void vApplicationGetIdleTaskMemory( StaticTask_t **ppxIdleTaskTCBBuffer, StackType_t **ppxIdleTaskStackBuffer, uint32_t *pulIdleTaskStackSize )
{
  *ppxIdleTaskTCBBuffer = &xIdleTaskTCBBuffer;
  *ppxIdleTaskStackBuffer = &xIdleStack[0];
  *pulIdleTaskStackSize = configMINIMAL_STACK_SIZE;
  /* place for user code */
}
/* USER CODE END GET_IDLE_TASK_MEMORY */

/**
  * @brief  FreeRTOS initialization
  * @param  None
  * @retval None
  */
void MX_FREERTOS_Init(void) {
  /* USER CODE BEGIN Init */
  // char msg[64];
  lidarChunkQueue = xQueueCreate(4, sizeof(LidarChunk));
  lidarPointQueue = xQueueCreate(16, sizeof(lidar_point_t));


  HAL_UARTEx_ReceiveToIdle_DMA(&huart2,DMA_luna_buffer,sizeof(DMA_luna_buffer));
  HAL_TIM_PWM_Start(&htim1,TIM_CHANNEL_1);
  HAL_TIM_Encoder_Start(&htim2, TIM_CHANNEL_ALL);
  HAL_GPIO_WritePin(GPIOC, GPIO_PIN_2, GPIO_PIN_SET);

  if (HAL_CAN_Start(&hcan1) != HAL_OK)
  {
    Error_Handler();
  }

  if ( HAL_CAN_ActivateNotification(&hcan1,
        CAN_IT_ERROR |
        CAN_IT_BUSOFF |
        CAN_IT_LAST_ERROR_CODE |
        CAN_IT_ERROR_WARNING |
        CAN_IT_ERROR_PASSIVE) != HAL_OK) {
    Error_Handler();
  }

  /* USER CODE END Init */

  /* USER CODE BEGIN RTOS_MUTEX */
  /* add mutexes, ... */
  /* USER CODE END RTOS_MUTEX */

  /* USER CODE BEGIN RTOS_SEMAPHORES */
  /* add semaphores, ... */
  /* USER CODE END RTOS_SEMAPHORES */

  /* USER CODE BEGIN RTOS_TIMERS */
  /* start timers, add new ones, ... */
  /* USER CODE END RTOS_TIMERS */

  /* USER CODE BEGIN RTOS_QUEUES */
  /* add queues, ... */
  /* USER CODE END RTOS_QUEUES */

  /* Create the thread(s) */
  /* definition and creation of defaultTask */
  osThreadDef(defaultTask, StartDefaultTask, osPriorityNormal, 0, 128);
  defaultTaskHandle = osThreadCreate(osThread(defaultTask), NULL);

  /* definition and creation of LidarParseTask */
  osThreadDef(LidarParseTask, LidarParseTask1, osPriorityHigh, 0, 1024);
  LidarParseTaskHandle = osThreadCreate(osThread(LidarParseTask), NULL);

  /* definition and creation of MotorCtrlTask */
  osThreadDef(MotorCtrlTask, MotorCtrlTask1, osPriorityNormal, 0, 128);
  MotorCtrlTaskHandle = osThreadCreate(osThread(MotorCtrlTask), NULL);

  /* definition and creation of CanTxTask */
  osThreadDef(CanTxTask, CanTxTask1, osPriorityNormal, 0, 512);
  CanTxTaskHandle = osThreadCreate(osThread(CanTxTask), NULL);

  /* definition and creation of DiagLogTask */
  osThreadDef(DiagLogTask, DiagLogTask1, osPriorityBelowNormal, 0, 512);
  DiagLogTaskHandle = osThreadCreate(osThread(DiagLogTask), NULL);

  /* USER CODE BEGIN RTOS_THREADS */
  /* add threads, ... */
  /* USER CODE END RTOS_THREADS */

}

/* USER CODE BEGIN Header_StartDefaultTask */
/**
  * @brief  Function implementing the defaultTask thread.
  * @param  argument: Not used
  * @retval None
  */
/* USER CODE END Header_StartDefaultTask */
void StartDefaultTask(void const * argument)
{
  /* USER CODE BEGIN StartDefaultTask */
  /* Infinite loop */
  for(;;)
  {
    CAN_DiagPoll();
    osDelay(1);
  }
  /* USER CODE END StartDefaultTask */
}

/* USER CODE BEGIN Header_LidarParseTask1 */
/**
* @brief Function implementing the LidarParseTask thread.
* @param argument: Not used
* @retval None
*/
/* USER CODE END Header_LidarParseTask1 */
void LidarParseTask1(void const * argument)
{
  /* USER CODE BEGIN LidarParseTask1 */
  /* Infinite loop */
  LidarChunk local_chunk;
  uint8_t parser_buffer[64];
  uint8_t parser_buffer_len = 0 ;
  for(;;)
  {

    if (xQueueReceive(lidarChunkQueue, &local_chunk, portMAX_DELAY) == pdPASS)
      {
      if (parser_buffer_len + local_chunk.count <= sizeof(parser_buffer))
      {
        uint16_t chunk_start_index = parser_buffer_len;
        memcpy(&parser_buffer[parser_buffer_len],local_chunk.data,local_chunk.count);
        parser_buffer_len += local_chunk.count ;
        uint16_t a = luna_input(parser_buffer,parser_buffer_len,chunk_start_index,&local_chunk,m1_speed);
        if (a > 0)
        {
          uint16_t left_bytes = parser_buffer_len - a ;
          if (left_bytes > 0)
          {
            memmove(&parser_buffer[0], &parser_buffer[a], left_bytes);
          }
          parser_buffer_len = left_bytes;
        }
      }
      else
      {
        parser_overflow_cnt++;
        parser_buffer_len = 0;
      }
    }
    osDelay(1);
  }
  /* USER CODE END LidarParseTask1 */
}

/* USER CODE BEGIN Header_MotorCtrlTask1 */
/**
* @brief Function implementing the MotorCtrlTask thread.
* @param argument: Not used
* @retval None
*/
/* USER CODE END Header_MotorCtrlTask1 */
void MotorCtrlTask1(void const * argument)
{
  /* USER CODE BEGIN MotorCtrlTask1 */
  /* Infinite loop */
  PID_init();
  uint16_t last_encoder_count = 0;
  uint32_t last_speed_ms = 0;
  uint16_t current_encoder_count = 0;
  uint8_t speed_update_cnt = 0;
  const uint32_t control_period_ms = 50U;
  const uint32_t counts_per_rev = (uint32_t)(ENC_PPR * GEAR_RATIO * 4.0f);
  const uint32_t reverse_interval_counts = 1U * counts_per_rev;
  const float target_speed_abs_rps = 0.15f;
  const float reverse_resume_speed_rps = 0.015f;
  const uint32_t reverse_ramp_ms = 1200U;
  const float startup_pwm = 220.0f;
  const float base_pwm = 430.0f;
  uint32_t segment_travel_count = 0U;
  uint32_t dir_resume_ms = 0U;
  int32_t scan_dir = 1;
  uint8_t reverse_pending = 0U;

  pidMotor1Speed.target_val = target_speed_abs_rps;
  last_encoder_count = (uint16_t)__HAL_TIM_GET_COUNTER(&htim2);
  last_speed_ms = HAL_GetTick();
  dir_resume_ms = last_speed_ms;



  for(;;)
    {
    uint32_t now_ms = HAL_GetTick();
    uint32_t elapsed_ms = now_ms - last_speed_ms;
    if (elapsed_ms >= control_period_ms)
    {
      current_encoder_count = (uint16_t)__HAL_TIM_GET_COUNTER(&htim2);
      int16_t delta_count = (int16_t)(current_encoder_count - last_encoder_count);
      uint32_t delta_abs = (delta_count >= 0) ? (uint32_t)delta_count : (uint32_t)(-delta_count);
      float dt_s = (float)elapsed_ms / 1000.0f;
      float rev1 = (float)delta_count / (ENC_PPR * GEAR_RATIO * 4.0f);

      if (elapsed_ms > 0)
      {
        m1_speed = rev1 / dt_s;

        if (delta_count != 0)
        {
          if (speed_update_cnt < 3U)
          {
            speed_update_cnt++;
          }
        }
        else
        {
          if (g_speed_valid == 0U)
          {
            speed_update_cnt = 0U;
          }
        }
        if (speed_update_cnt >= 2U)
        {
          g_speed_valid = 1U;
        }
      }


      float m1_speed_ctrl = -m1_speed;
      float trim = 0.0f;
      float pwm_cmd = 0.0f;

      if (reverse_pending == 0U)
      {
        float target_scale = 1.0f;
        uint32_t run_elapsed_ms = now_ms - dir_resume_ms;

        if (run_elapsed_ms < reverse_ramp_ms)
        {
          target_scale = (float)run_elapsed_ms / (float)reverse_ramp_ms;
        }

        segment_travel_count += delta_abs;
        pidMotor1Speed.target_val = (float)scan_dir * target_speed_abs_rps * target_scale;

        if (segment_travel_count >= reverse_interval_counts)
        {
          reverse_pending = 1U;
          pidMotor1Speed.target_val = 0.0f;
          PID_Reset(&pidMotor1Speed);
        }
      }

      if (reverse_pending != 0U)
      {
        float actual_speed_abs = (m1_speed_ctrl >= 0.0f) ? m1_speed_ctrl : -m1_speed_ctrl;

        pwm_cmd = 0.0f;

        if (actual_speed_abs <= reverse_resume_speed_rps)
        {
          scan_dir = -scan_dir;
          segment_travel_count = 0U;
          reverse_pending = 0U;
          dir_resume_ms = now_ms;
          PID_Reset(&pidMotor1Speed);
          pidMotor1Speed.target_val = 0.0f;
        }
      }

      if (reverse_pending == 0U)
      {
        float target_scale = 1.0f;
        float commanded_base_pwm = base_pwm;
        uint32_t run_elapsed_ms = now_ms - dir_resume_ms;

        if (run_elapsed_ms < reverse_ramp_ms)
        {
          target_scale = (float)run_elapsed_ms / (float)reverse_ramp_ms;

          commanded_base_pwm = startup_pwm + ((base_pwm - startup_pwm) * target_scale);
          pidMotor1Speed.target_val = (float)scan_dir * target_speed_abs_rps * target_scale;
        }

        trim = PID_realize(&pidMotor1Speed, m1_speed_ctrl, dt_s);
        pwm_cmd = ((float)scan_dir * commanded_base_pwm) + trim;
      }

      if (pwm_cmd < -999.0f) pwm_cmd = -999.0f;
      if (pwm_cmd > 999.0f) pwm_cmd = 999.0f;

      g_diag_tick_ms = now_ms;
      g_diag_target_speed_rps = pidMotor1Speed.target_val;
      g_diag_actual_speed_rps = m1_speed_ctrl;
      g_diag_speed_error_rps = pidMotor1Speed.err;
      g_diag_pwm_trim = trim;
      g_diag_pwm_cmd = pwm_cmd;

      Motor_Set((int)pwm_cmd);

    last_encoder_count = current_encoder_count;
    last_speed_ms = now_ms;
    }
      osDelay(10);
    }
  /* USER CODE END MotorCtrlTask1 */
}

/* USER CODE BEGIN Header_CanTxTask1 */
  /**
  * @brief Function implementing the CanTxTask thread.
  * @param argument: Not used
  * @retval None
  */
/* USER CODE END Header_CanTxTask1 */
void CanTxTask1(void const * argument)
{
  /* USER CODE BEGIN CanTxTask1 */
    /* Infinite loop */
  lidar_point_t point_rx;
    for(;;)
    {
    if (xQueueReceive(lidarPointQueue, &point_rx, portMAX_DELAY) == pdPASS)
      {
        CAN_TxHeaderTypeDef pHeader;
        uint8_t txData[8];
        uint32_t pTxMailbox;
        if (LIDAR_SendCAN(&hcan1, &pHeader, txData, &pTxMailbox, &point_rx) != HAL_OK ) {
          can_tx_fail_point_cnt++;
        }
        else {
          can_tx_ok_point_cnt++;
        }
      }

      osDelay(1);
    }
  /* USER CODE END CanTxTask1 */
}

/* USER CODE BEGIN Header_DiagLogTask1 */
/**
* @brief Function implementing the DiagLogTask thread.
* @param argument: Not used
* @retval None
*/
/* USER CODE END Header_DiagLogTask1 */
void DiagLogTask1(void const * argument)
{
  /* USER CODE BEGIN DiagLogTask1 */
  uint8_t header_sent = 0U;
  static char tx_line[320];
  static const char csv_header[] ="tick_ms,lidar_chunk_q_depth,lidar_chunk_q_hwm,uart_chunk_drop_cnt,uart_chunk_oversize_cnt,parser_overflow_cnt,checksum_fail_cnt,amp_low_cnt,too_near_cnt,lidar_point_q_depth,lidar_point_q_hwm,lidar_point_drop_cnt,can_tx_ok_point_cnt,can_tx_fail_point_cnt,can_tx_fail_frame_cnt,can_last_error_code,can_error_irq_cnt,can_bus_off_cnt,can_recovery_cnt\r\n";

  for(;;) {
    if (header_sent == 0U)
    {
      HAL_UART_Transmit(&huart3, (uint8_t *)csv_header, (uint16_t)strlen(csv_header), 100U);
      header_sent = 1U;
    }


      uint32_t tick_ms = HAL_GetTick();

      uint32_t lidar_chunk_q_depth_snapshot =
          (uint32_t)uxQueueMessagesWaiting(lidarChunkQueue);
      uint32_t lidar_chunk_q_hwm_snapshot = lidar_chunk_q_hwm;
      uint32_t uart_chunk_drop_snapshot = uart_chunk_drop_cnt;
      uint32_t uart_chunk_oversize_snapshot = uart_chunk_oversize_cnt;
      uint32_t parser_overflow_snapshot = parser_overflow_cnt;

      uint32_t checksum_fail_snapshot = checksum_fail_cnt;
      uint32_t amp_low_snapshot = amp_low_cnt;
      uint32_t too_near_snapshot = too_near_cnt;

      uint32_t lidar_point_q_depth_snapshot = (uint32_t)uxQueueMessagesWaiting(lidarPointQueue);
      uint32_t lidar_point_q_hwm_snapshot = lidar_point_q_hwm;
      uint32_t lidar_point_drop_snapshot = lidar_point_drop_cnt;

      uint32_t can_tx_ok_point_snapshot = can_tx_ok_point_cnt;
      uint32_t can_tx_fail_point_snapshot = can_tx_fail_point_cnt;
      uint32_t can_tx_fail_frame_snapshot = can_tx_fail_frame_cnt;

      uint32_t can_last_error_snapshot = can_last_error_code;
      uint32_t can_error_irq_snapshot = can_error_irq_cnt;
      uint32_t can_bus_off_snapshot = can_bus_off_cnt;
      uint32_t can_recovery_snapshot = can_recovery_cnt;

      int len = snprintf(
        tx_line,
        sizeof(tx_line),
        "%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,0x%08lX,%lu,%lu,%lu\r\n",
        (unsigned long)tick_ms,
        (unsigned long)lidar_chunk_q_depth_snapshot,
        (unsigned long)lidar_chunk_q_hwm_snapshot,
        (unsigned long)uart_chunk_drop_snapshot,
        (unsigned long)uart_chunk_oversize_snapshot,
        (unsigned long)parser_overflow_snapshot,
        (unsigned long)checksum_fail_snapshot,
        (unsigned long)amp_low_snapshot,
        (unsigned long)too_near_snapshot,
        (unsigned long)lidar_point_q_depth_snapshot,
        (unsigned long)lidar_point_q_hwm_snapshot,
        (unsigned long)lidar_point_drop_snapshot,
        (unsigned long)can_tx_ok_point_snapshot,
        (unsigned long)can_tx_fail_point_snapshot,
        (unsigned long)can_tx_fail_frame_snapshot,
        (unsigned long)can_last_error_snapshot,
        (unsigned long)can_error_irq_snapshot,
        (unsigned long)can_bus_off_snapshot,
        (unsigned long)can_recovery_snapshot);

      if (len > 0)
      {
        HAL_UART_Transmit(&huart3, (uint8_t *)tx_line, (uint16_t)len, 100U);
      }
    osDelay(1000);
  }
  /* USER CODE END DiagLogTask1 */
}

/* Private application code --------------------------------------------------*/
/* USER CODE BEGIN Application */

/* USER CODE END Application */
