# M5 长稳运行报告

## 1. 运行结论

本次运行由 `tools/m5_long_run.py` 自动采集并生成。最终结论需在实测 4h 后按下表判定；本页已经固定统计口径和证据路径。

| 项目 | 值 |
| --- | --- |
| run_id | `m5_20260507_144251` |
| mode | `offline_csv` |
| start_time | `2026-05-07T14:42:51` |
| end_time | `2026-05-07T14:42:51` |
| requested_duration_s | 0 |
| wall_duration_s | 0.0 |
| data_duration_s | 0.0 |
| total_points | 8 |
| point_refresh_rate_hz | 1600.000 |
| reassembly_loss_events | 0 |
| reassembly_loss_rate | 0.000000% |
| rpm_mean | 4.392 |
| rpm_std | 0.468 |
| rpm_p95_abs_delta | 0.741 |
| rpm_source | CAN angle_tick derived |

## 2. 指标判定口径

- 丢包率：`(reassembly_timeout + reassembly_overwrite_a + reassembly_overwrite_b) / (reassembly_ok + loss_events)`。
- 刷新率：CAN 重组点数除以有效数据时间，不等同于 GUI FPS。
- 转速波动：由 `angle_tick` 和 `t_sample_us` 估算。
- 本轮 M5 不采串口诊断，不统计温升。

## 3. 证据文件

- CAN 点云 CSV：`data/can_distance_v2_sample.csv`
- CAN 重组摘要：`data/offline_no_summary.txt`
- 分钟级采样：`data/m5_interval_samples.csv`
- 运行事件日志：`logs/m5_events.log`
- 基线指标页：`baseline_metrics.md`
- 测试记录：`test_record.md`

## 4. 实测观察

- 距离范围：63 cm 到 63 cm
- quality 范围：255 到 255
- 状态字分布：`{8: 8}`
- 告警点数：0
- 估算位点数：8

## 5. 初步结论

如果 `wall_duration_s >= 14400`，且丢包率、刷新率和转速波动都落在 `baseline_metrics.md` 的可接受范围内，则 M5 可作为后续 M6 几何优化的基线版本。
