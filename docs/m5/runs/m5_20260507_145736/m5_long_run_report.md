# M5 长稳运行报告

## 1. 运行结论

本次运行由 `tools/m5_long_run.py` 自动采集并生成。本轮实际运行约 1h42min，可作为 M6 前短长稳基线；不应写成严格 4h 长稳。

| 项目 | 值 |
| --- | --- |
| run_id | `m5_20260507_145736` |
| mode | `live_can` |
| start_time | `2026-05-07T14:57:36` |
| end_time | `2026-05-07T16:39:32` |
| requested_duration_s | 14400 |
| wall_duration_s | 6116.0 |
| data_duration_s | 6115.7 |
| total_points | 612466 |
| point_refresh_rate_hz | 100.147 |
| reassembly_loss_events | 7 |
| reassembly_loss_rate | 0.001143% |
| rpm_mean | 9.026 |
| rpm_std | 1.485 |
| rpm_p95_abs_delta | 3.887 |
| rpm_source | CAN angle_tick derived |

## 2. 指标判定口径

- 丢包率：`(reassembly_timeout + reassembly_overwrite_a + reassembly_overwrite_b) / (reassembly_ok + loss_events)`。
- 刷新率：CAN 重组点数除以有效数据时间，不等同于 GUI FPS。
- 转速波动：由 `angle_tick` 和 `t_sample_us` 估算。
- 本轮 M5 只采 CAN 点云和主机侧重组统计。

## 3. 证据文件

- CAN 点云 CSV：`data/can_points_m5_20260507_145736.csv`
- CAN 重组摘要：`data/can_points_m5_20260507_145736_summary.txt`
- 分钟级采样：`data/m5_interval_samples.csv`
- 运行事件日志：`logs/m5_events.log`
- 基线指标页：`baseline_metrics.md`
- 测试记录：`test_record.md`

## 4. 实测观察

- 距离范围：28 cm 到 581 cm
- quality 范围：104 到 255
- 状态字分布：`{8: 612466}`
- 告警点数：0
- 估算位点数：612466

## 5. 结论

本轮采集完整落盘并正常收尾，`wall_duration_s=6116.0`，`total_points=612466`，`reassembly_loss_rate=0.001143%`，`point_refresh_rate_hz=100.147`。它可以作为后续 M6 几何优化前的短长稳基线。

边界：本轮未满 4h，不能写成严格 4h 长稳完成。
