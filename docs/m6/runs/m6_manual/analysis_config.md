# M6 Analysis Configuration

This configuration is for offline analysis and display experiments only.
It does not change MCU firmware, CAN output, or raw CSV evidence.

## Recommended Current Configuration

| parameter | value | purpose |
| --- | ---: | --- |
| box_min_distance_mm | 280 | keep valid near box returns |
| box_max_distance_mm | 1000 | reject background far points |
| wall_min_distance_mm | 350 | select the measured wall segment |
| wall_max_distance_mm | 1000 | reject background far points |
| wall_angle_start_deg | 350 | wall segment starts before 0 deg |
| wall_angle_end_deg | 40 | wall segment ends after 0 deg |
| gap_threshold_mm | 120 | break large adjacent XY jumps |
| analysis_angle_offset_deg | 3 | offline/display rotation candidate only |

## Important Boundary

`analysis_angle_offset_deg` rotates the offline XY frame. It can make box-edge
classification and display alignment slightly cleaner, but it should not be
treated as proof that MCU synchronization needs a fixed offset.

Current scan result:

- baseline box_edge_rmse_mm: `16.76`
- candidate with `analysis_angle_offset_deg = 3`: `15.69`
- wall_line_rmse_mm remains `7.44`

Because the wall result is already good, keep firmware unchanged and use this
only as a PC-side analysis/display candidate.
