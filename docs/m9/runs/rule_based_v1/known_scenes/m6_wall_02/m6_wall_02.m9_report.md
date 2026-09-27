# M9 Rule Quality Gate Appendix Report - m6_wall_02

- Input: `docs\m8\datasets\known_scenes\m6_wall_02\m6_wall_02.csv`
- Filtered CSV: `docs\m9\runs\rule_based_v1\known_scenes\m6_wall_02\m6_wall_02.m9_filtered.csv`

## Metrics

| metric | value |
| --- | ---: |
| `total_rows` | 2855 |
| `valid_inputs` | 2855 |
| `kept_points` | 2820 |
| `filtered_points` | 35 |
| `filtered_ratio` | 0.0122592 |
| `status_estimated_count` | 2855 |
| `status_estimated_ratio` | 1 |
| `continuity_issue_count` | 12 |
| `continuity_issue_ratio` | 0.00420315 |
| `stability_issue_count` | 27 |
| `stability_issue_ratio` | 0.00945709 |

## Rule Reasons

| reason | count |
| --- | ---: |
| `distance_jump` | 10 |
| `isolated_distance` | 2 |
| `unstable_angle_bin` | 27 |

## Boundary

- This is rule-level point quality screening, not scene ground truth.
- `status=0x08` is tracked as an estimated flag and is not treated as an alert by itself.
- The stability rule uses repeated distance behavior within angle bins; moving targets or changed scenes still need manual labels.
