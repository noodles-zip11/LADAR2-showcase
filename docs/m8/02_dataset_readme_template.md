# 数据集说明模板

复制本模板到具体数据集目录，命名为 `README.md`。

## 1. 数据集基本信息

| 项目 | 内容 |
| --- | --- |
| 数据集名称 | TODO |
| 采集日期 | TODO |
| 场景分类 | static / dynamic / anomaly / long_stability / replay_sets |
| 采集方式 | live / replay / synthetic |
| 采集命令 | TODO |
| 设备状态 | TODO |
| 备注 | TODO |

## 2. 文件清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| TODO.csv | 原始 CSV | TODO |
| TODO.labels.csv | 标签 CSV | TODO |
| TODO.analysis.md | 分析报告 | TODO |

## 3. 标签定义

| 标签 | 使用范围 | 判定说明 |
| --- | --- | --- |
| normal | TODO | TODO |
| suspect_anomaly | TODO | TODO |
| dynamic_target | TODO | TODO |

## 4. 分析摘要

| 指标 | 结果 |
| --- | --- |
| 总点数 | TODO |
| 有效点数 | TODO |
| 估算帧率 | TODO |
| 异常点比例 | TODO |
| 状态码分布 | TODO |
| 轮廓稳定性备注 | TODO |

## 5. 可回放性

回放命令：

```powershell
TODO
```

已知限制：

- TODO

## 6. 是否可纳入固定测试集

结论：TODO

理由：

- TODO
