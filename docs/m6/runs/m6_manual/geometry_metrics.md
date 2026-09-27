# M6 Geometry Metrics

## Box Far Metrics

| metric | value | note |
| --- | ---: | --- |
| repeatability_p95_mm | 20.00 | radial median profile p95 across common 1 deg bins |
| seam_gap_mm | 11.82 | worst 0/360 median XY seam gap |
| box_edge_rmse_mm | 16.76 | combined four-edge PCA perpendicular RMSE |
| point_drop_or_gap_count | 3 | adjacent XY jumps greater than 120 mm |

### Box Inputs

| file | raw_points | accepted_points |
| --- | ---: | ---: |
| data/repeat_far_01.csv | 3268 | 3268 |
| data/repeat_far_02.csv | 3325 | 3325 |
| data/repeat_far_03.csv | 3269 | 3269 |

### Box Edge Details

| edge | points | rmse_mm | residual_p95_mm | span_mm_p5_to_p95 |
| --- | ---: | ---: | ---: | ---: |
| left | 1397 | 18.88 | 30.91 | 398.10 |
| right | 2180 | 15.94 | 34.62 | 379.86 |
| bottom | 1219 | 20.42 | 32.70 | 336.52 |
| top | 1670 | 12.37 | 23.79 | 369.39 |

### Box Gap Count

| run | gap_count |
| --- | ---: |
| repeat_far_01 | 1 |
| repeat_far_02 | 1 |
| repeat_far_03 | 1 |

## Wall Metrics

- wall_angle_window_deg: `350 -> 40`
- wall_distance_window_mm: `350 -> 1000`

| metric | value | note |
| --- | ---: | --- |
| wall_line_rmse_mm | 7.44 | combined wall segment PCA perpendicular RMSE |
| wall_line_residual_p95_mm | 13.09 | p95 absolute perpendicular residual |
| wall_span_mm_p5_to_p95 | 426.74 | fitted visible wall span |
| wall_repeat_offset_mm | 6.31 | max run-center offset from median run center |
| wall_gap_count | 5 | adjacent selected wall XY jumps greater than 120 mm |

### Wall Inputs

| file | selected_points | line_rmse_mm | residual_p95_mm | span_mm_p5_to_p95 | center_xy_mm |
| --- | ---: | ---: | ---: | ---: | --- |
| data/wall_01.csv | 463 | 7.86 | 13.58 | 421.21 | (492.41, 167.97) |
| data/wall_02.csv | 432 | 7.45 | 13.13 | 431.53 | (494.87, 159.68) |
| data/wall_03.csv | 547 | 6.87 | 12.29 | 426.88 | (495.53, 162.15) |

### Wall Gap Count

| run | gap_count |
| --- | ---: |
| wall_01 | 2 |
| wall_02 | 2 |
| wall_03 | 1 |

## Images

- box_far_overlay: `assets/box_far_overlay.png`
- box_far_edge_fit: `assets/box_far_edge_fit.png`
- box_far_seam_closeup: `assets/box_far_seam_closeup.png`
- wall_overlay: `assets/wall_overlay.png`
- wall_selected_segment: `assets/wall_selected_segment.png`
- wall_line_fit: `assets/wall_line_fit.png`
