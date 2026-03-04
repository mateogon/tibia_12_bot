# Task Log - Minimap Zoom + Unwalkable Data Workstream

Last updated: 2026-03-03
Owner context: Ongoing iterative debugging with in-game validation + offline evaluation.

## Objective
Improve minimap reliability in two related areas:
1. Unwalkable/TP tile extraction alignment across zoom levels (x1/x2/x4), especially yellow tile spill.
2. Automatic minimap zoom detection robustness, especially x1/x2 in black-heavy maps (undiscovered areas/small rooms/high floors).

## Current Status
- Unwalkable sample capture + annotation + evaluation pipeline exists and is working.
- Auto zoom capture now can also auto-save unwalkable samples per zoom with grouping metadata.
- Manual minimap zoom sample capture exists with manual zoom label and diagnostics.
- New runtime zoom-detector patch was added (center-focused run-width estimator + black-aware merge with existing detector).
- New offline evaluator for zoom samples exists and supports large sweeps.

## Key Findings So Far
### Unwalkable / TP
- Major issue was inconsistent yellow/TP tile behavior across x1/x2 (extra tile spill, usually south/diagonal).
- x4 is generally more stable than x1/x2.
- Annotation alignment had tool-side offsets; currently workable after adjustments.

### Zoom detection
- Baseline (from saved runtime metadata in sample JSON): poor on sync-gold sample set.
  - Example observed: runtime metadata baseline around 0.381 acc on n=21 sync-gold.
- Best offline detector family so far:
  - `majority_combined_m2_r10_w0.8-1.0-1.2`
  - Strong overall on mixed dataset, but x2 confusion still present.
- Main failure mode: true x2 often collapsing to x1 in difficult scenes.

## Data Sources
### Unwalkable dataset
- `training_data/unwalkable_samples/*.json`
- Contains game/minimap snapshots + auto predictions + editable labels.
- Important fields: `zoom_level`, `auto.unwalkable`, `auto.tp`, `labels.unwalkable`, `labels.tp`, `sync_gold`, `quality_tag`, `sync_group`.

### Zoom dataset
- `training_data/minimap_zoom_samples/*.json` + `*_minimap.png`
- Manual zoom labels + detector diagnostics.
- Important fields: `manual_zoom_level`, `detected_zoom_level`, `black_ratio`, `terrain_ratio`, `sync_gold`.

### Zoom set sessions
- `training_data/minimap_zoom_sets/<session>/metadata.json`
- Captured x1/x2/x4 set-style samples.

## Code Changes Already In Place
### Runtime / GUI
- `src/core/bot_runtime.py`
  - `capture_unwalkable_sample()` and shared save helper `_save_unwalkable_sample_from_frames(...)`.
  - Auto zoom capture can save unwalkable samples with `sync_group` linkage.
  - `capture_minimap_zoom_sample(manual_zoom)` for labeled zoom dataset capture.
  - `detect_minimap_scale(...)` has new center run-width estimator + black-aware blending with legacy/vectorized paths.
- `src/ui/main_GUI.py`
  - Toggle: `Auto-save Unwalkable Samples During Zoom Capture`.
  - Developer tool: `Save Minimap Zoom Sample` with manual zoom label selector.

### Offline tools
- `tools/evaluate_unwalkable_samples.py`
  - Baseline metrics + experiment sweeps + TP cross-zoom consistency analysis.
- `tools/evaluate_minimap_zoom_samples.py`
  - Zoom detector sweeps over many variants.
  - Bucketing by black ratio.
  - Confusion matrix output.
  - Runtime metadata baseline + `--eval-runtime-current` image-based emulation of current runtime detector.
  - `--exhaustive` larger grid.
  - Constraint filtering per zoom (`--min-z1-acc`, `--min-z2-acc`, `--min-z4-acc`).

## Recommended Workflow (Current)
1. Gather more failing zoom samples in black-heavy scenes using `Save Minimap Zoom Sample`.
2. Run exhaustive evaluation with constraints (avoid degenerate x2-focused winners):

```bash
python tools/evaluate_minimap_zoom_samples.py \
  --samples-dir training_data/minimap_zoom_samples \
  --sync-gold-only \
  --eval-runtime-current \
  --exhaustive \
  --optimize balanced \
  --min-z1-acc 0.70 \
  --min-z2-acc 0.50 \
  --min-z4-acc 0.70 \
  --top 40 \
  --details
```

3. Also run with zoom-sets included for broader coverage:

```bash
python tools/evaluate_minimap_zoom_samples.py \
  --samples-dir training_data/minimap_zoom_samples \
  --include-zoom-sets \
  --sets-dir training_data/minimap_zoom_sets \
  --eval-runtime-current \
  --exhaustive \
  --optimize balanced \
  --min-z1-acc 0.75 \
  --min-z2-acc 0.60 \
  --min-z4-acc 0.75 \
  --top 40
```

4. Choose the best constrained method and port it into runtime detector logic.
5. Re-capture a fresh validation set after runtime patch to verify real gain (not just offline).

## Open Problems
- x2 vs x1 separation remains the hardest class boundary in black-heavy maps.
- Need to verify that runtime patch improves `--eval-runtime-current` baseline on newly captured samples.
- Potentially split detector policy by black-ratio regime (normal vs black-heavy) with stricter x1 gating.

## Practical Notes
- "Sync gold" means trusted manual label quality, not guaranteed detector correctness.
- Metadata field `detected_zoom_level` reflects detector output at capture time; may be stale vs latest runtime code.
- Prefer image-based runtime emulation (`--eval-runtime-current`) for current-state baseline.

## Next Immediate Step
Run the two recommended exhaustive commands above and choose one candidate method that satisfies per-zoom constraints. Then apply that specific policy into `detect_minimap_scale(...)` and verify in-game.
