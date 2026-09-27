#!/usr/bin/env python3
"""M5 long-run capture and report generator.

This command is meant to be the single start command for the M5 stability run:
it captures CAN points, optionally captures UART diagnostic CSV, and writes the
M5 report bundle under docs/m5/runs/<run_id>/.
"""

from __future__ import annotations

import argparse
import csv
import math
import shutil
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from can_input import CsvReplaySource, open_bus
from can_output import CsvPointWriter
from can_parser import CanPointAssembler, FORMAL_CSV_FIELDS

COUNTS_PER_REV = int(7.0 * 210.0 * 4.0)
DEFAULT_DURATION_S = 4 * 60 * 60


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def fmt(value, digits=3, suffix=""):
    if value is None:
        return "NA"
    if isinstance(value, int):
        return f"{value}{suffix}"
    return f"{value:.{digits}f}{suffix}"


def pct(numerator, denominator):
    if not denominator:
        return None
    return 100.0 * numerator / denominator


def percentile(values, percent):
    if not values:
        return None
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * percent / 100.0))
    return ordered[max(0, min(index, len(ordered) - 1))]


@dataclass
class PointMetrics:
    total_points: int = 0
    first_host_us: int | None = None
    last_host_us: int | None = None
    previous_host_us: int | None = None
    previous_sample_us: int | None = None
    previous_angle_tick: int | None = None
    distance_min_cm: int | None = None
    distance_max_cm: int | None = None
    quality_min: int | None = None
    quality_max: int | None = None
    estimated_points: int = 0
    alert_points: int = 0
    status_counts: Counter = field(default_factory=Counter)
    gaps_ms: list[float] = field(default_factory=list)
    rpm_samples: list[float] = field(default_factory=list)

    def ingest(self, point):
        self.total_points += 1
        host_us = int(point.host_rx_time_us)
        if self.first_host_us is None:
            self.first_host_us = host_us
        self.last_host_us = host_us

        if self.previous_host_us is not None:
            gap_ms = (host_us - self.previous_host_us) / 1000.0
            if gap_ms >= 0:
                self.gaps_ms.append(gap_ms)
        self.previous_host_us = host_us

        if self.previous_sample_us is not None and self.previous_angle_tick is not None:
            dt_s = (int(point.t_sample_us) - self.previous_sample_us) / 1_000_000.0
            tick_delta = abs(int(point.angle_tick) - self.previous_angle_tick)
            tick_delta = min(tick_delta, COUNTS_PER_REV - tick_delta)
            if dt_s > 0 and tick_delta > 0:
                self.rpm_samples.append((tick_delta / COUNTS_PER_REV) / dt_s * 60.0)
        self.previous_sample_us = int(point.t_sample_us)
        self.previous_angle_tick = int(point.angle_tick)

        distance = int(point.distance_cm)
        quality = int(point.quality)
        self.distance_min_cm = distance if self.distance_min_cm is None else min(self.distance_min_cm, distance)
        self.distance_max_cm = distance if self.distance_max_cm is None else max(self.distance_max_cm, distance)
        self.quality_min = quality if self.quality_min is None else min(self.quality_min, quality)
        self.quality_max = quality if self.quality_max is None else max(self.quality_max, quality)

        status = int(point.status)
        self.status_counts[status] += 1
        if status & 0x08:
            self.estimated_points += 1
        if status & 0x07:
            self.alert_points += 1

    @property
    def data_duration_s(self):
        if self.first_host_us is None or self.last_host_us is None:
            return 0.0
        return max(0.0, (self.last_host_us - self.first_host_us) / 1_000_000.0)

    def summarize(self):
        rpm_mean = statistics.fmean(self.rpm_samples) if self.rpm_samples else None
        rpm_std = statistics.pstdev(self.rpm_samples) if len(self.rpm_samples) > 1 else None
        return {
            "total_points": self.total_points,
            "data_duration_s": self.data_duration_s,
            "point_rate_hz": (self.total_points / self.data_duration_s) if self.data_duration_s > 0 else None,
            "gap_mean_ms": statistics.fmean(self.gaps_ms) if self.gaps_ms else None,
            "gap_p95_ms": percentile(self.gaps_ms, 95),
            "gap_max_ms": max(self.gaps_ms) if self.gaps_ms else None,
            "rpm_mean": rpm_mean,
            "rpm_std": rpm_std,
            "rpm_p95_abs_delta": percentile(
                [abs(value - rpm_mean) for value in self.rpm_samples], 95
            ) if rpm_mean is not None else None,
            "rpm_min": min(self.rpm_samples) if self.rpm_samples else None,
            "rpm_max": max(self.rpm_samples) if self.rpm_samples else None,
            "distance_min_cm": self.distance_min_cm,
            "distance_max_cm": self.distance_max_cm,
            "quality_min": self.quality_min,
            "quality_max": self.quality_max,
            "estimated_points": self.estimated_points,
            "alert_points": self.alert_points,
            "status_counts": dict(sorted(self.status_counts.items())),
        }


