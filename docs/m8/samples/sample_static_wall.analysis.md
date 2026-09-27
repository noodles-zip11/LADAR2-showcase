# M8 离线分析报告

- 输入文件：`docs\m8\samples\sample_static_wall.csv`
- 字段：`host_rx_time_us, t_sample_us, angle_tick, angle_deg, distance_cm, x_mm, y_mm, quality, status`

## 基础指标

| 指标 | 结果 |
| --- | --- |
| `total_rows` | 12 |
| `valid_points` | 12 |
| `invalid_rows` | 0 |
| `duration_s` | 1.1 |
| `estimated_rate_hz` | 10 |
| `distance_cm_min` | 118 |
| `distance_cm_median` | 120.25 |
| `distance_cm_p95` | 202.1 |
| `quality_median` | 76 |
| `anomaly_ratio` | 0.166667 |
| `status_distribution` | {0: 11, 4: 1} |
| `angle_bin_count` | 12 |
| `angle_bin_min_points` | 1 |
| `angle_bin_max_points` | 1 |

## 标签分布

| 标签 | 片段数 |
| --- | --- |
| `suspect_anomaly` | 1 |
| `wall` | 2 |

## 说明

本报告由 M8 骨架脚本生成，只做离线统计；异常比例是用于快速筛查的粗略指标，不等同于正式算法判定。
