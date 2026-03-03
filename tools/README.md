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

- `tools/simulate_cavebot_marks.py`
  - Replays cavebot sessions and evaluates mark-follow behavior and accuracy.

- `tools/generate_synth_cavebot_session.py`
  - Generates synthetic cavebot sessions (experimental/not primary source of truth).

- `tools/evaluate_monster_detector.py`
  - Evaluates monster detector vs `training_data/*.json` labels, including optional offset sweep.

- `tools/detect_monsters.py`
  - CLI wrapper for the runtime monster detector (`src.bot.vision.detect_monsters`).

- `tools/annotation_tool.py`
  - Manual annotation editor for `training_data/*.json` coordinates.

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

python tools/simulate_cavebot_marks.py --session training_data/cavebot_sessions/20260302_024100

python tools/evaluate_monster_detector.py --data training_data --label-space name --match-distance 25 --sweep-offset --radius 12

python tools/detect_monsters.py --compare --runs 5 --warmup 2

python tools/annotation_tool.py
```
