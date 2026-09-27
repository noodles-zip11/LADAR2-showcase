# M8 离线分析报告

- 输入文件：`LOCAL_USER_HOME\Desktop\雷达\LADAR2\docs\m8\datasets\known_scenes\m6_box_far_03\m6_box_far_03.csv`
- 字段：`host_rx_time_us, t_sample_us, angle_tick, angle_deg, distance_cm, x_mm, y_mm, quality, status`

## 基础指标

| 指标 | 结果 |
| --- | --- |
| `total_rows` | 3269 |
| `valid_points` | 3269 |
| `invalid_rows` | 0 |
| `duration_s` | 32.4335 |
| `estimated_rate_hz` | 100.76 |
| `distance_cm_min` | 28 |
| `distance_cm_median` | 35 |
| `distance_cm_p95` | 41 |
| `distance_cm_max` | 46 |
| `quality_median` | 255 |
| `quality_min` | 255 |
| `low_quality_count` | 0 |
| `status_distribution` | {8: 3269} |
| `status_alert_distribution` | {0: 3269} |
| `status_alert_count` | 0 |
| `estimated_flag_count` | 3269 |
| `estimated_flag_ratio` | 1 |
| `near_obstacle_count` | 3269 |
| `too_near_count` | 572 |
| `anomaly_candidate_count` | 0 |
| `anomaly_candidate_ratio` | 0 |
| `angle_bin_deg` | 10 |
| `angle_bin_count` | 36 |
| `angle_coverage_ratio` | 1 |
| `angle_bin_min_points` | 69 |
| `angle_bin_max_points` | 233 |
| `outline_usable_bins` | 36 |
| `outline_spread_cm_median` | 3.575 |
| `outline_spread_cm_p95` | 8 |

## 标签分布

| 标签 | 片段数 |
| --- | --- |
| `static_box` | 1 |

## 口径说明

- `status & 0x07` 表示告警等级；仅该低 3 位非零时计入 `status_alert_count`。
- `status=0x08` 是 estimated 标记，不单独视为异常。
- `anomaly_candidate_ratio` 是离线筛查指标，不等同于人工场景标签或最终算法判定。
- `outline_spread_cm_*` 是按角度分箱统计的距离离散程度，只用于粗看轮廓稳定性。
