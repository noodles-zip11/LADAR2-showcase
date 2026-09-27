"""replay alarm state-change verification - no hardware, no broker, no PySide6.

Verifies Prompt 11 core requirement:
  normal -> alarm -> normal produces alarm=true and alarm=false publishes,
  even within a single frame.

Test method:
  Feed a sequence of mock points through a minimal alarm detector that
  mirrors the core logic, verifying each state-change triggers a publish.
"""
import json
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


# -- Mock LidarPoint --------------------------------------------------

class _FakePoint:
    """Minimal point stand-in with only the fields alarm detection needs."""
    def __init__(self, status, quality=10, distance_cm=100, angle_deg=45.0):
        self.status = status
        self.quality = quality
        self.distance_cm = distance_cm
        self.angle_deg = angle_deg


# -- Load STATUS_ALERT_MASK via importlib -----------------------------

def _get_alert_mask():
    """Controlled import to avoid triggering PySide6."""
    import importlib
    core = importlib.import_module("can_core")
    return core.STATUS_ALERT_MASK


# -- Minimal alarm detector (mirrors the core logic) ------------------

class _MiniAlarmDetector:
    """State-tracker that mirrors alarm detection core logic.

    Initial state (None) records the first point's alert_level without
    publishing, matching the real _check_and_publish_alarm behavior.
    """

    def __init__(self, alert_mask):
        self._mask = alert_mask
        self._last_state = None  # None = no history yet
        self.published = []      # list of published alarm payloads

    def check(self, point):
        if point is None:
            return
        alert_level = point.status & self._mask
        # initial state: record but don't publish
        if self._last_state is None:
            self._last_state = alert_level
            return
        if alert_level == self._last_state:
            return
        self._last_state = alert_level
        self.published.append({
            "alarm": alert_level != 0,
            "alarm_status": alert_level,
            "status_raw": point.status,
        })


# -- Test cases -------------------------------------------------------

def test_transient_alarm(alert_mask):
    """normal(0) -> alarm(3) -> normal(0) should trigger 2 publishes."""
    detector = _MiniAlarmDetector(alert_mask)

    # normal point (no alarm)
    p1 = _FakePoint(status=0)
    detector.check(p1)
    assert_equal(len(detector.published), 0, "first normal point should not publish")

    # alarm point
    p2 = _FakePoint(status=3)
    detector.check(p2)
    assert_equal(len(detector.published), 1, "alarm point triggers 1 publish")
    assert_equal(detector.published[0]["alarm"], True, "alarm trigger: alarm=true")
    assert_equal(detector.published[0]["alarm_status"], 3, "alarm trigger: alarm_status=3")

    # back to normal
    p3 = _FakePoint(status=0)
    detector.check(p3)
    assert_equal(len(detector.published), 2, "recovery triggers 2nd publish")
    assert_equal(detector.published[1]["alarm"], False, "alarm recovery: alarm=false")
    assert_equal(detector.published[1]["alarm_status"], 0, "alarm recovery: alarm_status=0")

    print("[PASS] transient alarm: 0->3->0 triggers 2 publishes")


def test_sustained_alarm_no_duplicate(alert_mask):
    """Consecutive alarm points should not duplicate."""
    detector = _MiniAlarmDetector(alert_mask)

    detector.check(_FakePoint(status=0))
    assert_equal(len(detector.published), 0, "initial normal no publish")

    detector.check(_FakePoint(status=3))
    assert_equal(len(detector.published), 1, "first alarm triggers 1")

    detector.check(_FakePoint(status=3))
    assert_equal(len(detector.published), 1, "duplicate alarm no publish")

    detector.check(_FakePoint(status=3))
    assert_equal(len(detector.published), 1, "triple alarm still no duplicate")

    print("[PASS] sustained alarm: 3->3->3 no duplicate")


