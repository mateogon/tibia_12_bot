# Tibia 12 Bot - Handoff Notes for Next Agent

## 1) Project Summary
- This is a Tibia automation bot with real-time screen vision, battle-list driven combat, cavebot mark navigation, and support logic (heals, equipment, runes, buffs).
- Entry point: `main.py` -> `src/bot/core/app.py` -> `BotRunner` loop.
- Current codebase is mid-refactor: core runtime moved under `src/bot/*`, but root still has legacy/deprecated files and scripts.

## 2) Main Runtime Architecture
- `src/bot/core/bot_runtime.py`
  - Main `Bot` class: game state, detection logic, action logic, cavebot logic, recorder/debug lab, visual overlays.
  - Contains combat, battle list scans, minimap scale detection, collision map extraction, cavebot mark handling, and most behavior policies.
- `src/bot/core/runner.py`
  - Main loop orchestration, cadence, perf spans, module ordering.
  - Handles periodic updates, background capture ingestion, actions, and visualization calls.
- `src/bot/vision/bg_capture.py`
  - Background frame capture thread + metrics.
- `src/bot/ui/main_GUI.py`
  - Tabs and controls for runtime toggles/settings/debug.

## 3) Current Debug/Perf Infrastructure
- Section log toggles in GUI/settings: global, action, perf, cavebot, battle list.
- Perf prints include top spans and cycle/fps style stats.
- Added minimap perf split spans in runner:
  - `minimap_capture`
  - `scale_detect`
- Battle list visual debug added:
  - GUI toggle: `visualize_battlelist`
  - OpenCV window: `Battle List Debug`
  - Shows sampled rows, selected row, attacked row marker, scan columns, source reason.

## 4) Battle List / Knight Targeting State
- Knight policy intended: always target first row in battle list.
- Current implementation improvements:
  - Explicit attacked-row detection via red marker scan at battle-list left column.
  - `clickAttack()` no longer early-returns for knights just because "attacking something"; it checks attacked row index.
  - If not on row 0, knight can retarget first row.
- Remaining work: verify offsets/colors on all servers/themes; tune `rel_x/start_y/step_y` if a client skin shifts rows.

## 5) Minimap Scale Detection (Optimized)
- `detect_minimap_scale()` moved to vectorized terrain-edge spacing fast path.
- Legacy loop logic retained as fallback only when vectorized result is ambiguous.
- Offline benchmarking showed `terrain_vec` ~3-4x faster than legacy with same accuracy on tested sessions.

## 6) Minimap Motion Tracking Work
### Runtime recorder metadata
- Cavebot recorder now stores per-frame:
  - `map_scale`, `zoom_label`, `zoom_label_source`
  - `map_delta`
  - `move_dx`, `move_dy`, `moved_px`, `move_confidence`, `move_method`
  - `motion_valid`, `motion_reason`
- Movement estimator currently template-first with light discontinuity guard:
  - Primary: center template match (`template_center`)
  - Discontinuity heuristic via `map_delta`
  - Invalidates weak high-delta frames instead of trusting bad vectors
  - Rare fallback to phase correlation outside discontinuity handling

### Key conclusion from tests
- Two regimes exist:
  1. Normal smooth movement: `template_center` best.
  2. Floor-change/discontinuous minimap: pure template degrades.
- Chosen compromise now: keep pure-template behavior for common case + light guard for obvious jumps.

## 7) Offline Test/Benchmark Scripts (Important)
### Monster detection
- `detect_monsters.py`
  - Supports compare mode, repeated runs, warmup, stage profiling.
  - Used to validate optimized monster detector vs legacy.

### Cavebot mark simulation
- `simulate_cavebot_marks.py`
  - Replays recorded cavebot sessions and reports mark-follow accuracy/deviation.
  - Has mismatch display and parameter tuning options.

### Minimap zoom benchmark
- `benchmark_minimap.py`
  - Single or multi-session benchmarking.
  - Compares zoom detectors (`legacy`, `codes`, `terrain_vec`, `color_edges`).
  - Reads `zoom_label` from `trace.jsonl` for label accuracy.

### Minimap motion benchmark
- `benchmark_minimap_motion.py`
  - Compares motion estimators vs brute-force reference.
  - Reports latency, MAE, drift, direction metrics, valid-rate.
  - Includes hybrid/discontinuity policy sweep mode:
    - `--sweep-hybrid --sweep-runs N --sweep-warmup N`

### Synthetic cavebot sessions
- `generate_synth_cavebot_session.py`
  - Experimental and currently not trusted as representative.
  - Synthetic movement/mark behavior still diverges from real minimap dynamics.

## 8) Cavebot Debug Lab (GUI)
- In Settings tab, there is a Cavebot Debug Lab section:
  - Start/stop recording
  - Save snapshot now
  - Manual goal mark set
  - Record interval
  - Zoom label (`0=auto`, `1/2/4=manual`)
- Output path:
  - `training_data/cavebot_sessions/<session>/`
  - `frames/*.png` + `trace.jsonl`

## 9) Known/Recent Stability Issues
- Intermittent `PyEval_RestoreThread: NULL tstate` has occurred during aggressive window drag/resize + OpenCV windows + background capture + keyboard threads.
- Current practical stance: keep concurrency/performance behavior and avoid overengineering resize handling; users primarily care about runtime responsiveness.

## 10) Refactor Status and Future Work
### Already underway
- Core moved under `src/bot/...`.
- Loop orchestration separated (`runner.py`).
- Still lots of logic in monolithic `bot_runtime.py`.

### Recommended next refactor slices
1. Extract battle list subsystem
- Detection, attacked-row parsing, click policy, debug overlay.
2. Extract minimap subsystem
- Scale detect, motion estimate, collision map, mark scan.
3. Extract cavebot policy/state machine
- Mark progression, visited memory, mode transitions.
4. Keep recorder/benchmark interfaces stable
- So offline tests continue working while internals move.

## 11) Practical Guidance for Next Agent
- Do not trust a single benchmark session; test at least:
  - one smooth walk session
  - one quick-turn/fast-walk session
  - one stairs/floor-change session
- For behavior changes, prefer:
  - implement -> replay benchmark -> in-game validation -> adjust thresholds
- Keep logs toggleable and avoid default spam.
- Prefer visual debug overlays for pixel/row based logic (battle list, minimap).

## 12) Quick Commands (examples)
- Zoom benchmark (3 sessions):
  - `python benchmark_minimap.py --sessions training_data/cavebot_sessions/20260302_022053 training_data/cavebot_sessions/20260302_022442 training_data/cavebot_sessions/20260302_022701 --runs 10 --warmup 3`
- Motion benchmark:
  - `python benchmark_minimap_motion.py --session training_data/cavebot_sessions/20260302_024100 --runs 10 --warmup 3 --max-shift 8`
- Motion hybrid sweep:
  - `python benchmark_minimap_motion.py --session training_data/cavebot_sessions/20260302_024216 --runs 10 --warmup 3 --max-shift 8 --sweep-hybrid --sweep-runs 3 --sweep-warmup 1`

## 13) Important Design Intent
- Most hunts do NOT spend much time on stairs.
- Therefore optimize for common smooth-motion case first, with lightweight safeguards for discontinuities.
- Knight combat intent remains strict: nearest/first battle-list target priority.
