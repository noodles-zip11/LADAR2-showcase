"""核心处理层 (core) 模块。

从 can_recv4.py 中拆分出来的纯数据处理层，包含：
- 状态位掩码常量 (STATUS_ESTIMATED, STATUS_ALERT_MASK)
- sweep 相关常量 (SWEEP_TARGET_DEG, MIN_SWEEP_POINT_COUNT, SWEEP_BREAK_DISTANCE_MM)
- 角度差值计算 (angular_delta_deg)
- sweep 提取 (extract_recent_sweep)
- sweep 轮廓线构建 (build_sweep_curve)

core 层只处理数据，不直接依赖 UI、CSV、MQTT。
后续 telemetry / alarm 计算入口应追加到本模块。

本轮 (Prompt 5) 只拆 core 层，不涉及 MQTT / UI 样式 / parser 契约。
"""

import math

# ── 状态位掩码 ──────────────────────────────────────────────────
# 详见 docs/spec_freeze/02_字段表.md

STATUS_ESTIMATED = 0x08    # bit3: 本点为插值/估算值
STATUS_ALERT_MASK = 0x07   # bit[2:0]: 告警等级 (0=正常, 1-7=告警)

# ── sweep 提取常量 ─────────────────────────────────────────────

SWEEP_TARGET_DEG = 340.0       # 目标扫描角度跨度 (度)
MIN_SWEEP_POINT_COUNT = 24     # 有效 sweep 最少点数
SWEEP_BREAK_DISTANCE_MM = 120.0  # 相邻点间距超过此值视为断点 (毫米)


# ── 角度计算 ────────────────────────────────────────────────────

def angular_delta_deg(current_deg, previous_deg):
    """计算两个角度之间的有向差值 (度)，自动处理 360° 回绕。

    Returns:
        float: 差值，范围 (-180, 180]。正值表示顺时针转动，负值表示逆时针。
    """
    return ((float(current_deg) - float(previous_deg) + 180.0) % 360.0) - 180.0


# ── sweep 提取 ──────────────────────────────────────────────────

def extract_recent_sweep(points, target_travel_deg=SWEEP_TARGET_DEG):
    """从点云尾部提取最近一圈扫描 (sweep)。

    从最新点向前回溯，累计角度跨度达到 target_travel_deg 时截断。
    最少返回 MIN_SWEEP_POINT_COUNT 个点。

    Args:
        points: LidarPoint 列表 (按时间升序排列)
        target_travel_deg: 目标角度跨度 (度)

    Returns:
        list[LidarPoint]: 最近一圈扫描的点列表 (保持原顺序)
    """
    if len(points) <= 1:
        return list(points)

    sweep_points = [points[-1]]
    angular_travel = 0.0

    for index in range(len(points) - 1, 0, -1):
        current_point = points[index]
        previous_point = points[index - 1]
        angular_travel += abs(
            angular_delta_deg(current_point.angle_deg, previous_point.angle_deg)
        )
        sweep_points.append(previous_point)
        if angular_travel >= target_travel_deg and len(sweep_points) >= MIN_SWEEP_POINT_COUNT:
            break

    sweep_points.reverse()
    return sweep_points


# ── sweep 轮廓线构建 ────────────────────────────────────────────

def build_sweep_curve(points, break_distance_mm=SWEEP_BREAK_DISTANCE_MM):
    """将 sweep 点序列转换为可绘制的轮廓线。

    相邻点间距超过 break_distance_mm 时插入 NaN 断点，
    使绘图库 (pyqtgraph connect="finite") 在该处断开线段。

    Args:
        points: LidarPoint 列表 (sweep 点序列)
        break_distance_mm: 断点阈值 (毫米)

    Returns:
        (list[float], list[float]): (xs, ys) 坐标序列 (含 NaN 断点)
    """
    if not points:
        return [], []

    xs = [points[0].x_mm]
    ys = [points[0].y_mm]

    for previous_point, current_point in zip(points, points[1:]):
        gap_mm = math.hypot(
            current_point.x_mm - previous_point.x_mm,
            current_point.y_mm - previous_point.y_mm,
        )
        if gap_mm > break_distance_mm:
            xs.append(math.nan)
            ys.append(math.nan)
        xs.append(current_point.x_mm)
        ys.append(current_point.y_mm)

    return xs, ys


# ── 最小距离 ────────────────────────────────────────────────────

