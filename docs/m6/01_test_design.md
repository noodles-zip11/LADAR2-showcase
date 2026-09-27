# M6 Test Design

## Goal

Measure whether the existing point cloud is stable, repeatable, and geometrically explainable using saved CSV data.

M6 does not change MCU firmware in the current stage.

## Data Groups

### Box Repeat Group

Use a rectangular box or similar target. Keep the device and target fixed.

Current files:

- `runs/m6_manual/data/repeat_far_01.csv`
- `runs/m6_manual/data/repeat_far_02.csv`
- `runs/m6_manual/data/repeat_far_03.csv`

Metrics:

- `repeatability_p95_mm`
- `seam_gap_mm`
- `box_edge_rmse_mm`
- `point_drop_or_gap_count`

### Wall Group

Use one wall only. Keep the device and wall fixed.

Current files:

- `runs/m6_manual/data/wall_01.csv`
- `runs/m6_manual/data/wall_02.csv`
- `runs/m6_manual/data/wall_03.csv`

Current wall selection:

- angle window: `350 -> 40 deg`
- distance window: `350 -> 1000 mm`

Metrics:

- `wall_line_rmse_mm`
- `wall_line_residual_p95_mm`
- `wall_repeat_offset_mm`
- `wall_gap_count`

## Analysis Rules

- Use existing `x_mm,y_mm` fields from CSV.
- Keep raw CSV unchanged.
- Exclude out-of-scope distances only inside analysis.
- Do not connect adjacent points when XY jump is greater than `120 mm`.
- Treat wall and box results separately.

## Current Reproduction Command

```powershell
py -3 .\tools\m6_group_analysis.py --run-dir .\docs\m6\runs\m6_manual
```

Tuning scan command:

```powershell
py -3 .\tools\m6_tuning_scan.py --run-dir .\docs\m6\runs\m6_manual
```

## Decision Rule

If wall straightness remains good while box edges remain worse, prioritize mechanical placement, target distance, edge/corner returns, and display/analysis filtering before any MCU synchronization changes.

The current scan keeps `gap_threshold_mm = 120` and recommends treating
`analysis_angle_offset_deg = 3` only as an offline/display candidate, not as an
MCU synchronization change.
