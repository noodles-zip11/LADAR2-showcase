# M5 长稳收口与基线交付

## 1. 目标

M5 的目标是把当前 LADAR2 主链路收口成可复现、可连续运行、可作为后续几何优化基线的版本。

本阶段不改 CAN 点云协议，不改变 CSV 正式字段，重点是把长稳测试、日志证据、指标统计和交付材料固定下来。

截至 2026-05-07，已完成一轮 `m5_20260507_145736` 短长稳基线：实际运行 `6116.0 s`，采集 `612466` 点，平均刷新率 `100.147 Hz`，CAN 重组丢包率 `0.001143%`。当前阶段接受这轮约 1h42min 记录作为 M6 前基线，M5 不再要求继续补跑 2h。

## 2. 可选复测命令

Windows + candleLight/gs_usb 适配器命令：

```powershell
py -3 .\tools\m5_long_run.py --duration-s 7200 --can-interface gs_usb --channel 0 --bitrate 500000
```

脚本会在 `docs/m5/runs/m5_YYYYMMDD_HHMMSS/` 下生成本轮证据包。当前 M5 已有可接受基线，复测不是 M6 前阻塞项。

## 3. 本阶段交付物

| 交付物 | 路径 |
| --- | --- |
| Checkpoint 对照 | `docs/m5/00_checkpoint_delivery.md` |
| M5 总说明 | `docs/m5/README.md` |
| 测试设计 | `docs/m5/01_test_design.md` |
| 日志与指标口径 | `docs/m5/02_logging_and_metrics.md` |
| 系统图/数据流/时序图 | `docs/m5/03_system_and_dataflow.md` |
| 演示素材清单 | `docs/m5/04_demo_materials.md` |
| 当前实测基线 | `docs/m5/05_current_run_summary.md` |
| 长稳采集脚本 | `tools/m5_long_run.py` |
| 每轮运行证据包 | `docs/m5/runs/<run_id>/` |

每轮运行证据包会自动包含：

- `m5_long_run_report.md`
- `test_record.md`
- `baseline_metrics.md`
- `key_log_excerpt.txt`
- `data/can_points_<run_id>.csv`
- `data/can_points_<run_id>_summary.txt`
- `data/m5_interval_samples.csv`
- `logs/m5_events.log`

## 4. 操作边界

你只需要做两件事：

1. 给 MCU、LiDAR、电机和 CAN 适配器上电。
2. 在仓库根目录运行上面的 M5 开始命令。

其余材料由脚本和文档模板自动产出。本轮 M5 只围绕 CAN 点云长稳、丢包率、刷新率和转速波动形成基线。

## 5. M5 完成判定

- 当前 M5 接受 `m5_20260507_145736` 作为 M6 前短长稳基线。
- CAN 点云 CSV 非空，并可用 M4 回放入口打开。
- `_summary.txt`、分钟级采样、测试记录和基线指标页齐全。
- 丢包率、刷新率、转速波动有明确统计。
- 不再补跑 2h；不能对外表述为“2h 长稳通过”，但可以表述为“约 1h42min 短长稳基线已完成并作为 M6 前基线”。