def compute_min_distance(points):
    """从点集中提取最小距离及对应角度。

    Args:
        points: LidarPoint 可迭代序列，None 按空点集处理

    Returns:
        (min_distance_cm: int | None, min_angle_deg: float | None)
        若 points 为 None 或空序列则返回 (None, None)。
    """
    if points is None:
        return None, None

    min_dist = None
    min_angle = None
    for point in points:
        if min_dist is None or point.distance_cm < min_dist:
            min_dist = point.distance_cm
            min_angle = point.angle_deg
    return min_dist, min_angle


# ── 扇区定义与统计 ────────────────────────────────────────────

# 默认四扇区定义：{扇区名: (start_deg, end_deg)}
# 角度按顺时针递增，区间包含 start_deg，不含 end_deg。
# 例如 Front 覆盖 (-45°, 45°]，即 315°→45° 跨越 0° 边界，需特殊处理。
DEFAULT_SECTOR_DEFS = {
    "Front": (-45.0, 45.0),
    "Right": (45.0, 135.0),
    "Rear":  (135.0, 225.0),
    "Left":  (225.0, 315.0),
}


def _angle_in_sector(angle_deg, start_deg, end_deg):
    """判断角度是否落在 [start_deg, end_deg) 扇区内，自动处理 360° 回绕。"""
    angle_deg = float(angle_deg) % 360.0
    start_deg = float(start_deg) % 360.0
    end_deg = float(end_deg) % 360.0

    if start_deg <= end_deg:
        # 普通区间 (如 45→135)
        return start_deg <= angle_deg < end_deg
    else:
        # 跨越 0° 边界 (如 315→45)
        return angle_deg >= start_deg or angle_deg < end_deg


def compute_sector_summary(points, sector_defs=None):
    """按扇区统计点数和最小距离。

    Args:
        points: LidarPoint 可迭代序列
        sector_defs: dict[name -> (start_deg, end_deg)]，默认使用 DEFAULT_SECTOR_DEFS

    Returns:
        list[dict]: 每个扇区的摘要，按 sector_defs 顺序排列。
        每项包含: name, point_count, min_distance_cm, alert_level
    """
    if sector_defs is None:
        sector_defs = DEFAULT_SECTOR_DEFS
    if points is None:
        points = []

    # 初始化累加器
    sectors = []
    for name in sector_defs:
        sectors.append({
            "name": name,
            "point_count": 0,
            "min_distance_cm": None,
            "alert_level": 0,
        })

    for point in points:
        angle = point.angle_deg % 360.0
        for idx, (name, (start, end)) in enumerate(sector_defs.items()):
            if _angle_in_sector(angle, start, end):
                sec = sectors[idx]
                sec["point_count"] += 1
                d = point.distance_cm
                if sec["min_distance_cm"] is None or d < sec["min_distance_cm"]:
                    sec["min_distance_cm"] = d
                alert_lv = point.status & STATUS_ALERT_MASK
                if alert_lv > sec["alert_level"]:
                    sec["alert_level"] = alert_lv
                break

    return sectors


# ── 告警状态 ────────────────────────────────────────────────────

def compute_alarm_state(point_or_status):
    """从 LidarPoint 或原始 status 值提取告警状态。

    Args:
        point_or_status: LidarPoint (取 .status) 或 int (原始 status 值)

    Returns:
        (alert_level: int, is_alert: bool)
    """
    if hasattr(point_or_status, "status"):
        raw = point_or_status.status
    else:
        raw = int(point_or_status)
    alert_level = raw & STATUS_ALERT_MASK
    return alert_level, alert_level != 0


# ── 派生告警常量 ──────────────────────────────────────────────

DERIVED_ALARM_NEAR_CM = 50       # Lv1 阈值 (厘米)
DERIVED_ALARM_TOO_NEAR_CM = 30   # Lv2 阈值 (厘米)
DERIVED_ALARM_CLEAR_CM = 60      # 滞回清除阈值 (厘米)
DERIVED_NO_POINTS_MS = 500       # 无有效点超时 (毫秒)
DERIVED_STARTUP_GRACE_MS = 2000  # 启动防抖宽限期 (毫秒)
DERIVED_ALARM_WINDOW_MS = 500    # 派生距离告警只看最近 N 毫秒的点 (毫秒)


# ── 派生告警状态 ──────────────────────────────────────────────

