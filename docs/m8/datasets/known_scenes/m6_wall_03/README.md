# M8 数据集条目

## 1. 基本信息

| 项目 | 内容 |
| --- | --- |
| 数据集名称 | `m6_wall_03` |
| 来源 CSV | `LOCAL_USER_HOME\Desktop\雷达\LADAR2\docs\m6\runs\m6_manual\data\wall_03.csv` |
| 场景标签 | `wall` |
| 标签说明 | M6 known scene: static wall repeat 03 |
| 分类 | `known_scenes` |

## 2. 文件清单

| 文件 | 说明 |
| --- | --- |
| `m6_wall_03.csv` | 原始 CSV 副本 |
| `m6_wall_03.labels.csv` | 标签模板 |
| `m6_wall_03.analysis.md` | 离线分析报告 |

## 3. 分析摘要

| 指标 | 结果 |
| --- | --- |
| `total_rows` | 3136 |
| `valid_points` | 3136 |
| `duration_s` | 30.8712 |
| `estimated_rate_hz` | 101.551 |
| `distance_cm_median` | 56 |
| `distance_cm_p95` | 198.25 |
| `status_distribution` | {8: 3136} |
| `status_alert_count` | 0 |
| `estimated_flag_ratio` | 1 |
| `near_obstacle_count` | 644 |
| `too_near_count` | 0 |
| `angle_coverage_ratio` | 1 |
| `outline_spread_cm_median` | 5 |

## 4. 采集摘要

| 字段 | 值 |
| --- | --- |
| `csv_path` | `LOCAL_USER_HOME\Desktop\雷达\LADAR2\docs\m6\runs\m6_manual\data\wall_03.csv` |
| `generated_at` | `2026-05-10T15:52:28` |
| `reassembly_ok_point_cnt` | `3136` |
| `reassembly_timeout_point_cnt` | `1` |
| `reassembly_overwrite_a_cnt` | `0` |
| `reassembly_overwrite_b_cnt` | `0` |
| `pending_frame_cnt` | `0` |
| `reassembly_timeout_ms` | `50` |

## 5. 标签状态

当前标签为 `wall`。未知场景保持 `unlabeled`；只有 M6 这类来源明确的数据才写入具体场景标签。
