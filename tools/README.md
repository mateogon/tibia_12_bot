# Offline Tools

Run all commands from the repository root (`tibia_12_bot`).

## Data Location
Keep datasets in `training_data/` at repo root.
- This avoids path breakage in runtime code and existing scripts.
- `tools/` stores scripts only.

## Scripts

- `tools/benchmark_minimap.py`
  - Benchmarks minimap zoom detection methods (`legacy`, `codes`, `terrain_vec`, `color_edges`) on cavebot sessions.

- `tools/benchmark_minimap_motion.py`
  - Benchmarks minimap motion estimators against brute-force reference and reports latency + accuracy metrics.

- `tools/benchmark_minimap_zoom_tiles.py`
  - Compares x1/x2 tile extraction against x4 truth in zoom-set sessions; reports runtime alignment vs best offset.

- `tools/sweep_minimap_anchor_methods.py`
  - Sweeps anchor/phase methods for minimap tile sampling and summarizes score/F1/`dy` error.

- `tools/check_zoom_detect_on_sessions.py`
  - Quick sanity check for zoom detector outputs across prepared zoom sessions.

- `tools/evaluate_minimap_zoom_samples.py`
  - Sweeps many zoom-detector variants on manually labeled `training_data/minimap_zoom_samples/*.json`.
  - Reports top methods overall, by zoom (x1/x2/x4), and high-black minimap performance.
  - Can optionally include labeled images from `training_data/minimap_zoom_sets/*/metadata.json`.

- `tools/simulate_cavebot_marks.py`
  - Replays cavebot sessions and evaluates mark-follow behavior and accuracy.

- `tools/generate_synth_cavebot_session.py`
  - Generates synthetic cavebot sessions (experimental/not primary source of truth).

- `tools/evaluate_monster_detector.py`
  - Evaluates monster detector vs `training_data/*.json` labels, including optional offset sweep.

- `tools/detect_monsters.py`
  - CLI wrapper for the runtime monster detector (`src.vision.detect_monsters`).

- `tools/annotation_tool.py`
  - Manual annotation editor for `training_data/*.json` coordinates.

- `tools/unwalkable_annotation_tool.py`
  - Manual tile-grid editor for `training_data/unwalkable_samples/*.json` using saved minimap/game snapshots and auto-detected unwalkable tiles as a starting point.

- `tools/evaluate_unwalkable_samples.py`
  - Evaluates `auto.unwalkable` and `auto.collision_unwalkable` against `labels.unwalkable` on `training_data/unwalkable_samples/*.json`.
  - Reports precision/recall/F1 by zoom and tile hot-spots (FN/FP).

- `tools/report_unwalkable_sample.py`
  - Detailed diff report for one sample (lists FN/FP tile coordinates for auto and collision predictions).

- `tools/fix_coordinates.py`
  - Batch coordinate correction utility for labeled training files.

- `tools/test_detection.py`
  - Legacy offline detector evaluation with debug image output (`debug_output/`).

- `tools/analyze_colors.py`
  - Color distribution helper for understanding dataset pixel classes around labels.

- `tools/test_scale.py`
  - Interactive minimap scale diagnostic script (manual capture flow).

- `tools/test_menu_follow_template.py`
  - Interactive template-match diagnostic for menu follow action.

## Example Commands

```bash
python tools/benchmark_minimap.py --sessions training_data/cavebot_sessions/20260302_022053 training_data/cavebot_sessions/20260302_022442 training_data/cavebot_sessions/20260302_022701 --runs 10 --warmup 3

python tools/benchmark_minimap_motion.py --session training_data/cavebot_sessions/20260302_024100 --runs 10 --warmup 3 --max-shift 8

python tools/benchmark_minimap_zoom_tiles.py --session training_data/minimap_zoom_sets/20260302_171107 --save-report

python tools/sweep_minimap_anchor_methods.py --sessions training_data/minimap_zoom_sets/20260302_171107 training_data/minimap_zoom_sets/20260302_171127 training_data/minimap_zoom_sets/20260302_171212 --radius 2

python tools/check_zoom_detect_on_sessions.py

python tools/evaluate_minimap_zoom_samples.py --samples-dir training_data/minimap_zoom_samples --sync-gold-only --details --top 15
python tools/evaluate_minimap_zoom_samples.py --samples-dir training_data/minimap_zoom_samples --sync-gold-only --optimize x2_focus --x2-weight 3.0 --top 25 --details
python tools/evaluate_minimap_zoom_samples.py --samples-dir training_data/minimap_zoom_samples --sync-gold-only --eval-runtime-current --exhaustive --optimize balanced --min-z1-acc 0.70 --min-z2-acc 0.50 --min-z4-acc 0.70 --top 40 --details

python tools/simulate_cavebot_marks.py --session training_data/cavebot_sessions/20260302_024100

python tools/evaluate_monster_detector.py --data training_data --label-space name --match-distance 25 --sweep-offset --radius 12

python tools/detect_monsters.py --compare --runs 5 --warmup 2

python tools/annotation_tool.py

python tools/unwalkable_annotation_tool.py

python tools/evaluate_unwalkable_samples.py --data training_data/unwalkable_samples --details

python tools/report_unwalkable_sample.py --sample training_data/unwalkable_samples/<sample>.json
```