def compute_derived_alarm_state(current_point, alarm_window_points,
                                previous_state=None, now_ms=None):
    """计算综合告警状态 (MCU status + 派生距离/遮挡告警)。

    纯函数，不依赖 MQTT / UI / CSV。优先级：
      1. MCU status & 0x07 非零 → 最高优先级
      2. alarm_window_points 最近点距离 <= 30cm → Lv2 derived_too_near
      3. alarm_window_points 最近点距离 <= 50cm → Lv1 derived_near_obstacle
      4. 超过 DERIVED_NO_POINTS_MS 无有效点 → Lv1 derived_no_valid_points
      5. 以上均不满足     → clear

    距离告警清除使用滞回：alarm_window_points 的 min_distance_cm > 60cm。

    Args:
        current_point: 当前最新 LidarPoint 或 None (无点超时检查时为 None)
        alarm_window_points: 最近 N 毫秒的 LidarPoint 列表 (非 8s 显示窗口)
        previous_state: 上一次返回的 dict，用于滞回/超时判断
        now_ms: 当前时间戳 (毫秒)，用于无点超时判断

    Returns:
        dict: {
            alert_level: int,          # 0=正常, 1=Lv1, 2=Lv2
            is_alert: bool,            # alert_level != 0
            alarm_source: str,         # "mcu_status" | "derived_distance" |
                                       # "derived_no_valid_points" | "clear"
            alarm_reason: str,         # 具体原因描述
            threshold_cm: int|None,    # 触发阈值
            min_distance_cm: int|None, # 当前 alarm_window 最小距离
            last_point_ms: int|None,   # 最近一个点的时间戳 (毫秒)，用于超时计算
        }
    """
    min_dist, _min_angle = compute_min_distance(alarm_window_points)

    # 提取最近一个点的时间戳 (毫秒)
    last_point_ms = None
    if now_ms is not None and previous_state is not None:
        last_point_ms = previous_state.get("last_point_ms")
    if current_point is not None and now_ms is not None:
        last_point_ms = now_ms

    result_base = {
        "alert_level": 0,
        "is_alert": False,
        "alarm_source": "clear",
        "alarm_reason": "alarm cleared",
        "threshold_cm": None,
        "min_distance_cm": min_dist,
        "last_point_ms": last_point_ms,
    }

    # ── 1. MCU status 告警 (最高优先级) ───────────────────────
    if current_point is not None:
        mcu_alert = current_point.status & STATUS_ALERT_MASK
        if mcu_alert != 0:
            return {
                **result_base,
                "alert_level": min(mcu_alert, 7),
                "is_alert": True,
                "alarm_source": "mcu_status",
                "alarm_reason": f"status bit[2:0]=0x{mcu_alert:02X}",
            }

    # ── 2. 派生距离告警 (带滞回，只用 alarm_window_points) ──
    if min_dist is not None:
        was_distance_alarm = (
            previous_state is not None
            and previous_state.get("alarm_source") == "derived_distance"
        )
        if min_dist <= DERIVED_ALARM_TOO_NEAR_CM:
            return {
                **result_base,
                "alert_level": 2,
                "is_alert": True,
                "alarm_source": "derived_distance",
                "alarm_reason": "derived_too_near",
                "threshold_cm": DERIVED_ALARM_TOO_NEAR_CM,
            }
        if min_dist <= DERIVED_ALARM_NEAR_CM:
            return {
                **result_base,
                "alert_level": 1,
                "is_alert": True,
                "alarm_source": "derived_distance",
                "alarm_reason": "derived_near_obstacle",
                "threshold_cm": DERIVED_ALARM_NEAR_CM,
            }
        # 滞回：之前是距离告警，需要 > 60cm 才清除
        if was_distance_alarm and min_dist <= DERIVED_ALARM_CLEAR_CM:
            # 维持上一个等级
            prev_reason = previous_state.get("alarm_reason", "derived_near_obstacle")
            prev_level = previous_state.get("alert_level", 1)
            return {
                **result_base,
                "alert_level": prev_level,
                "is_alert": True,
                "alarm_source": "derived_distance",
                "alarm_reason": prev_reason,
                "threshold_cm": DERIVED_ALARM_CLEAR_CM,
            }

    # ── 3. 派生无有效点告警 (真正检查超时) ──────────────────
    if now_ms is not None and not alarm_window_points:
        prev_last_point_ms = (
            previous_state.get("last_point_ms")
            if previous_state is not None
            else None
        )
        if prev_last_point_ms is not None:
            elapsed_ms = now_ms - prev_last_point_ms
            if elapsed_ms >= DERIVED_NO_POINTS_MS:
                return {
                    **result_base,
                    "alert_level": 1,
                    "is_alert": True,
                    "alarm_source": "derived_no_valid_points",
                    "alarm_reason": "derived_no_valid_points",
                }
            # 未超时：之前如果是 alert 状态则保持，避免数据间隙误发 clear
            if previous_state is not None and previous_state.get("is_alert"):
                return dict(previous_state, min_distance_cm=min_dist, last_point_ms=last_point_ms)

    # ── 4. 正常 ─────────────────────────────────────────────
    return result_base


