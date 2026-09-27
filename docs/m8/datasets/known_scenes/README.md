# M8 已知场景数据集索引

本目录由 `tools/m8_build_dataset.py` 从 M6 几何质量数据构建。
这些 CSV 的场景来源在 M6 中已经明确，因此可以带真实场景标签。

## 已知场景数据集

| 数据集 | 来源 | 点数 | 时长 s | 点率 Hz | 标签 |
| --- | --- | ---: | ---: | ---: | --- |
| [m6_box_far_01](m6_box_far_01/README.md) | `docs\m6\runs\m6_manual\data\repeat_far_01.csv` | 3268 | 33.4878 | 97.5579 | `static_box` |
| [m6_box_far_02](m6_box_far_02/README.md) | `docs\m6\runs\m6_manual\data\repeat_far_02.csv` | 3325 | 34.6351 | 95.972 | `static_box` |
| [m6_box_far_03](m6_box_far_03/README.md) | `docs\m6\runs\m6_manual\data\repeat_far_03.csv` | 3269 | 32.4335 | 100.76 | `static_box` |
| [m6_wall_01](m6_wall_01/README.md) | `docs\m6\runs\m6_manual\data\wall_01.csv` | 2284 | 22.434 | 101.765 | `wall` |
| [m6_wall_02](m6_wall_02/README.md) | `docs\m6\runs\m6_manual\data\wall_02.csv` | 2855 | 27.966 | 102.053 | `wall` |
| [m6_wall_03](m6_wall_03/README.md) | `docs\m6\runs\m6_manual\data\wall_03.csv` | 3136 | 30.8712 | 101.551 | `wall` |

## 标签口径

- `static_box`：M6 远距静态箱体重复采样，用于轮廓重复性和四边质量观察。
- `wall`：M6 静态墙面重复采样，用于直线度和重复偏移观察。
- 不从未知 replay 数据反推场景标签。