def test_alert_level_change(alert_mask):
    """Different alarm levels should trigger publishes (status=3 -> status=5)."""
    detector = _MiniAlarmDetector(alert_mask)

    # first point is alarm Lv3, which sets initial state (no publish yet)
    detector.check(_FakePoint(status=3))
    assert_equal(len(detector.published), 0, "first alarm sets initial state, no publish")

    # change to Lv5 triggers publish
    detector.check(_FakePoint(status=5))
    assert_equal(len(detector.published), 1, "alert level change triggers publish")
    assert_equal(detector.published[0]["alarm"], True, "Lv5 is alarm")
    assert_equal(detector.published[0]["alarm_status"], 5, "alarm_status=5")

    print("[PASS] alert level change: 3->5 triggers publish")


def test_estimated_flag(alert_mask):
    """bit[3] (ESTIMATED) must not affect alarm detection."""
    detector = _MiniAlarmDetector(alert_mask)

    # status=0x08 (ESTIMATED, no alert) - should not trigger
    detector.check(_FakePoint(status=0x08))
    assert_equal(len(detector.published), 0, "ESTIMATED flag alone no alarm")

    # status=0x0B (ESTIMATED + alert=3) - should trigger
    detector.check(_FakePoint(status=0x0B))
    assert_equal(len(detector.published), 1, "ESTIMATED+alert triggers")
    assert_equal(detector.published[0]["alarm_status"], 3, "mask correctly ignores bit[3]")

    print("[PASS] estimated flag (0x08) does not affect alert detection")


def test_many_points_same_frame(alert_mask):
    """Simulate many points in one frame: 0->3->0->5->0, capture every edge."""
    detector = _MiniAlarmDetector(alert_mask)

    sequence = [0, 3, 0, 5, 0]
    for s in sequence:
        detector.check(_FakePoint(status=s))

    assert_equal(len(detector.published), 4,
                 "0->3->0->5->0 triggers 4 publishes (one per adjacent change)")
    assert_equal(detector.published[0]["alarm_status"], 3, "publish #1: status=3")
    assert_equal(detector.published[1]["alarm_status"], 0, "publish #2: status=0")
    assert_equal(detector.published[2]["alarm_status"], 5, "publish #3: status=5")
    assert_equal(detector.published[3]["alarm_status"], 0, "publish #4: status=0")

    print("[PASS] many points same frame: all state changes captured")


def test_replay_point_by_point(alert_mask):
    """Simulate replay time advance, checking alarm per-point."""
    detector = _MiniAlarmDetector(alert_mask)

    # simulated CSV replay point sequence
    points = [
        _FakePoint(status=0),
        _FakePoint(status=0),
        _FakePoint(status=7),
        _FakePoint(status=7),
        _FakePoint(status=0),
        _FakePoint(status=0),
    ]

    for p in points:
        detector.check(p)

    assert_equal(len(detector.published), 2,
                 "0->0->7->7->0->0 triggers only 2 (first 7 and first 0)")
    assert_equal(detector.published[0]["alarm"], True, "publish #1: alarm=true")
    assert_equal(detector.published[1]["alarm"], False, "publish #2: alarm=false")

    print("[PASS] replay point-by-point: 0->0->7->7->0->0 triggers 2 edge changes")


# -- Derived alarm detector (mirrors can_core.compute_derived_alarm_state) --

class _DerivedAlarmDetector:
    """State-tracker that mirrors compute_derived_alarm_state logic.

    Uses the real can_core function for correctness.
    Simulates monotonic now_ms advancing 100ms per check.
    Supports point=None calls for no-point timeout testing.
    """
    def __init__(self):
        import importlib
        core = importlib.import_module("can_core")
        self._compute = core.compute_derived_alarm_state
        self._changed = core.alarm_state_changed
        self._DERIVED_NO_POINTS_MS = core.DERIVED_NO_POINTS_MS
        self._last_state = None
        self.published = []
        self._now_ms = 100000  # simulated wall clock
        self._last_point_payload = None  # cached latest_point for contract

    def check(self, point, alarm_window_points=None):
        self._now_ms += 100
        if alarm_window_points is None:
            alarm_window_points = [point] if point is not None else []
        state = self._compute(
            current_point=point,
            alarm_window_points=alarm_window_points,
            previous_state=self._last_state,
            now_ms=self._now_ms,
        )
        # Cache latest_point payload for contract compliance
        if point is not None:
            self._last_point_payload = {
                "distance_cm": point.distance_cm,
                "angle_deg": point.angle_deg,
                "quality": point.quality,
                "status": point.status,
            }
        if self._last_state is None:
            self._last_state = state
            return
        if self._changed(state, self._last_state):
            entry = {
                "alarm": state["is_alert"],
                "alarm_status": state["alert_level"],
                "alarm_source": state["alarm_source"],
                "alarm_reason": state["alarm_reason"],
                "min_distance_cm": state["min_distance_cm"],
            }
            if self._last_point_payload is not None:
                entry["latest_point"] = self._last_point_payload
            self.published.append(entry)
        self._last_state = state


