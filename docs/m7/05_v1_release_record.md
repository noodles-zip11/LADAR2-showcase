# V1 发布记录

> 发布候选日期：2026-05-10
> 提交后建议标签：`v1.0.0`
> 当前决策：先准备发布记录；审阅并提交后再创建 Git 标签

## 1. 发布范围

这个 V1 候选版本用于收口第一阶段工程演示：

- STM32 固件通过 UART DMA/IDLE 接收 TF-Luna 数据。
- 固件根据 chunk 时间、编码器状态和电机速度估算点时间与角度。
- 固件通过标准 CAN `0x123` 和 `0x124` 发送点数据。
- 上位机重组点、写 CSV、显示 2D 点云，并支持回放。
- 协议、CSV 字段和时间戳语义已经文档化。
- 长稳和几何基线已经归档。
- 面试交付材料已经准备。

## 2. 包含的里程碑

| 里程碑 | 包含证据 |
| --- | --- |
| M1 | 原始 LiDAR/CAN 采集证据 |
| M2 | 电机与同步文档，非机械误差预算 |
| M3 | CAN 报文定义、诊断、ACK fault recovery 证据 |
| M4 | 上位机实时/回放接收、CSV、UI、截图/视频证据 |
| M5 | 已接受的短长稳基线 |
| M6 | 几何质量分析和调参记录 |
| M6.5 | 当前本地/上板 MQTT 范围的可选插件收口 |
| M7 | README、图示、总览、面试讲稿、视频脚本、发布记录 |

## 3. 验证快照

| 检查项 | 命令或证据 | 结果 |
| --- | --- | --- |
| 上位机自检套件 | `powershell -ExecutionPolicy Bypass -File .\tools\selfcheck_all.ps1` | 2026-05-10 PASS |
| 固件 parser host harness | `py -3 .\tools\selfcheck_luna_firmware.py` | 2026-05-10 PASS |
| M5 长稳基线 | `docs/m5/05_current_run_summary.md` | 已接受短长稳基线 |
| M6 几何基线 | `docs/m6/runs/m6_manual/geometry_metrics.md` | 基线完成 |
| M6.5 MQTT 收口 | `docs/mqtt_plugin_refactor/08_m6_5_verification_record.md` | 当前范围已收口 |

## 4. 已知边界

- 已归档证据里还没有严格 4h/8h 长稳通过。
- 已接受的 M5 基线没有记录温升。
- M2 机械误差仍是物理测量边界。
- 当前 M3 恢复证据是 ACK fault recovery，不是完整 Bus-Off 注入。
- MQTT V1 范围不包含 ESP32、云平台、TLS/auth 或原始点云全量 MQTT 上传。
- M8 标注/数据闭环以及后续 AI/cloud 工作不属于这个 V1 标签。

## 5. 建议打标签流程

审阅并提交 M7 文档包后执行：

```powershell
git status --short
git add README.md docs/m7
git commit -m "docs: prepare m7 v1 delivery package"
git tag -a v1.0.0 -m "LADAR2 V1 first-stage delivery"
```

如果你还想把已有的未跟踪 milestone 文档也纳入 V1 commit，需要按路径显式 stage。当前 checkout 里有很多本地生成文件，不建议使用 `git add .`。

