/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
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
#include "main.h"
#include "cmsis_os.h"
#include "can.h"
#include "dma.h"
#include "tim.h"
#include "usart.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "diag.h"
#include "luna.h"
#include "string.h"
#include "motor.h"
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */
float m1_speed = 0.0f; // 电机1的速度，单位转每秒
QueueHandle_t lidarChunkQueue = NULL;
QueueHandle_t lidarPointQueue = NULL;
volatile uint32_t uart_chunk_drop_cnt = 0;
volatile uint32_t uart_chunk_oversize_cnt = 0;
volatile uint32_t parser_overflow_cnt = 0;
volatile uint32_t lidar_point_drop_cnt = 0;
volatile uint32_t checksum_fail_cnt = 0;
volatile uint32_t amp_low_cnt = 0;
volatile uint32_t too_near_cnt = 0;
volatile uint32_t lidar_chunk_q_hwm = 0;
volatile uint32_t lidar_point_q_hwm = 0;
volatile uint32_t can_last_error_code = 0;
volatile uint32_t can_error_irq_cnt = 0;
volatile uint32_t can_bus_off_cnt = 0;
volatile uint32_t can_recovery_cnt = 0;
volatile uint32_t can_tx_ok_point_cnt = 0;
volatile uint32_t can_tx_fail_point_cnt = 0;
volatile uint32_t can_tx_fail_frame_cnt = 0;
volatile uint32_t luna_frame_ok_cnt = 0;
volatile uint32_t luna_header_skip_cnt;
volatile uint32_t luna_resync_cnt = 0;
uint8_t DMA_luna_buffer[64];
volatile uint32_t encoder_count32_snapshot = 0;
volatile int32_t g_encoder_count32 = 0;
volatile uint16_t g_encoder_last16 = 0;
volatile uint8_t g_encoder_count32_valid = 0;
volatile int32_t g_last_rev_id = 0;
volatile uint32_t g_rev_transition_cnt = 0;
volatile uint8_t g_speed_valid = 0U;
volatile uint32_t g_diag_tick_ms = 0U;
volatile float g_diag_target_speed_rps = 0.0f;
volatile float g_diag_actual_speed_rps = 0.0f;
volatile float g_diag_speed_error_rps = 0.0f;
volatile float g_diag_pwm_trim = 0.0f;
volatile float g_diag_pwm_cmd = 0.0f;
/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
void MX_FREERTOS_Init(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
extern TIM_HandleTypeDef htim6;

static uint32_t micros_now(void)
{
  uint32_t ms_before;
  uint32_t ms_after;
  uint32_t us;
  uint32_t update_pending;

  do
  {
    ms_before = HAL_GetTick();
    us = __HAL_TIM_GET_COUNTER(&htim6);
    update_pending = __HAL_TIM_GET_FLAG(&htim6, TIM_FLAG_UPDATE);
    ms_after = HAL_GetTick();
  }
  while (ms_before != ms_after);

  if ((update_pending != 0U) && (us < 1000U))
  {
    ms_before++;
  }

  return (ms_before * 1000U) + us;
}


static int32_t encoder_take_snapshot32(uint16_t curr16)
{
  if (!g_encoder_count32_valid)
  {
    g_encoder_last16 = curr16;
    g_encoder_count32 = (int32_t)curr16;
    g_encoder_count32_valid = 1;
    return g_encoder_count32;
  }

  int16_t delta = (int16_t)(curr16 - g_encoder_last16);
  g_encoder_count32 += (int32_t)delta;
  g_encoder_last16 = curr16;
  return g_encoder_count32;
}
/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */
  // uint16_t last_encoder_count = 0;
  // uint32_t last_speed_ms = 0;
  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_DMA_Init();
  MX_TIM1_Init();
  MX_TIM2_Init();
  MX_USART2_UART_Init();
  MX_USART3_UART_Init();
  MX_CAN1_Init();
  /* USER CODE BEGIN 2 */

  /* USER CODE END 2 */

  /* Call init function for freertos objects (in cmsis_os2.c) */
  MX_FREERTOS_Init();

  /* Start scheduler */
  osKernelStart();

  /* We should never get here as control is now taken by the scheduler */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {

    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = 16;
  RCC_OscInitStruct.PLL.PLLN = 336;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV4;
  RCC_OscInitStruct.PLL.PLLQ = 4;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */

void HAL_UARTEx_RxEventCallback(UART_HandleTypeDef *huart, uint16_t Size)
{
    if (huart == &huart2)
    {
      BaseType_t xHigherPriorityTaskWoken = pdFALSE;
      LidarChunk chunk = {0};

      uint32_t chunk_time_us = micros_now();
      uint16_t enc16 = (uint16_t)__HAL_TIM_GET_COUNTER(&htim2);
      int32_t enc32 = encoder_take_snapshot32(enc16);

      if (Size > sizeof(chunk.data))
      {
        uart_chunk_oversize_cnt++;
      }
      else
      {
        chunk.luna_chunk_rx_time_us = chunk_time_us;
        chunk.luna_rx_encoder_tick16 = enc16;
        chunk.luna_rx_encoder_count32 = enc32;

        memcpy(chunk.data, DMA_luna_buffer, Size);
        chunk.count = Size;
        chunk.ready = 1;

        if (xQueueSendFromISR(lidarChunkQueue, &chunk, &xHigherPriorityTaskWoken) != pdPASS)
        {
          uart_chunk_drop_cnt++;
        }
        else
        {
          UBaseType_t depth = uxQueueMessagesWaitingFromISR(lidarChunkQueue);
          if ((uint32_t)depth > lidar_chunk_q_hwm)
          {
            lidar_chunk_q_hwm = (uint32_t)depth;
          }
        }

      }

      HAL_UARTEx_ReceiveToIdle_DMA(&huart2, DMA_luna_buffer, sizeof(DMA_luna_buffer));
      portYIELD_FROM_ISR(xHigherPriorityTaskWoken);
    }
}
/* USER CODE END 4 */

/**
  * @brief  Period elapsed callback in non blocking mode
  * @note   This function is called  when TIM6 interrupt took place, inside
  * HAL_TIM_IRQHandler(). It makes a direct call to HAL_IncTick() to increment
  * a global variable "uwTick" used as application time base.
  * @param  htim : TIM handle
  * @retval None
  */
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
  /* USER CODE BEGIN Callback 0 */

  /* USER CODE END Callback 0 */
  if (htim->Instance == TIM6)
  {
    HAL_IncTick();
  }
  /* USER CODE BEGIN Callback 1 */

  /* USER CODE END Callback 1 */
}

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