# -- Derived alarm test cases --------------------------------------------

def test_derived_mcu_status_still_works():
    """MCU status low-3-bit non-zero still triggers MCU status alarm."""
    detector = _DerivedAlarmDetector()

    detector.check(_FakePoint(status=0, distance_cm=100))
    assert_equal(len(detector.published), 0, "initial normal no publish")

    detector.check(_FakePoint(status=3, distance_cm=100))
    assert_equal(len(detector.published), 1, "MCU alarm triggers publish")
    assert_equal(detector.published[0]["alarm_source"], "mcu_status", "source is mcu_status")
    assert_equal(detector.published[0]["alarm_reason"], "status bit[2:0]=0x03", "reason has status")

    print("[PASS] derived: MCU status alarm still works")


def test_derived_too_near():
    """status=8 + distance<=30cm triggers derived_too_near."""
    detector = _DerivedAlarmDetector()

    # Safe distance with status=8
    detector.check(_FakePoint(status=0x08, distance_cm=100))
    assert_equal(len(detector.published), 0, "safe distance no publish")

    # Too near with status=8
    point = _FakePoint(status=0x08, distance_cm=25)
    detector.check(point, alarm_window_points=[point])
    assert_equal(len(detector.published), 1, "too near triggers")
    assert_equal(detector.published[0]["alarm_source"], "derived_distance", "too near source")
    assert_equal(detector.published[0]["alarm_reason"], "derived_too_near", "too near reason")
    assert_equal(detector.published[0]["alarm_status"], 2, "too near Lv2")

    print("[PASS] derived: status=8 + distance<=30 triggers derived_too_near")


def test_derived_near_obstacle():
    """status=8 + distance<=50cm triggers derived_near_obstacle."""
    detector = _DerivedAlarmDetector()

    detector.check(_FakePoint(status=0x08, distance_cm=100))
    assert_equal(len(detector.published), 0, "safe no publish")

    point = _FakePoint(status=0x08, distance_cm=45)
    detector.check(point, alarm_window_points=[point])
    assert_equal(len(detector.published), 1, "near obstacle triggers")
    assert_equal(detector.published[0]["alarm_reason"], "derived_near_obstacle", "near reason")
    assert_equal(detector.published[0]["alarm_status"], 1, "near Lv1")

    print("[PASS] derived: status=8 + distance<=50 triggers derived_near_obstacle")


def test_derived_clear_on_recovery():
    """Distance recovery to >60cm sends clear alarm."""
    detector = _DerivedAlarmDetector()

    detector.check(_FakePoint(status=0x08, distance_cm=100))

    # Trigger alarm
    point = _FakePoint(status=0x08, distance_cm=25)
    detector.check(point, alarm_window_points=[point])
    assert_equal(len(detector.published), 1, "alarm triggered")

    # Recovery
    point2 = _FakePoint(status=0x08, distance_cm=70)
    detector.check(point2, alarm_window_points=[point2])
    assert_equal(len(detector.published), 2, "clear triggers publish")
    assert_equal(detector.published[1]["alarm_source"], "clear", "clear source")
    assert_equal(detector.published[1]["alarm"], False, "clear alarm=false")

    print("[PASS] derived: distance recovery >60cm sends clear")


def test_derived_safe_distance_no_alarm():
    """status=8 and safe distance: no alarm at all."""
    detector = _DerivedAlarmDetector()

    detector.check(_FakePoint(status=0x08, distance_cm=100))
    assert_equal(len(detector.published), 0, "safe no alarm first")

    detector.check(_FakePoint(status=0x08, distance_cm=80))
    assert_equal(len(detector.published), 0, "safe no alarm second")

    detector.check(_FakePoint(status=0x08, distance_cm=120))
    assert_equal(len(detector.published), 0, "safe no alarm third")

    print("[PASS] derived: status=8 + safe distance = no alarm published")


