# M8 数据集合同

## 1. CSV 字段

M8 离线分析脚本识别以下字段：

| 字段 | 必需 | 含义 |
| --- | --- | --- |
| `host_rx_time_us` | 是 | 上位机完成点重组的本地时间，单位 us |
| `t_sample_us` | 否 | MCU 侧估算采样时间，单位 us |
| `angle_tick` | 否 | 原始角度 tick |
| `angle_deg` | 是 | 角度，单位 deg |
| `distance_cm` | 是 | 距离，单位 cm |
| `x_mm` | 否 | 派生 X 坐标，单位 mm |
| `y_mm` | 否 | 派生 Y 坐标，单位 mm |
| `quality` | 否 | LiDAR 质量值 |
| `status` | 否 | 点状态码 |

最小可分析 CSV：

```text
host_rx_time_us,angle_deg,distance_cm
```

当前正式 CSV：

```text
host_rx_time_us,t_sample_us,angle_tick,angle_deg,distance_cm,x_mm,y_mm,quality,status
```

## 2. 状态码口径

当前上位机和回放告警逻辑采用以下口径：

| 位 | 含义 | M8 统计方式 |
| --- | --- | --- |
| `status & 0x07` | 告警等级 | 低 3 位非零时计入 `status_alert_count` |
| `status & 0x08` | estimated 标记 | 计入 `estimated_flag_count`，不单独视为异常 |

因此 `status=0x08` 表示 estimated 点，不应被 M8 离线分析直接判为异常。

## 3. 文件命名

建议格式：

```text
<source_or_scene>_<yyyymmdd>_<hhmmss>_<note>.csv
```

当前从根目录已有采集构建的数据集保留原始采集名，例如：

```text
can_distance_20260510_000136.csv
```

## 4. 数据分类

| 分类 | 用途 | 示例 |
| --- | --- | --- |
| `replay_sets` | 已归档、可重复分析和回放的数据集 | 当前 5 份 `can_distance_*` 采集 |
| `static` | 静态场景基线 | 墙面、固定盒子、固定角点 |
| `dynamic` | 动态目标 | 人手移动、目标横穿 |
| `anomaly` | 异常样例 | 弱反射、低质量、跳点、状态告警 |
| `long_stability` | 长稳样例 | 10 min、30 min、1 h 连续数据 |

`static/dynamic/anomaly/long_stability` 需要人工确认场景后再归档。当前自动构建脚本只放入 `replay_sets`。

## 5. 标签文件

标签文件使用独立 CSV，不回写原始数据。命名：

```text
<csv_stem>.labels.csv
```

字段：

```text
start_host_rx_time_us,end_host_rx_time_us,label,comment
```

推荐标签：

| 标签 | 含义 |
| --- | --- |
| `unlabeled` | 已归档但尚未人工确认场景 |
| `normal` | 正常片段 |
| `static_box` | 静态箱体或盒子目标 |
| `suspect_anomaly` | 疑似异常 |
| `dynamic_target` | 动态目标 |
| `wall` | 墙面 |
| `corner` | 拐角 |
| `low_quality` | 质量偏低 |
| `unstable_outline` | 轮廓不稳定 |

## 6. M8 第一版验收

- 现有有效 CSV 已进入 `docs/m8/datasets/replay_sets/`。
- 每份数据有原始 CSV 副本、`.labels.csv` 模板、`.analysis.md` 报告和条目 README。
- M6 已知墙面/箱体数据进入 `docs/m8/datasets/known_scenes/`，带 `wall` / `static_box` 场景标签。
- 空采集不会混入 replay 数据集，原因记录在索引中。
- 脚本能重新生成数据集和报告。
- 未知 replay 采集仍保持 `unlabeled`，不从 CSV 数值反推真实场景。
