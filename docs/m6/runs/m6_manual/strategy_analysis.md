# M6 Strategy Analysis

## Observed Phenomena

- The newer box repeats are cleaner than the first close-box set, but the target is still close enough that edge/near-field effects matter.
- Box repeatability is 20.00 mm p95, so the main shape is repeatable at roughly 2 cm scale.
- Box seam closure is 11.82 mm, so 0/360 closure is not the dominant problem.
- Box four-edge RMSE is 16.76 mm; individual edges show different residuals, so geometry quality is not uniform around the scan.
- The wall segment is clearly selected at 350->40 deg and has combined RMSE 7.44 mm.

## Evaluation

- The system is stable enough for M6 offline analysis: all six CSV files are usable and contain XY fields.
- Single-wall geometry is notably better than box geometry, which suggests the core angle-distance pairing is not grossly broken.
- The box case remains harder because it mixes multiple faces, corners, near-range returns, and occlusion-like gaps.

## Shortcomings

- The target distance is still relatively close, so the TF-Luna near-field limit can still affect box edge shape.
- Box edges are not uniformly straight; this points to mounting eccentricity, target placement, edge/corner returns, or filtering, before firmware sync changes.
- Gap counts are still present, so display/analysis should avoid connecting large point jumps as continuous geometry.
- Current wall selection is fixed to the measured window; if the wall moves, the selection window should be re-detected or passed explicitly.

## Recommended Change Plan

1. Keep MCU firmware unchanged for now.
2. Keep raw CSV unchanged; apply filtering only in analysis/display paths.
3. Use separate analysis modes: box repeats for whole-shape/four-edge metrics, wall repeats for single-line straightness.
4. Add or keep a configurable wall angle window, currently `350 -> 40` deg for this dataset.
5. In the UI/display layer, avoid connecting adjacent points when XY jump exceeds the gap threshold.
6. If future 60-80 cm wall tests still show high wall RMSE, then investigate angle offset or mounting eccentricity before changing sync logic.