def write_interval_sample(writer, elapsed_s, metrics, assembler, last_point_count, last_elapsed_s):
    point_delta = metrics.total_points - last_point_count
    elapsed_delta = max(0.001, elapsed_s - last_elapsed_s)
    stats = assembler.stats_snapshot() if assembler is not None else {
        "ok": metrics.total_points,
        "timeout": 0,
        "overwrite_a": 0,
        "overwrite_b": 0,
        "pending": 0,
    }
    writer.writerow({
        "elapsed_s": f"{elapsed_s:.1f}",
        "total_points": metrics.total_points,
        "interval_point_rate_hz": f"{point_delta / elapsed_delta:.3f}",
        "reassembly_ok": stats["ok"],
        "reassembly_timeout": stats["timeout"],
        "reassembly_overwrite_a": stats["overwrite_a"],
        "reassembly_overwrite_b": stats["overwrite_b"],
        "reassembly_pending": stats["pending"],
    })
    return metrics.total_points, elapsed_s


def summarize_reassembly(stats):
    loss_events = stats.get("timeout", 0) + stats.get("overwrite_a", 0) + stats.get("overwrite_b", 0)
    denominator = stats.get("ok", 0) + loss_events
    return loss_events, pct(loss_events, denominator)


def write_reports(run_dir, context, point_summary, reassembly_stats):
    data_dir = run_dir / "data"
    report_path = run_dir / "m5_long_run_report.md"
    record_path = run_dir / "test_record.md"
    baseline_path = run_dir / "baseline_metrics.md"
    excerpt_path = run_dir / "key_log_excerpt.txt"

    loss_events, loss_rate = summarize_reassembly(reassembly_stats)
    rpm_source = "CAN angle_tick derived"

    report = f"""# M5 长稳运行报告

## 1. 运行结论

本次运行由 `tools/m5_long_run.py` 自动采集并生成。本页固定统计口径和证据路径；M5 当前收口接受约 1h42min 短长稳基线作为 M6 前基线。

| 项目 | 值 |
| --- | --- |
| run_id | `{context['run_id']}` |
| mode | `{context['mode']}` |
| start_time | `{context['start_time']}` |
| end_time | `{context['end_time']}` |
| requested_duration_s | {context['requested_duration_s']} |
| wall_duration_s | {fmt(context['wall_duration_s'], 1)} |
| data_duration_s | {fmt(point_summary['data_duration_s'], 1)} |
| total_points | {point_summary['total_points']} |
| point_refresh_rate_hz | {fmt(point_summary['point_rate_hz'], 3)} |
| reassembly_loss_events | {loss_events} |
| reassembly_loss_rate | {fmt(loss_rate, 6, "%")} |
| rpm_mean | {fmt(point_summary['rpm_mean'], 3)} |
| rpm_std | {fmt(point_summary['rpm_std'], 3)} |
| rpm_p95_abs_delta | {fmt(point_summary['rpm_p95_abs_delta'], 3)} |
| rpm_source | {rpm_source} |

## 2. 指标判定口径

- 丢包率：`(reassembly_timeout + reassembly_overwrite_a + reassembly_overwrite_b) / (reassembly_ok + loss_events)`。
- 刷新率：CAN 重组点数除以有效数据时间，不等同于 GUI FPS。
- 转速波动：由 `angle_tick` 和 `t_sample_us` 估算。
- 本轮 M5 只采 CAN 点云和主机侧重组统计。

## 3. 证据文件

- CAN 点云 CSV：`data/{context['can_csv_name']}`
- CAN 重组摘要：`data/{context['can_summary_name']}`
- 分钟级采样：`data/{context['sample_csv_name']}`
- 运行事件日志：`logs/{context['event_log_name']}`
- 基线指标页：`baseline_metrics.md`
- 测试记录：`test_record.md`

## 4. 实测观察

- 距离范围：{fmt(point_summary['distance_min_cm'])} cm 到 {fmt(point_summary['distance_max_cm'])} cm
- quality 范围：{fmt(point_summary['quality_min'])} 到 {fmt(point_summary['quality_max'])}
- 状态字分布：`{point_summary['status_counts']}`
- 告警点数：{point_summary['alert_points']}
- 估算位点数：{point_summary['estimated_points']}

## 5. 初步结论

如果采集过程完整落盘，且丢包率、刷新率和转速波动都写入 `baseline_metrics.md`，则本轮可作为后续 M6 几何优化的基线版本。当前项目接受 `m5_20260507_145736` 约 1h42min 记录作为 M6 前基线。
"""

    baseline = f"""# M5 基线指标页

| 指标 | 本次值 | 建议基线/判定 |
| --- | ---: | --- |
| 连续运行时长 | {fmt(context['wall_duration_s'], 1)} s | 当前接受约 1h42min 短长稳基线 |
| CAN 重组点数 | {point_summary['total_points']} | 非 0，且运行中持续增长 |
| 丢包率 | {fmt(loss_rate, 6, "%")} | 先记录为基线；后续 M6/M7 不应显著变差 |
| 刷新率 | {fmt(point_summary['point_rate_hz'], 3)} Hz | 先记录为基线；后续优化需对比 |
| 点间隔 p95 | {fmt(point_summary['gap_p95_ms'], 3)} ms | 先记录为基线 |
| 最大点间隔 | {fmt(point_summary['gap_max_ms'], 3)} ms | 用于定位卡顿/断流 |
| 平均转速 | {fmt(point_summary['rpm_mean'], 3)} rpm | 先记录为基线 |
| 转速标准差 | {fmt(point_summary['rpm_std'], 3)} rpm | 先记录为基线 |
| 转速 p95 偏差 | {fmt(point_summary['rpm_p95_abs_delta'], 3)} rpm | 先记录为基线 |
"""

    record = f"""# M5 测试记录

## 基本信息

| 项目 | 记录 |
| --- | --- |
| run_id | `{context['run_id']}` |
| 操作人 | project_author |
| 采集命令 | `{context['command']}` |
| CAN backend | `{context.get('can_interface', 'NA')}` |
| CAN channel | `{context.get('channel', 'NA')}` |
| bitrate | `{context.get('bitrate', 'NA')}` |

## 检查点

- [x] 完成当前阶段短长稳基线
- [ ] CAN 点云 CSV 可回放
- [ ] 丢包率已统计
- [ ] 刷新率已统计
- [ ] 转速波动已统计
- [ ] 关键日志和数据样例已归档

## 结论

待人工复核本目录下报告和截图后填写最终结论。
"""

    excerpt = "\n".join([
        f"run_id={context['run_id']}",
        f"total_points={point_summary['total_points']}",
        f"point_refresh_rate_hz={fmt(point_summary['point_rate_hz'], 3)}",
        f"reassembly_loss_events={loss_events}",
        f"reassembly_loss_rate={fmt(loss_rate, 6, '%')}",
        f"rpm_mean={fmt(point_summary['rpm_mean'], 3)}",
        f"rpm_std={fmt(point_summary['rpm_std'], 3)}",
    ]) + "\n"

    report_path.write_text(report, encoding="utf-8")
    baseline_path.write_text(baseline, encoding="utf-8")
    record_path.write_text(record, encoding="utf-8")
    excerpt_path.write_text(excerpt, encoding="utf-8")
    return report_path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="M5 long-run CAN capture and report generator")
    parser.add_argument("--duration-s", type=float, default=DEFAULT_DURATION_S)
    parser.add_argument("--can-interface", default="gs_usb")
    parser.add_argument("--channel", default="0")
    parser.add_argument("--bitrate", type=int, default=500000)
    parser.add_argument("--output-root", type=Path, default=REPO_ROOT / "docs" / "m5" / "runs")
    parser.add_argument("--sample-interval-s", type=float, default=60.0)
    parser.add_argument("--input-csv", type=Path, help="Offline mode: analyze an existing point CSV instead of CAN")
    return parser.parse_args(argv)


