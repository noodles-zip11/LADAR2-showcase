# M8 数据集索引

本目录由 `tools/m8_build_dataset.py` 从根目录已有 `can_distance_*.csv` 构建。

这些采集只证明数据可回放、可统计、可进入离线分析；由于缺少现场记录，不承担墙面、箱子、拐角或动态目标等场景语义。

## 可回放数据集

| 数据集 | 点数 | 时长 s | 点率 Hz | 状态分布 | 标签状态 |
| --- | ---: | ---: | ---: | --- | --- |
| [can_distance_20260507_141150](can_distance_20260507_141150/README.md) | 5220 | 51.4775 | 101.384 | `{8: 5220}` | `unlabeled` |
| [can_distance_20260509_214813](can_distance_20260509_214813/README.md) | 15671 | 154.922 | 101.148 | `{8: 15671}` | `unlabeled` |
| [can_distance_20260509_222646](can_distance_20260509_222646/README.md) | 20881 | 237.316 | 87.9841 | `{8: 20881}` | `unlabeled` |
| [can_distance_20260509_223115](can_distance_20260509_223115/README.md) | 8691 | 86.5127 | 100.448 | `{8: 8691}` | `unlabeled` |
| [can_distance_20260510_000136](can_distance_20260510_000136/README.md) | 33304 | 407.084 | 81.8086 | `{8: 33304}` | `unlabeled` |

## 未纳入回放集的采集

| 文件 | 原因 |
| --- | --- |
| `can_distance_20260507_140135.csv` | no valid points |
| `can_distance_20260509_235522.csv` | no valid points |
| `can_distance_20260509_235632.csv` | no valid points |

## 使用方式

单文件分析：

```powershell
py -3 .\tools\m8_offline_analysis.py --input .\docs\m8\datasets\replay_sets\<dataset>\<dataset>.csv --labels .\docs\m8\datasets\replay_sets\<dataset>\<dataset>.labels.csv
```

重建数据集：

```powershell
py -3 .\tools\m8_build_dataset.py
```

## 边界

- 本索引不把 `unlabeled` 当作真实场景标签。
- 不知道现场的 5 月 7 日和 5 月 9/10 日根目录采集，只能保留为 unknown replay 数据。
- `status=0x08` 按 estimated 标记统计，不按异常统计。
- 后续若补充采集现场记录，可以只编辑对应 `.labels.csv` 和条目 README。
