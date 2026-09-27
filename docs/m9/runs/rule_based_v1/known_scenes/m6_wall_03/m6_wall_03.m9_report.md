# M9 Rule Quality Gate Appendix Report - m6_wall_03

- Input: `docs\m8\datasets\known_scenes\m6_wall_03\m6_wall_03.csv`
- Filtered CSV: `docs\m9\runs\rule_based_v1\known_scenes\m6_wall_03\m6_wall_03.m9_filtered.csv`

## Metrics

| metric | value |
| --- | ---: |
| `total_rows` | 3136 |
| `valid_inputs` | 3136 |
| `kept_points` | 3121 |
| `filtered_points` | 15 |
| `filtered_ratio` | 0.00478316 |
| `status_estimated_count` | 3136 |
| `status_estimated_ratio` | 1 |
| `continuity_issue_count` | 2 |
| `continuity_issue_ratio` | 0.000637755 |
| `stability_issue_count` | 14 |
| `stability_issue_ratio` | 0.00446429 |

## Rule Reasons

| reason | count |
| --- | ---: |
| `distance_jump` | 2 |
| `unstable_angle_bin` | 14 |

## Boundary

- This is rule-level point quality screening, not scene ground truth.
- `status=0x08` is tracked as an estimated flag and is not treated as an alert by itself.
- The stability rule uses repeated distance behavior within angle bins; moving targets or changed scenes still need manual labels.
