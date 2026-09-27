# M9 Rule Quality Gate Appendix Report - m6_box_far_01

- Input: `docs\m8\datasets\known_scenes\m6_box_far_01\m6_box_far_01.csv`
- Filtered CSV: `docs\m9\runs\rule_based_v1\known_scenes\m6_box_far_01\m6_box_far_01.m9_filtered.csv`

## Metrics

| metric | value |
| --- | ---: |
| `total_rows` | 3268 |
| `valid_inputs` | 3268 |
| `kept_points` | 3268 |
| `filtered_points` | 0 |
| `filtered_ratio` | 0 |
| `status_estimated_count` | 3268 |
| `status_estimated_ratio` | 1 |
| `continuity_issue_count` | 0 |
| `continuity_issue_ratio` | 0 |
| `stability_issue_count` | 0 |
| `stability_issue_ratio` | 0 |

## Rule Reasons

| reason | count |
| --- | ---: |
| n/a | 0 |

## Boundary

- This is rule-level point quality screening, not scene ground truth.
- `status=0x08` is tracked as an estimated flag and is not treated as an alert by itself.
- The stability rule uses repeated distance behavior within angle bins; moving targets or changed scenes still need manual labels.