def test_derived_alarm_preserved_before_timeout():
    """Active distance alarm -> data gap (<500ms) -> no premature clear published."""
    detector = _DerivedAlarmDetector()

    # Establish baseline
    detector.check(_FakePoint(status=0x08, distance_cm=100))

    # Trigger alarm
    point = _FakePoint(status=0x08, distance_cm=25)
    detector.check(point, alarm_window_points=[point])
    assert_equal(len(detector.published), 1, "alarm triggered")

    # Data gap: point=None, alarm_window_points=[] — 100ms increments per check
    # 5 checks = 500ms, but each is +100 so after 4 checks = 400ms < 500ms
    for _ in range(4):
        detector.check(None, alarm_window_points=[])
    assert_equal(len(detector.published), 1, "no premature clear before timeout")

    print("[PASS] derived: active alarm preserved during data gap before timeout")


def test_derived_no_valid_points_after_timeout():
    """Active alarm -> data gap (>500ms) -> derived_no_valid_points published."""
    detector = _DerivedAlarmDetector()

    # Establish baseline
    detector.check(_FakePoint(status=0x08, distance_cm=100))

    # Trigger alarm
    point = _FakePoint(status=0x08, distance_cm=25)
    detector.check(point, alarm_window_points=[point])
    assert_equal(len(detector.published), 1, "alarm triggered")

    # Data gap: 10 more checks × 100ms = 1000ms total since alarm > 500ms threshold
    for _ in range(10):
        detector.check(None, alarm_window_points=[])

    assert_equal(len(detector.published), 2, "no_valid_points published after timeout")
    assert_equal(detector.published[1]["alarm_source"], "derived_no_valid_points",
                 "source is derived_no_valid_points")
    assert_equal(detector.published[1]["alarm_reason"], "derived_no_valid_points",
                 "reason is derived_no_valid_points")

    print("[PASS] derived: no_valid_points published after timeout")


def test_derived_no_valid_points_has_latest_point():
    """No-valid-points alarm payload includes cached latest_point."""
    detector = _DerivedAlarmDetector()

    # Send a real point
    detector.check(_FakePoint(status=0x08, distance_cm=100))

    # Trigger alarm then wait for timeout
    point = _FakePoint(status=0x08, distance_cm=25)
    detector.check(point, alarm_window_points=[point])
    assert_equal(len(detector.published), 1, "distance alarm")

    # Wait for no_valid_points timeout (>500ms)
    for _ in range(10):
        detector.check(None, alarm_window_points=[])

    assert_equal(len(detector.published), 2, "no_valid_points published")
    no_valid_pub = detector.published[1]
    assert_true("latest_point" in no_valid_pub, "no_valid alarm has latest_point")
    assert_equal(no_valid_pub["latest_point"]["distance_cm"], 25,
                 "latest_point is from last real point")

    print("[PASS] derived: no_valid_points alarm includes cached latest_point")


# -- main -------------------------------------------------------------

def main():
    alert_mask = _get_alert_mask()
    assert_equal(alert_mask, 0x07, "STATUS_ALERT_MASK == 0x07")

    print("selfcheck_replay_alarm - alarm state-change verification")
    print()

    test_transient_alarm(alert_mask)
    test_sustained_alarm_no_duplicate(alert_mask)
    test_alert_level_change(alert_mask)
    test_estimated_flag(alert_mask)
    test_many_points_same_frame(alert_mask)
    test_replay_point_by_point(alert_mask)

    # Derived alarm tests
    test_derived_mcu_status_still_works()
    test_derived_too_near()
    test_derived_near_obstacle()
    test_derived_clear_on_recovery()
    test_derived_safe_distance_no_alarm()
    test_derived_alarm_preserved_before_timeout()
    test_derived_no_valid_points_after_timeout()
    test_derived_no_valid_points_has_latest_point()

    print()
    print("PASS: selfcheck_replay_alarm - all alarm edge detection tests passed (including derived alarms)")


if __name__ == "__main__":
    main()
