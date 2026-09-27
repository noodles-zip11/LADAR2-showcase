# M8 数据集条目

## 1. 基本信息

| 项目 | 内容 |
| --- | --- |
| 数据集名称 | `m6_box_far_02` |
| 来源 CSV | `LOCAL_USER_HOME\Desktop\雷达\LADAR2\docs\m6\runs\m6_manual\data\repeat_far_02.csv` |
| 场景标签 | `static_box` |
| 标签说明 | M6 known scene: far static box repeat 02 |
| 分类 | `known_scenes` |

## 2. 文件清单

| 文件 | 说明 |
| --- | --- |
| `m6_box_far_02.csv` | 原始 CSV 副本 |
| `m6_box_far_02.labels.csv` | 标签模板 |
| `m6_box_far_02.analysis.md` | 离线分析报告 |

## 3. 分析摘要

| 指标 | 结果 |
| --- | --- |
| `total_rows` | 3325 |
| `valid_points` | 3325 |
| `duration_s` | 34.6351 |
| `estimated_rate_hz` | 95.972 |
| `distance_cm_median` | 36 |
| `distance_cm_p95` | 41 |
| `status_distribution` | {8: 3325} |
| `status_alert_count` | 0 |
| `estimated_flag_ratio` | 1 |
| `near_obstacle_count` | 3325 |
| `too_near_count` | 534 |
| `angle_coverage_ratio` | 1 |
| `outline_spread_cm_median` | 3 |

## 4. 采集摘要

| 字段 | 值 |
| --- | --- |
| `csv_path` | `LOCAL_USER_HOME\Desktop\雷达\LADAR2\docs\m6\runs\m6_manual\data\repeat_far_02.csv` |
| `generated_at` | `2026-05-10T15:46:15` |
| `reassembly_ok_point_cnt` | `3325` |
| `reassembly_timeout_point_cnt` | `1` |
| `reassembly_overwrite_a_cnt` | `0` |
| `reassembly_overwrite_b_cnt` | `0` |
| `pending_frame_cnt` | `0` |
| `reassembly_timeout_ms` | `50` |

## 5. 标签状态

当前标签为 `static_box`。未知场景保持 `unlabeled`；只有 M6 这类来源明确的数据才写入具体场景标签。
