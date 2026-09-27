# M8 第一版完成说明

## 1. 已完成

本轮把 M8 从骨架推进到可交付第一版：

- 修正离线分析脚本的状态码口径。
- 新增批量数据集构建脚本。
- 从根目录已有 `can_distance_*.csv` 构建 replay 数据集。
- 从 M6 几何质量数据构建 `known_scenes` 数据集。
- 为每份有效数据生成分析报告。
- 为每份有效数据生成标签模板。
- 生成 replay 数据集总索引。
- 保留空采集记录，避免误纳入可回放测试集。
- 新增 M8 数据集自检，并接入 `tools/selfcheck_all.ps1`。

## 2. 当前未知 replay 数据集

| 数据集 | 说明 |
| --- | --- |
| `can_distance_20260507_141150` | 有效采集，场景未知，保持 `unlabeled` |
| `can_distance_20260509_214813` | 有效采集，场景未知，保持 `unlabeled` |
| `can_distance_20260509_222646` | 有效采集，场景未知，保持 `unlabeled` |
| `can_distance_20260509_223115` | 有效采集，场景未知，保持 `unlabeled` |
| `can_distance_20260510_000136` | 有效采集，场景未知，保持 `unlabeled` |

## 3. 当前 M6 已知场景数据集

| 数据集 | 标签 | 来源 |
| --- | --- | --- |
| `m6_box_far_01` | `static_box` | `docs/m6/runs/m6_manual/data/repeat_far_01.csv` |
| `m6_box_far_02` | `static_box` | `docs/m6/runs/m6_manual/data/repeat_far_02.csv` |
| `m6_box_far_03` | `static_box` | `docs/m6/runs/m6_manual/data/repeat_far_03.csv` |
| `m6_wall_01` | `wall` | `docs/m6/runs/m6_manual/data/wall_01.csv` |
| `m6_wall_02` | `wall` | `docs/m6/runs/m6_manual/data/wall_02.csv` |
| `m6_wall_03` | `wall` | `docs/m6/runs/m6_manual/data/wall_03.csv` |

## 4. 未自动完成的部分

以下内容不能由脚本从未知 replay 采集中可靠推断：

- 哪一段是真实墙面。
- 哪一段是真实拐角。
- 哪一段包含动态目标。
- 哪一段是人为制造的异常样例。

这些标签需要结合采集现场记录、视频、截图或你的描述确认。未知 replay 的 `.labels.csv` 保持全段 `unlabeled`，这是有意保守处理。

## 5. 后续补标签方式

如果后续你能确认某份未知 replay 的现场，打开对应 `.labels.csv`，把全段 `unlabeled` 拆成具体时间范围即可。没有现场依据时不要补：

```text
start_host_rx_time_us,end_host_rx_time_us,label,comment
1778342496342157,1778342600000000,wall,static wall segment
1778342600000001,1778342700000000,dynamic_target,hand moved across scan
```

补完标签后重新运行：

```powershell
py -3 .\tools\m8_offline_analysis.py --input <csv> --labels <labels> --output <analysis.md>
```

或直接重建整个索引：

```powershell
py -3 .\tools\m8_build_dataset.py
```

默认重建会保留已有 `.labels.csv`。如果确实要重写标签模板，显式使用：

```powershell
py -3 .\tools\m8_build_dataset.py --overwrite-labels
```
