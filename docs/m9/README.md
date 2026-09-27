# M9 规则质量门附录

M9 当前降级为附录性质的离线规则质量门。它保留脚本、报告和图表，证明数据集可以被规则流程处理，但不作为 LADAR2 封箱的核心证明项，也不宣称已经形成有效异常检测能力。

M9 不引入 AI，不训练模型，也不修改 MCU、CAN 或 live 上位机链路。

## 交付内容

| 交付物 | 文件 |
| --- | --- |
| 规则过滤脚本 | `tools/m9_rule_filter.py` |
| M9 自检 | `tools/selfcheck_m9_rule_filter.py` |
| 图读法指引 | `docs/m9/02_plot_reading_guide.md` |
| M9 附录汇总 | `docs/m9/runs/rule_based_v1/README.md` |
| known_scenes 总览图 | `docs/m9/runs/rule_based_v1/known_scenes_contact_sheet.png` |
| M6 墙面 ROI 裁剪图 | `docs/m9/runs/rule_based_v1/known_scenes_wall_roi_contact_sheet.png` |
| 未知 replay 过滤结果 | `docs/m9/runs/rule_based_v1/replay_sets/<dataset>/` |
| M6 已知场景过滤结果 | `docs/m9/runs/rule_based_v1/known_scenes/<dataset>/` |
| 每组数据过滤后 CSV | `<dataset>.m9_filtered.csv` |
| 每组数据指标报告 | `<dataset>.m9_report.md` |
| 每组数据对比图 | `<dataset>.m9_compare.png` |

## 附录范围

- 距离突变：检查相邻点在短角度或短时间范围内是否出现不合理距离跳变。
- 邻域连续性：检查点是否缺少邻近点，或邻近点距离差过大。
- `quality/status` 联合判断：低 `quality` 和 `status & 0x07` 非零会进入规则异常候选；`status=0x08` 仅按 estimated 标记统计，不单独视为异常。
- 连续圈稳定性：按角度桶统计多次扫描中的距离稳定程度，识别偶发偏离点。

## 当前结果

已基于 M8 的两类数据完成批量过滤。汇总入口：

```text
docs/m9/runs/rule_based_v1/README.md
```

- 未知 replay：处理 `83767` 行，过滤候选异常 `1140` 点，比例约 `1.36%`。这组只用于工具回归和前后输出检查，不用于墙面/箱体场景结论。
- M6 已知场景：处理 `18137` 行，过滤候选异常 `69` 点，比例约 `0.38%`。这组可用于墙面和静态箱体的 rule-based 前后对比。
- M6 墙面有效 ROI 内几乎没有红点：`wall_01` 为 0 点，`wall_02` 为 1 点，`wall_03` 为 0 点。全图红点主要位于非目标区域，不作为墙面有效区域异常证据。
- M6 箱体三组均未触发过滤，说明当前规则没有在箱体数据中发现明显点级候选异常。

因此，M9 当前不作为“算法效果证明”。它只说明：规则脚本能复现运行，能输出候选点、报告和图；但现有数据没有支撑“异常检测有效”或“明显改善点云质量”的结论。

## 复现命令

```powershell
py -3 .\tools\m9_rule_filter.py --all
py -3 .\tools\selfcheck_m9_rule_filter.py
```

完整自检入口：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\selfcheck_all.ps1
```

## 边界

M9 的输出是规则候选异常，不是人工真值标签。未知 replay 不反推场景；M6 known_scenes 也没有给出强证明结果。当前结果不能夸大为“显著改善墙面/箱体图形质量”，更合适的定位是规则流程骨架和后续扩展入口。若后续要计算 precision/recall、误判率或漏判率，需要先补更严格的人工真值标签和专门异常样例。
