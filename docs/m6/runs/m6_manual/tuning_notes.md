# M6 Tuning Notes

## Current Data Split

- Box repeats: `repeat_far_01.csv`, `repeat_far_02.csv`, `repeat_far_03.csv`.
- Wall repeats: `wall_01.csv`, `wall_02.csv`, `wall_03.csv`.
- Wall selection: `angle_deg >= 350` or `angle_deg <= 40`, distance `350-1000 mm`.

## Current Metrics

| group | metric | value |
| --- | --- | ---: |
| box | repeatability_p95_mm | 20.00 |
| box | seam_gap_mm | 11.82 |
| box | box_edge_rmse_mm | 16.76 |
| box | point_drop_or_gap_count | 3 |
| wall | wall_line_rmse_mm | 7.44 |
| wall | wall_line_residual_p95_mm | 13.09 |
| wall | wall_repeat_offset_mm | 6.31 |
| wall | wall_gap_count | 5 |

## Interpretation

- Wall straightness is good enough to treat the core angle-distance pairing as basically usable.
- Box geometry is repeatable but not uniformly straight across all edges, so keep diagnosing at the analysis/display/mechanical level before firmware changes.
- Seam closure is not the primary issue in this dataset.

## Next Action

- Keep MCU firmware unchanged.
- Preserve raw CSV files as evidence.
- Use `tools/m6_group_analysis.py` as the M6 baseline analysis entrypoint.
- If applying display changes later, keep the existing 120 mm large-jump break policy and make it configurable rather than changing raw point coordinates.
