# M4 Linux 闭环收尾

## 1. 结论

截至 2026-03-29，M4 对应的 Linux 闭环交付已经具备收尾条件。

本轮收尾范围覆盖：

- Linux 实时接收 CAN 双帧
- 按冻结协议重组点数据
- 输出正式 CSV
- 回放历史 CSV
- 显示 XY 2D 点云
- 补齐依赖、运行说明和示例数据

说明：

- 当前仓库中的运行入口是 `can_recv4.py`
- 当前正式里程碑名称是 `M4`
- 协议与字段约束以 `docs/spec_freeze/` 为准

## 2. 完成项对照

### 2.1 将 Linux 接收端脚本与运行方式纳入正式交付

已完成，对应文件：

- `can_recv4.py`
- `requirements.txt`
- `docs/m4/README.md`

### 2.2 统一 Linux 侧时间字段名称与含义

已完成，正式字段固定为：

- `host_rx_time_us`

语义：

- `host_rx_time_us` 是 Linux 在完成点重组时记录的主机侧时间
- `t_sample_us` 是 MCU 侧的采样时间，不与 Linux 时间混用

### 2.3 固定 CSV 字段顺序、单位和兼容策略

已完成，新版正式 CSV 固定为 9 列：

1. `host_rx_time_us`
2. `t_sample_us`
3. `angle_tick`
4. `angle_deg`
5. `distance_cm`
6. `x_mm`
7. `y_mm`
8. `quality`
9. `status`

兼容策略：

- 新版正式 CSV 直接回放
- 旧版调试 CSV 兼容回放
- 旧版若缺少 `x_mm / y_mm`，由 `distance_cm + angle_deg` 在加载时现算

### 2.4 完成 CSV 历史回放功能

已完成。

脚本支持：

- `--mode replay`
- 新旧两类 CSV 回放
- 时间轴拖动
- 暂停/继续
- `0.5x / 1x / 2x` 倍速

### 2.5 将距离-时间曲线升级为真正的 XY 2D 点云实时图

已完成。

当前主界面为：

- 单页双模式
- 中央 XY 雷达视图
- 等比例坐标
- 距离环、十字准线、方位标记
- 历史点保留为压暗背景点
- 最近一圈扫描单独提取并分段显示
- 最近一圈以连续轮廓线叠加显示，便于直接观察当前轮廓

说明：

- 以上改动属于可视化增强，不改变 CAN 协议、CSV 字段和回放兼容策略
- 实时模式与回放模式共用同一套“背景点 + 最近一圈 + 轮廓线”显示逻辑

### 2.6 补 `requirements.txt`、运行说明、示例数据文件

已完成，对应文件：

- `requirements.txt`
- `docs/m4/data/can_distance_v2_sample.csv`
- `docs/m4/data/can_distance_v2_sample_summary.txt`

## 3. 交付物

本轮收尾后的主交付物如下：

- 脚本入口：`can_recv4.py`
- 依赖清单：`requirements.txt`
- 运行说明：`docs/m4/README.md`
- 规格冻结：`docs/spec_freeze/README.md`
- 字段定义：`docs/spec_freeze/02_字段表.md`
- 报文定义：`docs/spec_freeze/03_报文表.md`
- 时间戳定义：`docs/spec_freeze/04_时间戳说明表.md`
- M4 收尾文档：`docs/m4/README.md`

## 4. 证据归档

### 4.1 公开快照中的展示材料

源仓库中的 M4 桌面截图和演示视频包含机器本地账户路径及无关桌面信息，因此未纳入脱敏公开快照。M4 的可核查数据、重组统计、日志与回放输入仍保留在本目录；公开首页改用不含个人信息的电机控制和几何分析图展示结果。

### 4.2 数据与日志

- CAN 抓包样例：`docs/m4/data/candump_m4_live.log`
- Linux 正式 CSV：`docs/m4/data/can_distance_20260329_145239.csv`
- Linux 重组摘要：`docs/m4/data/can_distance_20260329_145239_summary.txt`
- 回放样例 CSV：`docs/m4/data/can_distance_v2_sample.csv`
- 回放样例摘要：`docs/m4/data/can_distance_v2_sample_summary.txt`

### 4.3 已核对的关键信息

1. `candump_m4_live.log` 仅包含 `0x123` 和 `0x124` 两种报文
2. 抓包中 `0x123` 数量为 `1335`，`0x124` 数量为 `1335`
3. `can_distance_20260329_145239.csv` 的正式表头为：

`host_rx_time_us,t_sample_us,angle_tick,angle_deg,distance_cm,x_mm,y_mm,quality,status`

4. `can_distance_20260329_145239.csv` 数据行数为 `1958`
5. `can_distance_20260329_145239_summary.txt` 中：

- `reassembly_ok_point_cnt=1958`
- `reassembly_timeout_point_cnt=0`
- `reassembly_overwrite_a_cnt=0`
- `reassembly_overwrite_b_cnt=0`
- `pending_frame_cnt=0`

### 4.4 证据边界说明

当前归档的抓包样例、正式 CSV/summary、界面截图都可以独立证明链路已经跑通，但它们不是同一次运行的完全同步证据包。

这不影响当前仓库收尾结论，但如果后续需要对外答辩或正式验收，建议额外补一套“同一轮运行”的统一证据包：

- 同一次运行的视频
- 同一次运行的实时截图
- 同一次运行的 `candump`
- 同一次运行生成的 CSV
- 同一次运行生成的 `_summary.txt`

## 5. 运行入口

### 5.1 Linux 实时模式

```bash
python3 can_recv4.py --mode live --channel can0
```

### 5.2 Linux 回放模式

```bash
python3 can_recv4.py --mode replay --input-csv docs/m4/data/can_distance_v2_sample.csv
```

## 6. M4 收尾结论

按当前仓库代码、文档和已归档证据判断，可以将 M4 的 Linux 闭环部分标记为已完成收尾。

本次收尾确认的是：

- Linux 端接收、解析、存储、回放、2D 点云显示已经闭环
- 运行方式、依赖和样例数据已补齐
- 协议、字段、时间戳语义已有冻结依据

本次收尾不包含：

- 修改 MCU 端协议
- 修改 MCU 端采样/发包逻辑
- 把历史所有证据都统一成一轮同步采集包