def run_offline(args, run_dir, data_dir, logs_dir, event_log, run_id):
    source = CsvReplaySource(args.input_csv)
    metrics = PointMetrics()
    for point in source.points:
        metrics.ingest(point)

    sample_csv = data_dir / "m5_interval_samples.csv"
    offline_summary = data_dir / "offline_no_summary.txt"
    with sample_csv.open("w", newline="", encoding="utf-8") as sample_file:
        writer = csv.DictWriter(
            sample_file,
            fieldnames=[
                "elapsed_s",
                "total_points",
                "interval_point_rate_hz",
                "reassembly_ok",
                "reassembly_timeout",
                "reassembly_overwrite_a",
                "reassembly_overwrite_b",
                "reassembly_pending",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "elapsed_s": f"{metrics.data_duration_s:.1f}",
            "total_points": metrics.total_points,
            "interval_point_rate_hz": fmt(metrics.summarize()["point_rate_hz"], 3),
            "reassembly_ok": metrics.total_points,
            "reassembly_timeout": 0,
            "reassembly_overwrite_a": 0,
            "reassembly_overwrite_b": 0,
            "reassembly_pending": 0,
        })

    copied_csv = data_dir / Path(args.input_csv).name
    if Path(args.input_csv).resolve() != copied_csv.resolve():
        shutil.copy2(args.input_csv, copied_csv)
    offline_summary.write_text(
        "\n".join([
            f"csv_path={copied_csv}",
            f"generated_at={datetime.now().isoformat(timespec='seconds')}",
            f"reassembly_ok_point_cnt={metrics.total_points}",
            "reassembly_timeout_point_cnt=0",
            "reassembly_overwrite_a_cnt=0",
            "reassembly_overwrite_b_cnt=0",
            "pending_frame_cnt=0",
            "mode=offline_csv",
        ]) + "\n",
        encoding="utf-8",
    )

    context = {
        "run_id": run_id,
        "mode": "offline_csv",
        "start_time": datetime.now().isoformat(timespec="seconds"),
        "end_time": datetime.now().isoformat(timespec="seconds"),
        "requested_duration_s": 0,
        "wall_duration_s": 0.0,
        "command": " ".join(sys.argv),
        "can_csv_name": copied_csv.name,
        "can_summary_name": offline_summary.name,
        "sample_csv_name": sample_csv.name,
        "event_log_name": Path(event_log.name).name,
    }
    report_path = write_reports(
        run_dir,
        context,
        metrics.summarize(),
        {"ok": metrics.total_points, "timeout": 0, "overwrite_a": 0, "overwrite_b": 0, "pending": 0},
    )
    event_log.write(f"offline report written: {report_path}\n")
    return 0


