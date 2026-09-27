# M8 数据闭环与离线分析

> 状态：可交付版第一版。已把未知采集归档成可回放数据集，并把 M6 已知墙面/箱体数据归档成带场景标签的数据集。

## 1. 目标

M8 建立本地数据闭环：

```text
录制 CSV -> 归档分类 -> 离线分析 -> 人工标签/备注 -> 可回放测试集
```

当前已完成数据合同、批量构建、离线分析、报告生成、标签模板和数据集索引。根目录 `can_distance_*.csv` 只作为未知场景 replay；M6 已知图形数据作为真实场景标签来源。

## 2. 当前交付物

| 交付物 | 文件 |
| --- | --- |
| 数据字段、命名、标签合同 | `docs/m8/01_dataset_contract.md` |
| 数据集说明模板 | `docs/m8/02_dataset_readme_template.md` |
| M8 完成说明 | `docs/m8/03_m8_delivery_note.md` |
| 样例 CSV 和样例标签 | `docs/m8/samples/` |
| 未知场景可回放数据集索引 | `docs/m8/datasets/replay_sets/README.md` |
| M6 已知场景数据集索引 | `docs/m8/datasets/known_scenes/README.md` |
| 单文件离线分析脚本 | `tools/m8_offline_analysis.py` |
| 批量数据集构建脚本 | `tools/m8_build_dataset.py` |

## 3. 数据集现状

已从根目录 `can_distance_*.csv` 构建出 5 份未知场景可回放数据集。它们可用于回放和统计，但不声明墙面、箱体、拐角或动态目标语义：

- `can_distance_20260507_141150`
- `can_distance_20260509_214813`
- `can_distance_20260509_222646`
- `can_distance_20260509_223115`
- `can_distance_20260510_000136`

以下 3 份采集没有有效点，已记录为未纳入回放集：

- `can_distance_20260507_140135.csv`
- `can_distance_20260509_235522.csv`
- `can_distance_20260509_235632.csv`

已从 M6 几何质量数据构建出 6 份已知场景数据集：

- `m6_box_far_01` / `m6_box_far_02` / `m6_box_far_03`：`static_box`
- `m6_wall_01` / `m6_wall_02` / `m6_wall_03`：`wall`

## 4. 使用方式

单文件分析：

```powershell
py -3 .\tools\m8_offline_analysis.py --input .\docs\m8\datasets\replay_sets\can_distance_20260510_000136\can_distance_20260510_000136.csv --labels .\docs\m8\datasets\replay_sets\can_distance_20260510_000136\can_distance_20260510_000136.labels.csv
```

重建整个 M8 数据集：

```powershell
py -3 .\tools\m8_build_dataset.py
```

## 5. 分析口径

- `status & 0x07` 表示告警等级，低 3 位非零才计入 `status_alert_count`。
- `status=0x08` 是 estimated 标记，不单独视为异常。
- `near_obstacle_count` 和 `too_near_count` 是距离阈值统计，不等同于真实场景标签。
- `anomaly_candidate_ratio` 是离线筛查指标，不等同于最终算法判断。
- `outline_spread_cm_*` 是按角度分箱统计的距离离散程度，只用于粗看轮廓稳定性。

## 6. 标签边界

根目录未知采集保持 `unlabeled`，例如不知道 5 月 7 日现场是什么，就不能给它标墙面或箱体。

M6 数据的现场语义已经明确，因此 M8 将 `repeat_far_*` 标为 `static_box`，将 `wall_*` 标为 `wall`。后续如果有新采集，只有在有现场记录、截图或视频支撑时才补具体场景标签。
