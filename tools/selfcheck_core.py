"""core 业务计算自检 — 不上板、不连 Broker, 纯函数验证。

覆盖 Prompt 14 要求的 core 层合同:
  - compute_min_distance: 空点集、正常点集
  - compute_sector_summary: 扇区统计
  - compute_alarm_state: 告警点 status & 0x07, ESTIMATED bit 0x08
  - build_telemetry_dict: 字段完整性
  - compute_device_summary: 汇总字段完整性
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def fail(message):
    print(f"FAIL: {message}")
    sys.exit(1)


def assert_equal(actual, expected, context):
    if actual != expected:
        fail(f"{context}: expected {expected!r}, got {actual!r}")


def assert_true(cond, context):
    if not cond:
        fail(f"{context}: expected True")


# -- Mock point ----------------------------------------------------------

class _FakePoint:
    def __init__(self, distance_cm, angle_deg, status=0, quality=10):
        self.distance_cm = distance_cm
        self.angle_deg = angle_deg
        self.status = status
        self.quality = quality


# -- Compute min distance ------------------------------------------------

def test_min_distance_empty():
    from can_core import compute_min_distance

    dist, ang = compute_min_distance([])
    assert_true(dist is None, "empty: min dist is None")
    assert_true(ang is None, "empty: min angle is None")

    dist, ang = compute_min_distance(None)
    assert_true(dist is None, "None input: min dist is None")

    print("[PASS] compute_min_distance: empty input -> None")


def test_min_distance_normal():
    from can_core import compute_min_distance

    points = [
        _FakePoint(distance_cm=150, angle_deg=10.0),
        _FakePoint(distance_cm=45, angle_deg=90.0),
        _FakePoint(distance_cm=200, angle_deg=180.0),
    ]
    dist, ang = compute_min_distance(points)
    assert_equal(dist, 45, "min distance")
    assert_equal(round(ang, 1), 90.0, "min distance angle")

    print("[PASS] compute_min_distance: normal points")


# -- Compute sector summary ----------------------------------------------

def test_sector_summary():
    from can_core import compute_sector_summary, DEFAULT_SECTOR_DEFS

    # Empty
    sectors = compute_sector_summary([])
    assert_equal(len(sectors), 4, "4 sectors by default")
    for sec in sectors:
        assert_equal(sec["point_count"], 0, f"{sec['name']} empty count")
        assert_true(sec["min_distance_cm"] is None, f"{sec['name']} empty min_dist")
        assert_equal(sec["alert_level"], 0, f"{sec['name']} empty alert")

    # Points in front/right/rear/left
    points = [
        _FakePoint(distance_cm=50,  angle_deg=0.0,  status=0),    # Front
        _FakePoint(distance_cm=80,  angle_deg=90.0, status=3),    # Right (alert)
        _FakePoint(distance_cm=120, angle_deg=170.0, status=0),   # Rear
        _FakePoint(distance_cm=60,  angle_deg=200.0, status=0),   # Rear
        _FakePoint(distance_cm=200, angle_deg=270.0, status=5),   # Left (alert)
        _FakePoint(distance_cm=30,  angle_deg=-30.0, status=0),   # Front (330°)
    ]
    sectors = compute_sector_summary(points)
    by_name = {s["name"]: s for s in sectors}

    assert_equal(by_name["Front"]["point_count"], 2, "Front count")
    assert_equal(by_name["Front"]["min_distance_cm"], 30, "Front min")
    assert_equal(by_name["Front"]["alert_level"], 0, "Front alert")

    assert_equal(by_name["Right"]["point_count"], 1, "Right count")
    assert_equal(by_name["Right"]["min_distance_cm"], 80, "Right min")
    assert_equal(by_name["Right"]["alert_level"], 3, "Right alert")

    assert_equal(by_name["Rear"]["point_count"], 2, "Rear count")
    assert_equal(by_name["Rear"]["min_distance_cm"], 60, "Rear min")
    assert_equal(by_name["Rear"]["alert_level"], 0, "Rear alert")

    assert_equal(by_name["Left"]["point_count"], 1, "Left count")
    assert_equal(by_name["Left"]["min_distance_cm"], 200, "Left min")
    assert_equal(by_name["Left"]["alert_level"], 5, "Left alert")

    print("[PASS] compute_sector_summary: 4-sector distribution correct")


def test_sector_boundary_wrap():
    """Front sector (-45, 45) correctly handles 315°->45° wrap."""
    from can_core import compute_sector_summary

    points = [
        _FakePoint(distance_cm=100, angle_deg=350.0, status=0),  # Front (near 0°)
        _FakePoint(distance_cm=200, angle_deg=10.0,  status=0),  # Front
    ]
    sectors = {s["name"]: s for s in compute_sector_summary(points)}
    assert_equal(sectors["Front"]["point_count"], 2, "Front wrap count")

    print("[PASS] sector boundary wrap: 350° and 10° both go to Front")


# -- Compute alarm state -------------------------------------------------

def test_alarm_state():
    from can_core import compute_alarm_state

    # Normal
    lv, is_alert = compute_alarm_state(_FakePoint(status=0, distance_cm=10, angle_deg=0))
    assert_equal(lv, 0, "normal alert_level")
    assert_true(not is_alert, "normal is_alert=False")

    # Alert Lv3
    lv, is_alert = compute_alarm_state(_FakePoint(status=3, distance_cm=10, angle_deg=0))
    assert_equal(lv, 3, "Lv3 alert_level")
    assert_true(is_alert, "Lv3 is_alert=True")

    # ESTIMATED flag alone (0x08) -> alert_level=0
    lv, is_alert = compute_alarm_state(_FakePoint(status=0x08, distance_cm=10, angle_deg=0))
    assert_equal(lv, 0, "ESTIMATED alone alert_level")
    assert_true(not is_alert, "ESTIMATED alone is_alert=False")

    # ESTIMATED + Lv3 (0x0B) -> alert_level=3
    lv, is_alert = compute_alarm_state(_FakePoint(status=0x0B, distance_cm=10, angle_deg=0))
    assert_equal(lv, 3, "ESTIMATED+Lv3 alert_level")
    assert_true(is_alert, "ESTIMATED+Lv3 is_alert=True")

    # Also works with raw int
    lv, _ = compute_alarm_state(7)
    assert_equal(lv, 7, "raw int alert_level")

    print("[PASS] compute_alarm_state: status mask correct, ESTIMATED ignored")


# -- Build telemetry dict ------------------------------------------------

def test_build_telemetry_dict():
    from can_core import build_telemetry_dict

    points = [
        _FakePoint(distance_cm=100, angle_deg=30.0, status=0, quality=12),
        _FakePoint(distance_cm=50, angle_deg=90.0, status=0, quality=15),
    ]
    sweep_points = list(points)
    current_point = points[-1]

    telemetry = build_telemetry_dict(
        device_id="lidar-test",
        mode="replay",
        visible_points=points,
        sweep_points=sweep_points,
        current_point=current_point,
        reassembly={"ok": 10, "timeout": 0, "overwrite_a": 0, "overwrite_b": 0, "pending": 1},
        replay_progress_pct=45.2,
    )

    required_keys = {
        "device_id", "mode", "ts", "point_count", "sweep_point_count",
        "min_distance_cm", "min_distance_angle_deg", "latest_quality",
        "latest_status", "reassembly",
    }
    for key in required_keys:
        assert_true(key in telemetry, f"telemetry missing {key}")

    assert_equal(telemetry["device_id"], "lidar-test", "telemetry device_id")
    assert_equal(telemetry["mode"], "replay", "telemetry mode")
    assert_equal(telemetry["point_count"], 2, "telemetry point_count")
    assert_equal(telemetry["sweep_point_count"], 2, "telemetry sweep")
    assert_equal(telemetry["min_distance_cm"], 50, "telemetry min_dist")
    assert_equal(telemetry["latest_quality"], 15, "telemetry quality")
    assert_equal(telemetry["latest_status"], 0, "telemetry status")
    assert_equal(telemetry["replay_progress_pct"], 45.2, "telemetry progress")
    assert_true(isinstance(telemetry["ts"], int) and telemetry["ts"] > 0, "telemetry ts positive int")

    # Empty points
    empty_tlm = build_telemetry_dict(
        device_id="lidar-test",
        mode="live",
        visible_points=[],
        sweep_points=[],
        current_point=None,
        reassembly={"ok": 0, "timeout": 0, "overwrite_a": 0, "overwrite_b": 0, "pending": 0},
    )
    assert_true(empty_tlm["min_distance_cm"] is None, "empty telemetry min_dist null")
    assert_true(empty_tlm["latest_quality"] is None, "empty telemetry quality null")

    print("[PASS] build_telemetry_dict: all required fields present")


# -- Compute device summary ----------------------------------------------

def test_device_summary():
    from can_core import compute_device_summary

    points = [
        _FakePoint(distance_cm=100, angle_deg=30.0, status=0, quality=12),
        _FakePoint(distance_cm=50, angle_deg=90.0, status=3, quality=8),
    ]
    summary = compute_device_summary(
        mode="replay",
        visible_points=points,
        sweep_points=points,
        current_point=points[-1],
        reassembly={"ok": 5, "timeout": 1, "overwrite_a": 0, "overwrite_b": 0, "pending": 0},
        replay_progress_pct=50.0,
    )

    assert_equal(summary["mode"], "replay", "summary mode")
    assert_equal(summary["point_count"], 2, "summary point_count")
    assert_equal(summary["sweep_point_count"], 2, "summary sweep")
    assert_equal(summary["min_distance_cm"], 50, "summary min_dist")
    assert_equal(summary["alert_level"], 3, "summary alert_level")
    assert_true(summary["is_alert"], "summary is_alert")
    assert_equal(len(summary["sectors"]), 4, "summary has 4 sectors")
    assert_equal(summary["replay_progress_pct"], 50.0, "summary progress")
    assert_equal(summary["reassembly"]["ok"], 5, "summary reassembly")

    # Empty
    empty_summary = compute_device_summary(
        mode="live",
        visible_points=[],
        sweep_points=[],
        current_point=None,
        reassembly={"ok": 0, "timeout": 0, "overwrite_a": 0, "overwrite_b": 0, "pending": 0},
    )
    assert_equal(empty_summary["point_count"], 0, "empty summary count")
    assert_true(empty_summary["min_distance_cm"] is None, "empty summary min_dist")
    assert_equal(empty_summary["alert_level"], 0, "empty summary alert")
    assert_true(not empty_summary["is_alert"], "empty summary not alert")

    print("[PASS] compute_device_summary: all fields correct")


# -- Derived alarm state -------------------------------------------------

def test_derived_alarm_mcu_status_priority():
    """MCU status alert takes highest priority over derived distance."""
    from can_core import compute_derived_alarm_state

    point = _FakePoint(distance_cm=10, angle_deg=0.0, status=3)
    window = [point, _FakePoint(distance_cm=10, angle_deg=45.0, status=0)]

    state = compute_derived_alarm_state(point, window)
    assert_equal(state["alarm_source"], "mcu_status", "MCU status source")
    assert_equal(state["alert_level"], 3, "MCU alert level")
    assert_true(state["is_alert"], "MCU is_alert")

    print("[PASS] derived alarm: MCU status takes priority over distance")


def test_derived_alarm_too_near():
    """distance <= 30cm triggers Lv2 derived_too_near."""
    from can_core import compute_derived_alarm_state

    point = _FakePoint(distance_cm=25, angle_deg=0.0, status=0x08)
    window = [point, _FakePoint(distance_cm=40, angle_deg=90.0, status=0x08)]

    state = compute_derived_alarm_state(point, window)
    assert_equal(state["alarm_source"], "derived_distance", "too near source")
    assert_equal(state["alarm_reason"], "derived_too_near", "too near reason")
    assert_equal(state["alert_level"], 2, "too near level")
    assert_equal(state["threshold_cm"], 30, "too near threshold")
    assert_equal(state["min_distance_cm"], 25, "too near min_dist")

    print("[PASS] derived alarm: distance<=30cm triggers derived_too_near Lv2")


def test_derived_alarm_near_obstacle():
    """distance <= 50cm (but > 30cm) triggers Lv1 derived_near_obstacle."""
    from can_core import compute_derived_alarm_state

    point = _FakePoint(distance_cm=45, angle_deg=0.0, status=0x08)
    window = [point, _FakePoint(distance_cm=60, angle_deg=90.0, status=0x08)]

    state = compute_derived_alarm_state(point, window)
    assert_equal(state["alarm_source"], "derived_distance", "near source")
    assert_equal(state["alarm_reason"], "derived_near_obstacle", "near reason")
    assert_equal(state["alert_level"], 1, "near level")
    assert_equal(state["threshold_cm"], 50, "near threshold")
    assert_equal(state["min_distance_cm"], 45, "near min_dist")

    print("[PASS] derived alarm: distance<=50cm triggers derived_near_obstacle Lv1")


def test_derived_alarm_clear():
    """Distance > 60cm clears derived distance alarm."""
    from can_core import compute_derived_alarm_state

    point = _FakePoint(distance_cm=70, angle_deg=0.0, status=0x08)
    window = [point, _FakePoint(distance_cm=80, angle_deg=90.0, status=0x08)]

    # First establish a distance alarm
    prev_state = {
        "alert_level": 1,
        "is_alert": True,
        "alarm_source": "derived_distance",
        "alarm_reason": "derived_near_obstacle",
        "threshold_cm": 50,
        "min_distance_cm": 45,
        "last_point_ms": 99000,
    }

    state = compute_derived_alarm_state(point, window, previous_state=prev_state)
    assert_equal(state["alarm_source"], "clear", "clear source")
    assert_equal(state["alert_level"], 0, "clear level")
    assert_true(not state["is_alert"], "clear is_alert=False")

    print("[PASS] derived alarm: distance>60cm clears alarm")


def test_derived_alarm_hysteresis():
    """Hysteresis: distance between 50-60cm maintains previous alarm level."""
    from can_core import compute_derived_alarm_state

    point = _FakePoint(distance_cm=55, angle_deg=0.0, status=0x08)
    window = [point]

    prev_state = {
        "alert_level": 1,
        "is_alert": True,
        "alarm_source": "derived_distance",
        "alarm_reason": "derived_near_obstacle",
        "threshold_cm": 50,
        "min_distance_cm": 45,
        "last_point_ms": 99000,
    }

    state = compute_derived_alarm_state(point, window, previous_state=prev_state)
    assert_equal(state["alarm_source"], "derived_distance", "hysteresis source")
    assert_equal(state["alert_level"], 1, "hysteresis level maintained")
    assert_true(state["is_alert"], "hysteresis still alert")
    assert_equal(state["threshold_cm"], 60, "hysteresis threshold is clear level")

    print("[PASS] derived alarm: hysteresis maintains alarm between 50-60cm")


def test_derived_alarm_safe_distance_no_alarm():
    """status=8 (estimated) and safe distance produces no alarm."""
    from can_core import compute_derived_alarm_state

    point = _FakePoint(distance_cm=100, angle_deg=0.0, status=0x08)
    window = [point, _FakePoint(distance_cm=120, angle_deg=90.0, status=0x08)]

    state = compute_derived_alarm_state(point, window)
    assert_equal(state["alarm_source"], "clear", "safe source")
    assert_equal(state["alert_level"], 0, "safe level")
    assert_true(not state["is_alert"], "safe is_alert=False")

    print("[PASS] derived alarm: status=8 + safe distance = no alarm")


def test_derived_alarm_no_valid_points_timeout():
    """Empty alarm window + elapsed >= DERIVED_NO_POINTS_MS triggers alarm."""
    from can_core import compute_derived_alarm_state, DERIVED_NO_POINTS_MS

    prev_state = {
        "alert_level": 0,
        "is_alert": False,
        "alarm_source": "clear",
        "alarm_reason": "alarm cleared",
        "threshold_cm": None,
        "min_distance_cm": 100,
        "last_point_ms": 100000,
    }

    # now_ms - last_point_ms = 100800 - 100000 = 800ms >= 500ms -> trigger
    state = compute_derived_alarm_state(
        None, alarm_window_points=[], previous_state=prev_state, now_ms=100800,
    )
    assert_equal(state["alarm_source"], "derived_no_valid_points", "timeout source")
    assert_equal(state["alert_level"], 1, "timeout level")
    assert_true(state["is_alert"], "timeout is_alert")

    print("[PASS] derived alarm: no valid points after timeout triggers alarm")


def test_derived_alarm_no_valid_points_not_yet_timeout():
    """Empty alarm window + elapsed < DERIVED_NO_POINTS_MS does NOT trigger."""
    from can_core import compute_derived_alarm_state, DERIVED_NO_POINTS_MS

    prev_state = {
        "alert_level": 0,
        "is_alert": False,
        "alarm_source": "clear",
        "alarm_reason": "alarm cleared",
        "threshold_cm": None,
        "min_distance_cm": 100,
        "last_point_ms": 100000,
    }

    # now_ms - last_point_ms = 100300 - 100000 = 300ms < 500ms -> no trigger
    state = compute_derived_alarm_state(
        None, alarm_window_points=[], previous_state=prev_state, now_ms=100300,
    )
    assert_equal(state["alarm_source"], "clear", "not yet timeout source")
    assert_equal(state["alert_level"], 0, "not yet timeout level")

    print("[PASS] derived alarm: no valid points before timeout does NOT trigger")


def test_derived_alarm_no_valid_points_startup_grace():
    """No valid points without last_point_ms does NOT trigger alarm (startup grace)."""
    from can_core import compute_derived_alarm_state

    state = compute_derived_alarm_state(
        None, alarm_window_points=[], previous_state=None, now_ms=100000,
    )
    assert_equal(state["alarm_source"], "clear", "startup grace source")
    assert_equal(state["alert_level"], 0, "startup grace level")

    print("[PASS] derived alarm: startup grace prevents false no_valid_points alarm")


def test_derived_alarm_preserves_alert_before_timeout():
    """During data gap before timeout, active alert is preserved (no premature clear)."""
    from can_core import compute_derived_alarm_state

    prev_state = {
        "alert_level": 2,
        "is_alert": True,
        "alarm_source": "derived_distance",
        "alarm_reason": "derived_too_near",
        "threshold_cm": 30,
        "min_distance_cm": 25,
        "last_point_ms": 100000,
    }

    # now_ms - last_point_ms = 100200 - 100000 = 200ms < 500ms -> preserve alert
    state = compute_derived_alarm_state(
        None, alarm_window_points=[], previous_state=prev_state, now_ms=100200,
    )
    assert_equal(state["alarm_source"], "derived_distance", "preserve source")
    assert_equal(state["alarm_reason"], "derived_too_near", "preserve reason")
    assert_equal(state["alert_level"], 2, "preserve level")
    assert_true(state["is_alert"], "preserve is_alert")

    print("[PASS] derived alarm: active alert preserved during data gap before timeout")


def test_alarm_state_changed():
    """alarm_state_changed detects level and reason changes."""
    from can_core import alarm_state_changed

    state_a = {
        "alert_level": 1,
        "is_alert": True,
        "alarm_source": "derived_distance",
        "alarm_reason": "derived_near_obstacle",
        "threshold_cm": 50,
        "min_distance_cm": 45,
        "last_point_ms": 100000,
    }
    state_b = {
        "alert_level": 2,
        "is_alert": True,
        "alarm_source": "derived_distance",
        "alarm_reason": "derived_too_near",
        "threshold_cm": 30,
        "min_distance_cm": 25,
        "last_point_ms": 100100,
    }
    state_c = {
        "alert_level": 1,
        "is_alert": True,
        "alarm_source": "derived_distance",
        "alarm_reason": "derived_near_obstacle",
        "threshold_cm": 50,
        "min_distance_cm": 45,
        "last_point_ms": 100200,
    }

    # Same state -> no change
    assert_true(not alarm_state_changed(state_a, state_a), "identical state no change")
    # Different level -> change
    assert_true(alarm_state_changed(state_b, state_a), "different level = change")
    # Same level & reason -> no change (even if other fields differ)
    assert_true(not alarm_state_changed(state_a, state_c), "same level+reason no change")
    # None previous -> no change
    assert_true(not alarm_state_changed(state_a, None), "None previous no change")

    print("[PASS] alarm_state_changed: detects level/reason changes correctly")


# -- main ----------------------------------------------------------------

def main():
    print("selfcheck_core — core 业务计算自检 (不上板、不连 Broker)")
    print()

    test_min_distance_empty()
    test_min_distance_normal()
    test_sector_summary()
    test_sector_boundary_wrap()
    test_alarm_state()
    test_build_telemetry_dict()
    test_device_summary()
    test_derived_alarm_mcu_status_priority()
    test_derived_alarm_too_near()
    test_derived_alarm_near_obstacle()
    test_derived_alarm_clear()
    test_derived_alarm_hysteresis()
    test_derived_alarm_safe_distance_no_alarm()
    test_derived_alarm_no_valid_points_timeout()
    test_derived_alarm_no_valid_points_not_yet_timeout()
    test_derived_alarm_no_valid_points_startup_grace()
    test_derived_alarm_preserves_alert_before_timeout()
    test_alarm_state_changed()

    print()
    print("PASS: selfcheck_core — all core business calculation tests passed")


if __name__ == "__main__":
    main()
