/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    can.c
  * @brief   This file provides code for the configuration
  *          of the CAN instances.
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
#include "can.h"

/* USER CODE BEGIN 0 */
#include "diag.h"
#include "main.h"
#include "string.h"

static uint8_t can_point_seq = 0U;
static volatile uint32_t can_bus_off_latched = 0U;
/* USER CODE END 0 */

CAN_HandleTypeDef hcan1;

/* CAN1 init function */
void MX_CAN1_Init(void)
{

  /* USER CODE BEGIN CAN1_Init 0 */

  /* USER CODE END CAN1_Init 0 */

  /* USER CODE BEGIN CAN1_Init 1 */

  /* USER CODE END CAN1_Init 1 */
  hcan1.Instance = CAN1;
  hcan1.Init.Prescaler = 6;
  hcan1.Init.Mode = CAN_MODE_NORMAL;
  hcan1.Init.SyncJumpWidth = CAN_SJW_1TQ;
  hcan1.Init.TimeSeg1 = CAN_BS1_11TQ;
  hcan1.Init.TimeSeg2 = CAN_BS2_2TQ;
  hcan1.Init.TimeTriggeredMode = DISABLE;
  hcan1.Init.AutoBusOff = ENABLE;
  hcan1.Init.AutoWakeUp = DISABLE;
  hcan1.Init.AutoRetransmission = ENABLE;
  hcan1.Init.ReceiveFifoLocked = DISABLE;
  hcan1.Init.TransmitFifoPriority = DISABLE;
  if (HAL_CAN_Init(&hcan1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN CAN1_Init 2 */

  /* USER CODE END CAN1_Init 2 */

}

void HAL_CAN_MspInit(CAN_HandleTypeDef* canHandle)
{

  GPIO_InitTypeDef GPIO_InitStruct = {0};
  if(canHandle->Instance==CAN1)
  {
  /* USER CODE BEGIN CAN1_MspInit 0 */

  /* USER CODE END CAN1_MspInit 0 */
    /* CAN1 clock enable */
    __HAL_RCC_CAN1_CLK_ENABLE();

    __HAL_RCC_GPIOA_CLK_ENABLE();
    /**CAN1 GPIO Configuration
    PA11     ------> CAN1_RX
    PA12     ------> CAN1_TX
    */
    GPIO_InitStruct.Pin = GPIO_PIN_11|GPIO_PIN_12;
    GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
    GPIO_InitStruct.Alternate = GPIO_AF9_CAN1;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

    /* CAN1 interrupt Init */
    HAL_NVIC_SetPriority(CAN1_TX_IRQn, 5, 0);
    HAL_NVIC_EnableIRQ(CAN1_TX_IRQn);
    HAL_NVIC_SetPriority(CAN1_RX0_IRQn, 5, 0);
    HAL_NVIC_EnableIRQ(CAN1_RX0_IRQn);
    HAL_NVIC_SetPriority(CAN1_RX1_IRQn, 5, 0);
    HAL_NVIC_EnableIRQ(CAN1_RX1_IRQn);
    HAL_NVIC_SetPriority(CAN1_SCE_IRQn, 5, 0);
    HAL_NVIC_EnableIRQ(CAN1_SCE_IRQn);
  /* USER CODE BEGIN CAN1_MspInit 1 */

  /* USER CODE END CAN1_MspInit 1 */
  }
}

void HAL_CAN_MspDeInit(CAN_HandleTypeDef* canHandle)
{

  if(canHandle->Instance==CAN1)
  {
  /* USER CODE BEGIN CAN1_MspDeInit 0 */

  /* USER CODE END CAN1_MspDeInit 0 */
    /* Peripheral clock disable */
    __HAL_RCC_CAN1_CLK_DISABLE();

    /**CAN1 GPIO Configuration
    PA11     ------> CAN1_RX
    PA12     ------> CAN1_TX
    */
    HAL_GPIO_DeInit(GPIOA, GPIO_PIN_11|GPIO_PIN_12);

    /* CAN1 interrupt Deinit */
    HAL_NVIC_DisableIRQ(CAN1_TX_IRQn);
    HAL_NVIC_DisableIRQ(CAN1_RX0_IRQn);
    HAL_NVIC_DisableIRQ(CAN1_RX1_IRQn);
    HAL_NVIC_DisableIRQ(CAN1_SCE_IRQn);
  /* USER CODE BEGIN CAN1_MspDeInit 1 */

  /* USER CODE END CAN1_MspDeInit 1 */
  }
}

/* USER CODE BEGIN 1 */
void HAL_CAN_ErrorCallback(CAN_HandleTypeDef *hcan)
{
  uint32_t err;

  if (hcan->Instance != CAN1)
    return;

  can_error_irq_cnt++;

  err = HAL_CAN_GetError(hcan);
  can_last_error_code = err;

  if ((err & HAL_CAN_ERROR_BOF) != 0U)
  {

    if (can_bus_off_latched == 0U)
    {
      can_bus_off_cnt++;
      can_bus_off_latched = 1U;
    }
  }

}

void CAN_DiagPoll()
{
  uint32_t err;
  if (can_bus_off_latched == 1U) {
    err = hcan1.Instance->ESR;
    if ((err & CAN_ESR_BOFF) == 0U) {
      can_recovery_cnt++;
      can_bus_off_latched = 0U;
    }
  }
}




HAL_StatusTypeDef LIDAR_SendCAN(CAN_HandleTypeDef *hcan,  CAN_TxHeaderTypeDef *pHeader,
                                        uint8_t aData[], uint32_t *pTxMailbox,lidar_point_t *point)
{
  if (hcan == NULL || pHeader == NULL || aData == NULL || pTxMailbox == NULL || point == NULL)
  {
    return HAL_ERROR;
  }
  uint8_t seq = ++can_point_seq;
  float angle = point->angle_deg;
  uint32_t ang_bits = 0 ;
  memcpy(&ang_bits, &angle, sizeof(ang_bits));
    aData[0] = seq;
    aData[1] = (point->distance_cm >> 8) & 0xFF;
    aData[2] = point->distance_cm & 0xFF;
    aData[3] = (ang_bits >> 24) & 0xFF;
    aData[4] = (ang_bits >> 16) & 0xFF;
    aData[5] = (ang_bits >> 8) & 0xFF;
    aData[6] = ang_bits  & 0xFF;
    aData[7] = point->quality;
    pHeader->DLC = 8 ;
    pHeader->IDE = CAN_ID_STD ;
    pHeader->RTR = CAN_RTR_DATA;
    pHeader->StdId = 0x123 ;
    pHeader->ExtId = 0;
    pHeader->TransmitGlobalTime = DISABLE ;
  if (HAL_CAN_AddTxMessage(hcan, pHeader, aData, pTxMailbox) != HAL_OK)
  {
    can_tx_fail_frame_cnt++;
    return HAL_ERROR;
  }

  aData[0] = seq;
  aData[1] = (point->t_sample_us >> 24) & 0xFF;
  aData[2] = (point->t_sample_us >> 16) & 0xFF;
  aData[3] = (point->t_sample_us >> 8) & 0xFF;
  aData[4] = point->t_sample_us  & 0xFF;
  aData[5] = (point->angle_tick) >> 8 & 0xFF;
  aData[6] = point->angle_tick & 0xFF ;
  aData[7] = point->status;
  pHeader->DLC = 8 ;
  pHeader->IDE = CAN_ID_STD ;
  pHeader->RTR = CAN_RTR_DATA;
  pHeader->StdId = 0x124 ;
  pHeader->ExtId = 0;
  pHeader->TransmitGlobalTime = DISABLE ;
  if (HAL_CAN_AddTxMessage(hcan, pHeader, aData, pTxMailbox) != HAL_OK)
  {
    can_tx_fail_frame_cnt++;
    return HAL_ERROR;
  }
  return HAL_OK;
}

/* USER CODE END 1 */

