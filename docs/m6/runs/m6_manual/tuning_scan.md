# M6 Tuning Scan

This scan changes only offline analysis parameters. Raw CSV files and MCU firmware are unchanged.

## Baseline

| parameter / metric | value |
| --- | ---: |
| angle_offset_deg | 0.00 |
| box_min_distance_mm | 280.00 |
| box_max_distance_mm | 1000.00 |
| gap_threshold_mm | 120.00 |
| box_edge_rmse_mm | 16.76 |
| box_repeatability_p95_mm | 20.00 |
| box_gap_count | 3 |
| wall_line_rmse_mm | 7.44 |
| wall_repeat_offset_mm | 6.31 |

## Recommended Offline Configuration

| parameter / metric | value |
| --- | ---: |
| angle_offset_deg | 3.00 |
| box_min_distance_mm | 280.00 |
| box_max_distance_mm | 1000.00 |
| gap_threshold_mm | 120.00 |
| box_edge_rmse_mm | 15.69 |
| box_repeatability_p95_mm | 20.00 |
| box_gap_count | 3 |
| wall_line_rmse_mm | 7.44 |
| wall_repeat_offset_mm | 6.34 |
| score | 22.30 |

## Top 10 Candidates

| rank | score | offset_deg | box_min_mm | box_max_mm | gap_mm | box_edge_rmse | wall_rmse | box_gap | wall_gap |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 22.30 | 3.00 | 280.00 | 1000.00 | 120.00 | 15.69 | 7.44 | 3 | 5 |
| 2 | 22.35 | 3.00 | 280.00 | 1000.00 | 80.00 | 15.69 | 7.44 | 3 | 6 |
| 3 | 22.60 | 2.00 | 280.00 | 1000.00 | 120.00 | 16.07 | 7.44 | 3 | 5 |
| 4 | 22.65 | 2.00 | 280.00 | 1000.00 | 80.00 | 16.07 | 7.44 | 3 | 6 |
| 5 | 22.83 | 1.00 | 280.00 | 1000.00 | 120.00 | 16.24 | 7.44 | 3 | 5 |
| 6 | 22.88 | 1.00 | 280.00 | 1000.00 | 80.00 | 16.24 | 7.44 | 3 | 6 |
| 7 | 23.49 | 0.00 | 280.00 | 1000.00 | 120.00 | 16.76 | 7.44 | 3 | 5 |
| 8 | 23.54 | 0.00 | 280.00 | 1000.00 | 80.00 | 16.76 | 7.44 | 3 | 6 |
| 9 | 23.73 | -1.00 | 280.00 | 1000.00 | 120.00 | 17.12 | 7.44 | 3 | 5 |
| 10 | 23.78 | -1.00 | 280.00 | 1000.00 | 80.00 | 17.12 | 7.44 | 3 | 6 |

## Interpretation

- A constant angle offset mostly rotates the XY frame; it should not be expected to fix curvature by itself.
- If the recommended score improves mainly through distance filtering, keep this as an analysis/display policy rather than changing MCU data.
- If future wall RMSE becomes high under the same scan, then re-open synchronization or mounting diagnostics.