def alarm_state_changed(current, previous):
    """判断告警状态是否发生变化 (等级或原因)。

    Args:
        current: compute_derived_alarm_state() 返回的 dict
        previous: 上一次返回的 dict，或 None

    Returns:
        bool: 状态是否变化
    """
    if previous is None:
        return False
    return (current["alert_level"] != previous["alert_level"]
            or current["alarm_reason"] != previous["alarm_reason"])


# ── telemetry payload 构建 ────────────────────────────────────

def build_telemetry_dict(*, device_id, mode, visible_points,
                         sweep_points, current_point,
                         reassembly, replay_progress_pct=None):
    """构建 telemetry payload dict (03 §5.3.2)。

    纯计算函数，不依赖 MQTT / UI / CSV 句柄。

    Args:
        device_id: MQTT device_id
        mode: "live" | "replay"
        visible_points: 当前可见 LidarPoint 列表
        sweep_points: 最近一圈 sweep 点列表
        current_point: 当前最新 LidarPoint 或 None
        reassembly: dict(ok, timeout, overwrite_a, overwrite_b, pending)
        replay_progress_pct: float | None，回放进度百分比

    Returns:
        dict: 可直接传给 MqttOutput.publish_telemetry() 的 payload
    """
    import time

    min_dist, min_angle = compute_min_distance(visible_points) if visible_points else (None, None)

    telemetry = {
        "device_id": device_id,
        "mode": mode,
        "ts": int(time.time() * 1000),
        "point_count": len(visible_points),
        "sweep_point_count": len(sweep_points),
        "min_distance_cm": min_dist,
        "min_distance_angle_deg": round(min_angle, 2) if min_angle is not None else None,
        "latest_quality": current_point.quality if current_point is not None else None,
        "latest_status": current_point.status if current_point is not None else None,
        "reassembly": reassembly,
    }
    if replay_progress_pct is not None:
        telemetry["replay_progress_pct"] = round(replay_progress_pct, 1)
    return telemetry


# ── 设备状态汇总 ────────────────────────────────────────────────

def compute_device_summary(*, mode, visible_points, sweep_points,
                           current_point, reassembly, replay_progress_pct=None):
    """构建设备状态汇总 dict，供 UI 状态面板和日志输出使用。

    纯计算函数，不依赖 PySide6 / pyqtgraph / Paho / CSV。

    Args:
        mode: "live" | "replay"
        visible_points: 当前可见 LidarPoint 列表
        sweep_points: 最近一圈 sweep 点列表
        current_point: 当前最新 LidarPoint 或 None
        reassembly: dict(ok, timeout, overwrite_a, overwrite_b, pending)
        replay_progress_pct: float | None

    Returns:
        dict: {
            mode, point_count, sweep_point_count,
            min_distance_cm, min_distance_angle_deg,
            alert_level, is_alert,
            sectors: list[dict],
            reassembly,
            replay_progress_pct,
        }
    """
    min_dist, min_angle = compute_min_distance(visible_points)
    alert_level, is_alert = compute_alarm_state(current_point) if current_point else (0, False)
    sectors = compute_sector_summary(visible_points)

    summary = {
        "mode": mode,
        "point_count": len(visible_points),
        "sweep_point_count": len(sweep_points),
        "min_distance_cm": min_dist,
        "min_distance_angle_deg": round(min_angle, 2) if min_angle is not None else None,
        "alert_level": alert_level,
        "is_alert": is_alert,
        "sectors": sectors,
        "reassembly": reassembly,
    }
    if replay_progress_pct is not None:
        summary["replay_progress_pct"] = round(replay_progress_pct, 1)
    return summary
