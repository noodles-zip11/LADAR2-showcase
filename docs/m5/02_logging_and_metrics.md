# M5 日志设计与指标口径

## 1. 自动生成文件

每次运行 `tools/m5_long_run.py` 后，会生成：

| 文件 | 作用 |
| --- | --- |
| `data/can_points_<run_id>.csv` | 正式 CAN 点云 CSV |
| `data/can_points_<run_id>_summary.txt` | CAN 双帧重组摘要 |
| `data/m5_interval_samples.csv` | 分钟级点数和重组统计 |
| `logs/m5_events.log` | 脚本事件和异常记录 |
| `m5_long_run_report.md` | 长稳报告 |
| `baseline_metrics.md` | 基线指标页 |
| `test_record.md` | 测试记录 |

## 2. CAN 点云 CSV 字段

沿用 M4 冻结字段：

```text
host_rx_time_us,t_sample_us,angle_tick,angle_deg,distance_cm,x_mm,y_mm,quality,status
```

M5 不在这个正式 CSV 中追加温度、转速或调试计数，避免破坏回放兼容。

## 3. 丢包率

CAN 双帧重组器统计：

- `ok`
- `timeout`
- `overwrite_a`
- `overwrite_b`
- `pending`

M5 丢包率口径：

```text
loss_events = timeout + overwrite_a + overwrite_b
loss_rate = loss_events / (ok + loss_events)
```

`pending` 表示结束时仍未配对的半帧，主要用于解释收尾瞬间状态，不直接计入默认丢包率。

## 4. 刷新率

默认刷新率指点云数据刷新率：

```text
point_refresh_rate_hz = total_points / data_duration_s
```

它不是 GUI 的屏幕 FPS。

## 5. 转速波动

脚本使用 CAN 点云字段 `angle_tick + t_sample_us` 派生 rpm：

```text
rpm = abs(delta_angle_tick) / counts_per_rev / delta_t_s * 60
counts_per_rev = ENC_PPR * GEAR_RATIO * 4 = 5880
```

输出：

- `rpm_mean`
- `rpm_std`
- `rpm_p95_abs_delta`
- `rpm_min`
- `rpm_max`

## 6. 本轮边界

本轮 M5 的通过标准只覆盖 CAN 点云长稳、丢包率、刷新率和转速波动。

`m5_20260507_145736` 已按该口径生成：

- `m5_long_run_report.md`
- `baseline_metrics.md`
- `test_record.md`
- `data/can_points_m5_20260507_145736_summary.txt`
- `data/m5_interval_samples.csv`
