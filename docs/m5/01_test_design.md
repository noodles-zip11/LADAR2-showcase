# M5 测试设计

## 1. 测试目的

验证当前链路在长时间运行下是否稳定：

```text
TF-Luna -> UART DMA/IDLE -> MCU parser -> angle/time pairing -> CAN 0x123/0x124
-> Windows/Linux CAN capture -> CSV -> replay/report
```

## 2. 测试时长

M6 前接受当前短长稳基线作为收口证据。

当前已有实测轮次 `m5_20260507_145736` 实际运行 `6116.0 s`，约 1h42min，作为 M6 前短长稳基线。后续不再补跑 2h。

调试命令可以先用短时长验证：

```powershell
py -3 .\tools\m5_long_run.py --duration-s 60 --can-interface gs_usb --channel 0 --bitrate 500000
```

## 3. 必采指标

| 指标 | 来源 | 说明 |
| --- | --- | --- |
| 丢包率 | CAN 双帧重组统计 | `timeout + overwrite_a + overwrite_b` 对比成功点数 |
| 刷新率 | CAN 点云 CSV | 成功重组点数 / 有效数据时间 |
| 转速波动 | CAN `angle_tick` 派生 | 默认用 `angle_tick + t_sample_us` 估算 rpm |

## 4. 通过标准

M5 不先写死绝对阈值，而是形成第一版基线。当前完成条件：

- 本轮程序未崩溃，采集文件完整落盘。
- CAN 点云持续增长，没有长时间断流。
- 丢包率、刷新率和转速波动被写入 `baseline_metrics.md`。
- 本轮通过标准只覆盖 CAN 点云长稳、丢包率、刷新率和转速波动。

当前短长稳基线判定：

- `m5_20260507_145736` 已完整落盘并正常收尾。
- 实际运行 `6116.0 s`，点数 `612466`。
- `reassembly_timeout=7`，`overwrite_a=0`，`overwrite_b=0`，`pending=0`。
- 可作为 M6 前基线，不写成 2h 长稳通过。

## 5. 失败处理

如果后续复测中断：

- 保留本轮 `docs/m5/runs/<run_id>/`，不要覆盖。
- 先看 `logs/m5_events.log`。
- 再看 `data/m5_interval_samples.csv` 中最后一次点数增长时间。
- 结论中明确写“短长稳基线”，不要写成 2h 长稳通过。
