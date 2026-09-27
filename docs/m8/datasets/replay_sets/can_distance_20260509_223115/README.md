# M8 数据集条目

## 1. 基本信息

| 项目 | 内容 |
| --- | --- |
| 数据集名称 | `can_distance_20260509_223115` |
| 来源 CSV | `LOCAL_USER_HOME\Desktop\雷达\LADAR2\can_distance_20260509_223115.csv` |
| 场景标签 | `unlabeled` |
| 标签说明 | unknown replay capture; scene is not claimed |
| 分类 | `replay_sets` |

## 2. 文件清单

| 文件 | 说明 |
| --- | --- |
| `can_distance_20260509_223115.csv` | 原始 CSV 副本 |
| `can_distance_20260509_223115.labels.csv` | 标签模板 |
| `can_distance_20260509_223115.analysis.md` | 离线分析报告 |

## 3. 分析摘要

| 指标 | 结果 |
| --- | --- |
| `total_rows` | 8691 |
| `valid_points` | 8691 |
| `duration_s` | 86.5127 |
| `estimated_rate_hz` | 100.448 |
| `distance_cm_median` | 45 |
| `distance_cm_p95` | 184 |
| `status_distribution` | {8: 8691} |
| `status_alert_count` | 0 |
| `estimated_flag_ratio` | 1 |
| `near_obstacle_count` | 5036 |
| `too_near_count` | 268 |
| `angle_coverage_ratio` | 1 |
| `outline_spread_cm_median` | 16 |

## 4. 采集摘要

| 字段 | 值 |
| --- | --- |
| `csv_path` | `LOCAL_USER_HOME\Desktop\雷达\LADAR2\can_distance_20260509_223115.csv` |
| `generated_at` | `2026-05-09T22:32:41` |
| `reassembly_ok_point_cnt` | `8691` |
| `reassembly_timeout_point_cnt` | `2` |
| `reassembly_overwrite_a_cnt` | `0` |
| `reassembly_overwrite_b_cnt` | `0` |
| `pending_frame_cnt` | `0` |
| `reassembly_timeout_ms` | `50` |

## 5. 标签状态

当前标签为 `unlabeled`。未知场景保持 `unlabeled`；只有 M6 这类来源明确的数据才写入具体场景标签。
