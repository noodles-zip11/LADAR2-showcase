# M6 Geometry Quality and Synchronization

M6 keeps the MCU firmware unchanged and evaluates geometry quality from saved CSV point clouds.

The current baseline run is:

- `docs/m6/runs/m6_manual/`

The run contains two analysis groups:

| group | CSV files | purpose |
| --- | --- | --- |
| box far | `repeat_far_01.csv`, `repeat_far_02.csv`, `repeat_far_03.csv` | whole-shape repeatability, seam closure, four-edge quality |
| wall | `wall_01.csv`, `wall_02.csv`, `wall_03.csv` | single-wall straightness and repeat offset |

## Reproduce

From the repository root:

```powershell
py -3 .\tools\m6_group_analysis.py --run-dir .\docs\m6\runs\m6_manual
```

To scan offline tuning parameters:

```powershell
py -3 .\tools\m6_tuning_scan.py --run-dir .\docs\m6\runs\m6_manual
```

This regenerates:

- `geometry_metrics.md`
- `strategy_analysis.md`
- `tuning_notes.md`
- `assets/box_far_overlay.png`
- `assets/box_far_edge_fit.png`
- `assets/box_far_seam_closeup.png`
- `assets/wall_overlay.png`
- `assets/wall_selected_segment.png`
- `assets/wall_line_fit.png`
- `tuning_scan.csv`
- `tuning_scan.md`

## Current Policy

- Raw CSV files are evidence and should not be modified.
- Filtering belongs in offline analysis or display logic, not in MCU output.
- Current wall selection is `angle_deg >= 350` or `angle_deg <= 40`, with distance `350-1000 mm`.
- Large adjacent XY jumps use a `120 mm` break threshold.
- MCU synchronization changes are deferred until wall tests show a persistent large error.
- Current offline/display tuning candidate is recorded in `runs/m6_manual/analysis_config.md`.
