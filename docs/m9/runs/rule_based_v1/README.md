# M9 Rule Quality Gate Appendix

M9 is an offline rule-based point quality filter built on the M8 dataset contract.
It does not train a model, does not use AI, and does not change the live CAN/MCU path.
The results are separated so unknown replay captures are not used as scene-level evidence.

## Rule Set

- Distance jump: flags unreasonable short-neighbor distance changes.
- Neighborhood continuity: flags points without close neighbors or with only far-distance neighbors.
- Quality/status: flags low quality and non-zero alert levels from `status & 0x07`.
- Multi-scan stability: flags points that deviate from the repeated distance behavior of the same angle bin.

## Unknown Replay Results

| dataset | total | kept | filtered | filtered ratio | continuity issue ratio | stability issue ratio | report | plot |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `can_distance_20260507_141150` | 5220 | 5214 | 6 | 0.00114943 | 0 | 0.00114943 | [report](replay_sets/can_distance_20260507_141150/can_distance_20260507_141150.m9_report.md) | [plot](replay_sets/can_distance_20260507_141150/can_distance_20260507_141150.m9_compare.png) |
| `can_distance_20260509_214813` | 15671 | 15505 | 166 | 0.0105928 | 0.00280773 | 0.00899751 | [report](replay_sets/can_distance_20260509_214813/can_distance_20260509_214813.m9_report.md) | [plot](replay_sets/can_distance_20260509_214813/can_distance_20260509_214813.m9_compare.png) |
| `can_distance_20260509_222646` | 20881 | 20597 | 284 | 0.0136009 | 0.000862028 | 0.0129783 | [report](replay_sets/can_distance_20260509_222646/can_distance_20260509_222646.m9_report.md) | [plot](replay_sets/can_distance_20260509_222646/can_distance_20260509_222646.m9_compare.png) |
| `can_distance_20260509_223115` | 8691 | 8581 | 110 | 0.0126568 | 0.00115062 | 0.0116212 | [report](replay_sets/can_distance_20260509_223115/can_distance_20260509_223115.m9_report.md) | [plot](replay_sets/can_distance_20260509_223115/can_distance_20260509_223115.m9_compare.png) |
| `can_distance_20260510_000136` | 33304 | 32730 | 574 | 0.0172352 | 0.00279246 | 0.014743 | [report](replay_sets/can_distance_20260510_000136/can_distance_20260510_000136.m9_report.md) | [plot](replay_sets/can_distance_20260510_000136/can_distance_20260510_000136.m9_compare.png) |

## Known Scene Results

| dataset | total | kept | filtered | filtered ratio | continuity issue ratio | stability issue ratio | report | plot |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `m6_box_far_01` | 3268 | 3268 | 0 | 0 | 0 | 0 | [report](known_scenes/m6_box_far_01/m6_box_far_01.m9_report.md) | [plot](known_scenes/m6_box_far_01/m6_box_far_01.m9_compare.png) |
| `m6_box_far_02` | 3325 | 3325 | 0 | 0 | 0 | 0 | [report](known_scenes/m6_box_far_02/m6_box_far_02.m9_report.md) | [plot](known_scenes/m6_box_far_02/m6_box_far_02.m9_compare.png) |
| `m6_box_far_03` | 3269 | 3269 | 0 | 0 | 0 | 0 | [report](known_scenes/m6_box_far_03/m6_box_far_03.m9_report.md) | [plot](known_scenes/m6_box_far_03/m6_box_far_03.m9_compare.png) |
| `m6_wall_01` | 2284 | 2265 | 19 | 0.00831874 | 0.000875657 | 0.00788091 | [report](known_scenes/m6_wall_01/m6_wall_01.m9_report.md) | [plot](known_scenes/m6_wall_01/m6_wall_01.m9_compare.png) |
| `m6_wall_02` | 2855 | 2820 | 35 | 0.0122592 | 0.00420315 | 0.00945709 | [report](known_scenes/m6_wall_02/m6_wall_02.m9_report.md) | [plot](known_scenes/m6_wall_02/m6_wall_02.m9_compare.png) |
| `m6_wall_03` | 3136 | 3121 | 15 | 0.00478316 | 0.000637755 | 0.00446429 | [report](known_scenes/m6_wall_03/m6_wall_03.m9_report.md) | [plot](known_scenes/m6_wall_03/m6_wall_03.m9_compare.png) |

## V1 Conclusion

- Unknown replay rows processed: `83767`; filtered candidates: `1140` (`0.0136092`).
- Known-scene rows processed: `18137`; filtered candidates: `69` (`0.00380438`).
- Unknown replay data is suitable for tool regression and before/after output checks, not for wall/box scene claims.
- Known-scene data from M6 is suitable for wall/static-box before/after comparison.
- Real scene labels are still required before claiming precision/recall or model-grade anomaly detection.

## Reproduce

```powershell
py -3 .\tools\m9_rule_filter.py --all
py -3 .\tools\selfcheck_m9_rule_filter.py
```
