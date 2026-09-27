# M5 测试记录

## 基本信息

| 项目 | 记录 |
| --- | --- |
| run_id | `m5_20260507_145736` |
| 操作人 | project_author |
| 采集命令 | `.\tools\m5_long_run.py --duration-s 14400 --can-interface gs_usb --channel 0 --bitrate 500000` |
| CAN backend | `gs_usb` |
| CAN channel | `0` |
| bitrate | `500000` |

## 检查点

- [x] 完成一轮短长稳运行，实际 `6116.0 s`
- [ ] 连续运行不少于 4h
- [x] CAN 点云 CSV 可回放
- [x] 丢包率已统计
- [x] 刷新率已统计
- [x] 转速波动已统计
- [x] 关键日志和数据样例已归档

## 结论

本轮采集完整落盘并正常收尾，可作为 M6 前短长稳基线。边界：未满 4h，不能写成严格 4h 长稳完成。
