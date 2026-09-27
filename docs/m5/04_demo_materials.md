# M5 演示素材清单

## 1. 运行中需要截图

建议在长稳测试期间至少截图三次：

| 时间点 | 截图内容 | 目标路径 |
| --- | --- | --- |
| 启动后 1-3 分钟 | 终端显示点数增长 | `docs/m5/runs/<run_id>/assets/start_terminal.png` |
| 运行中段 | 终端或点云界面 | `docs/m5/runs/<run_id>/assets/mid_run.png` |
| 结束后 | 报告目录和关键指标 | `docs/m5/runs/<run_id>/assets/final_report.png` |

## 2. 结束后需要保留

脚本自动生成：

- `m5_long_run_report.md`
- `baseline_metrics.md`
- `test_record.md`
- `key_log_excerpt.txt`
- `data/`
- `logs/`

人工补充：

- 点云回放截图
- 必要时录一段 30-60 秒回放视频
- 若发生异常，补异常前后终端截图

## 3. 对外讲法

M5 的核心表述：

```text
我把前面 M1-M4 的链路收口成一个可重复运行的长稳测试包。
当前已完成一轮约 1h42min 的短长稳基线，采集 612466 点，
自动产出重组丢包率、刷新率、转速波动和基线指标页。
后面的几何优化先以这轮短长稳基线为对比对象。当前不再补跑 2h，对外不写成“2h 长稳通过”。
```

## 4. 回放命令

把 `<run_id>` 和 CSV 文件名替换成本轮生成值：

```powershell
py -3 .\can_recv4_windows.py --mode replay --input-csv .\docs\m5\runs\<run_id>\data\can_points_<run_id>.csv
```