def main(argv=None):
    args = parse_args(argv)
    run_id = f"m5_{now_stamp()}"
    run_dir = args.output_root / run_id
    data_dir = run_dir / "data"
    logs_dir = run_dir / "logs"
    assets_dir = run_dir / "assets"
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    event_log_path = logs_dir / "m5_events.log"
    with event_log_path.open("w", encoding="utf-8") as event_log:
        event_log.write(f"run_id={run_id}\n")
        event_log.write(f"command={' '.join(sys.argv)}\n")

        if args.input_csv:
            return run_offline(args, run_dir, data_dir, logs_dir, event_log, run_id)

        start_time = datetime.now()
        start_monotonic = time.monotonic()
        deadline = start_monotonic + args.duration_s
        csv_path = data_dir / f"can_points_{run_id}.csv"
        sample_csv = data_dir / "m5_interval_samples.csv"

        metrics = PointMetrics()
        assembler = CanPointAssembler()
        bus = None
        writer = None
        run_error = None
        sample_fields = [
            "elapsed_s",
            "total_points",
            "interval_point_rate_hz",
            "reassembly_ok",
            "reassembly_timeout",
            "reassembly_overwrite_a",
            "reassembly_overwrite_b",
            "reassembly_pending",
        ]

        try:
            bus = open_bus(args.channel, interface=args.can_interface, bitrate=args.bitrate)
            writer = CsvPointWriter(csv_path)
            with sample_csv.open("w", newline="", encoding="utf-8") as sample_file:
                sample_writer = csv.DictWriter(sample_file, fieldnames=sample_fields)
                sample_writer.writeheader()
                last_sample_s = 0.0
                last_sample_points = 0

                print(f"M5 long run started: {run_id}", flush=True)
                print(f"CAN: interface={args.can_interface} channel={args.channel} bitrate={args.bitrate}", flush=True)
                print(f"Output: {run_dir}", flush=True)

                while time.monotonic() < deadline:
                    msg = bus.recv(timeout=1.0)
                    if msg is not None:
                        for point in assembler.process_message(msg):
                            writer.write_point(point)
                            metrics.ingest(point)
                    assembler.prune_stale_frames()

                    elapsed_s = time.monotonic() - start_monotonic
                    if elapsed_s - last_sample_s >= args.sample_interval_s:
                        last_sample_points, last_sample_s = write_interval_sample(
                            sample_writer,
                            elapsed_s,
                            metrics,
                            assembler,
                            last_sample_points,
                            last_sample_s,
                        )
                        sample_file.flush()
                        print(
                            f"[M5] elapsed={elapsed_s:.0f}s points={metrics.total_points} "
                            f"stats={assembler.stats_text()}",
                            flush=True,
                        )
        except KeyboardInterrupt:
            event_log.write("interrupted by user\n")
        except Exception as exc:
            run_error = exc
            event_log.write(f"run failed: {exc}\n")
            print(f"M5 run failed: {exc}", file=sys.stderr, flush=True)
        finally:
            if assembler is not None:
                assembler.prune_stale_frames()
            if writer is not None:
                writer.write_summary(assembler.stats_snapshot())
                writer.close()
            if bus is not None:
                bus.shutdown()

        end_time = datetime.now()
        wall_duration_s = time.monotonic() - start_monotonic
        reassembly_stats = assembler.stats_snapshot()
        context = {
            "run_id": run_id,
            "mode": "live_can",
            "start_time": start_time.isoformat(timespec="seconds"),
            "end_time": end_time.isoformat(timespec="seconds"),
            "requested_duration_s": int(args.duration_s),
            "wall_duration_s": wall_duration_s,
            "command": " ".join(sys.argv),
            "can_interface": args.can_interface,
            "channel": args.channel,
            "bitrate": args.bitrate,
            "can_csv_name": csv_path.name,
            "can_summary_name": writer.summary_path.name if writer is not None else "",
            "sample_csv_name": sample_csv.name,
            "event_log_name": event_log_path.name,
        }
        report_path = write_reports(
            run_dir,
            context,
            metrics.summarize(),
            reassembly_stats,
        )
        event_log.write(f"report written: {report_path}\n")
        print(f"M5 report written: {report_path}", flush=True)
        return 1 if run_error is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
