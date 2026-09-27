# 2026-05-10 Windows Board Derived Alarm Evidence

Source: user-provided `mosquitto_sub` screenshot from the Windows board run.

The log proves that `lidar/01/alarm` is emitted during physical blocking / near-obstacle testing. The observed alarm is derived by the Linux/Windows gateway layer, not by MCU `status & 0x07`.

Key observations:

- `lidar/01/alarm` appeared interleaved with `lidar/01/telemetry`, which is expected: telemetry is periodic, alarm is state-change/event output.
- `latest_status` stayed at `8`; this is `STATUS_ESTIMATED` (`0x08`) and is not an MCU alert bit.
- Derived alarm sources were visible:
  - `alarm_source="derived_distance"`, `alarm_reason="derived_too_near"`, `alarm_status=2`, `threshold_cm=30`, `min_distance_cm=28`
  - `alarm_source="derived_no_valid_points"`, `alarm_reason="derived_no_valid_points"`, `alarm_status=1`
  - `alarm_source="derived_distance"`, `alarm_reason="derived_near_obstacle"`, `alarm_status=1`, `threshold_cm=50`, `min_distance_cm=31`
- `reassembly.ok` continued increasing during the test, so the CAN stream was not fully broken while blocking occurred.

Representative payload shape:

```text
lidar/01/alarm {
  "device_id": "lidar-01",
  "alarm": true,
  "alarm_status": 2,
  "alarm_source": "derived_distance",
  "alarm_reason": "derived_too_near",
  "threshold_cm": 30,
  "min_distance_cm": 28,
  "alarm_description": "derived_distance: derived_too_near",
  "latest_point": {"distance_cm": 28, "quality": 255, "status": 8}
}
```

Conclusion: real board alarm publication is PASS for the M6.5 MQTT stage, using gateway-derived alarm semantics.
