# M9 Rule Quality Gate Appendix Report - m6_wall_01

- Input: `docs\m8\datasets\known_scenes\m6_wall_01\m6_wall_01.csv`
- Filtered CSV: `docs\m9\runs\rule_based_v1\known_scenes\m6_wall_01\m6_wall_01.m9_filtered.csv`

## Metrics

| metric | value |
| --- | ---: |
| `total_rows` | 2284 |
| `valid_inputs` | 2284 |
| `kept_points` | 2265 |
| `filtered_points` | 19 |
| `filtered_ratio` | 0.00831874 |
| `status_estimated_count` | 2284 |
| `status_estimated_ratio` | 1 |
| `continuity_issue_count` | 2 |
| `continuity_issue_ratio` | 0.000875657 |
| `stability_issue_count` | 18 |
| `stability_issue_ratio` | 0.00788091 |

## Rule Reasons

| reason | count |
| --- | ---: |
| `distance_jump` | 2 |
| `unstable_angle_bin` | 18 |

## Boundary

- This is rule-level point quality screening, not scene ground truth.
- `status=0x08` is tracked as an estimated flag and is not treated as an alert by itself.
- The stability rule uses repeated distance behavior within angle bins; moving targets or changed scenes still need manual labels.
