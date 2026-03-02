"""Generate synthetic cavebot sessions compatible with simulate_cavebot_marks.py.

Usage:
  python generate_synth_cavebot_session.py ^
    --source-session training_data/cavebot_sessions/20260302_003506 ^
    --out-session synth_figure8_v1 --scenario figure8 --laps 4
"""

import argparse
import json
import random
import time
from pathlib import Path

import cv2
import numpy as np


MARKS = ["skull", "lock", "cross", "star"]
THRESHOLDS = {"skull": 0.88, "lock": 0.80, "cross": 0.89, "star": 0.89}


def load_trace(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def detect_mark_positions(frame_bgr, template_bgr, threshold):
    if template_bgr is None:
        return []
    if template_bgr.ndim == 3 and template_bgr.shape[2] == 4:
        template_bgr = template_bgr[:, :, :3]
    if frame_bgr.ndim == 3 and frame_bgr.shape[2] == 4:
        frame_bgr = frame_bgr[:, :, :3]
    res = cv2.matchTemplate(frame_bgr, template_bgr, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(res >= threshold)
    out = []
    h, w = template_bgr.shape[:2]
    for x, y in sorted(zip(xs, ys), key=lambda p: res[p[1], p[0]], reverse=True):
        cx = x + w // 2
        cy = y + h // 2
        keep = True
        for px, py, _ in out:
            if abs(cx - px) < max(6, w // 2) and abs(cy - py) < max(6, h // 2):
                keep = False
                break
        if keep:
            out.append((cx, cy, float(res[y, x])))
    return out


def mark_nonbg_mask(tp):
    if tp.shape[2] == 4:
        return tp[:, :, 3] > 0
    # Avoid black-box overlays for non-alpha templates.
    return np.any(tp > 20, axis=2)


def overlay_mark(dst, tp, center):
    h, w = tp.shape[:2]
    cx, cy = int(center[0]), int(center[1])
    x0 = cx - w // 2
    y0 = cy - h // 2
    x1 = x0 + w
    y1 = y0 + h
    if x1 <= 0 or y1 <= 0 or x0 >= dst.shape[1] or y0 >= dst.shape[0]:
        return
    sx0 = max(0, x0)
    sy0 = max(0, y0)
    sx1 = min(dst.shape[1], x1)
    sy1 = min(dst.shape[0], y1)
    tx0 = sx0 - x0
    ty0 = sy0 - y0
    tx1 = tx0 + (sx1 - sx0)
    ty1 = ty0 + (sy1 - sy0)
    roi = dst[sy0:sy1, sx0:sx1]
    src = tp[ty0:ty1, tx0:tx1, :3]
    m = mark_nonbg_mask(tp[ty0:ty1, tx0:tx1]).astype(np.uint8) * 255
    cv2.copyTo(src, m, roi)


def extract_palette(source_session: Path, templates, palette_k=8, pad=3, max_frames=60, sample_per_frame=800):
    trace = load_trace(source_session / "trace.jsonl")
    frames_dir = source_session / "frames"
    if not trace:
        raise RuntimeError("Empty source trace.jsonl")

    picked = trace[:max_frames] if len(trace) <= max_frames else random.sample(trace, max_frames)
    pix = []
    for row in picked:
        fp = frames_dir / row["frame"]
        frame = cv2.imread(str(fp))
        if frame is None:
            continue
        h, w = frame.shape[:2]
        keep = np.ones((h, w), dtype=np.uint8) * 255

        # Remove mark pixels + padded ring so terrain palette is clean.
        for m in MARKS:
            tp = templates[m]
            th = THRESHOLDS[m]
            pts = detect_mark_positions(frame, tp, th)
            mh, mw = tp.shape[:2]
            for cx, cy, _ in pts:
                x0 = max(0, int(cx - mw // 2 - pad))
                y0 = max(0, int(cy - mh // 2 - pad))
                x1 = min(w, int(cx + mw // 2 + pad))
                y1 = min(h, int(cy + mh // 2 + pad))
                keep[y0:y1, x0:x1] = 0

        ys, xs = np.where(keep > 0)
        if len(xs) == 0:
            continue
        if len(xs) > sample_per_frame:
            idx = np.random.choice(len(xs), size=sample_per_frame, replace=False)
            ys = ys[idx]
            xs = xs[idx]
        pix.append(frame[ys, xs])

    if not pix:
        return np.array([[40, 90, 40], [60, 120, 70], [50, 60, 90], [80, 80, 80]], dtype=np.uint8)

    data = np.concatenate(pix, axis=0).astype(np.float32)
    K = max(3, min(int(palette_k), len(data)))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _compactness, _labels, centers = cv2.kmeans(
        data, K, None, criteria, 3, cv2.KMEANS_PP_CENTERS
    )
    return np.clip(centers, 0, 255).astype(np.uint8)


def synth_background(h, w, palette, seed):
    rng = np.random.default_rng(seed)
    gh = max(8, h // 8)
    gw = max(8, w // 8)
    ids = rng.integers(0, len(palette), size=(gh, gw), dtype=np.int32)
    coarse = palette[ids]  # gh x gw x 3
    bg = cv2.resize(coarse.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
    return bg


def scenario_mark_world_positions(scenario, world_center):
    cx, cy = int(world_center[0]), int(world_center[1])
    if scenario == "stairs_pingpong":
        return {
            "skull": (cx - 62, cy - 42),
            "lock": (cx + 58, cy - 44),
            "cross": (cx - 58, cy + 44),
            "star": (cx + 62, cy + 42),
        }
    # figure8-ish geometry
    return {
        "skull": (cx - 64, cy - 56),
        "lock": (cx + 64, cy - 56),
        "cross": (cx - 64, cy + 56),
        "star": (cx + 64, cy + 56),
    }


def crop_world(world_bgr, center_xy, out_w, out_h):
    h, w = world_bgr.shape[:2]
    cx, cy = int(center_xy[0]), int(center_xy[1])
    x0 = cx - out_w // 2
    y0 = cy - out_h // 2
    x1 = x0 + out_w
    y1 = y0 + out_h
    # Simple clamped crop (good enough for synthetic sessions).
    if x0 < 0:
        x1 -= x0
        x0 = 0
    if y0 < 0:
        y1 -= y0
        y0 = 0
    if x1 > w:
        shift = x1 - w
        x0 = max(0, x0 - shift)
        x1 = w
    if y1 > h:
        shift = y1 - h
        y0 = max(0, y0 - shift)
        y1 = h
    crop = world_bgr[y0:y1, x0:x1]
    if crop.shape[0] != out_h or crop.shape[1] != out_w:
        crop = cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_NEAREST)
    return crop, x0, y0


def write_session(
    out_session: Path,
    templates,
    palette,
    scenario="figure8",
    laps=3,
    frames_per_segment=16,
    arrival_hold_frames=1,
    ts_step_ms=130,
    dropout_rate=0.0,
):
    out_session.mkdir(parents=True, exist_ok=True)
    frames_dir = out_session / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_session / "trace.jsonl"

    # Minimap frame size.
    h, w = 106, 106

    rng = random.Random(1337)
    now_ms = int(time.time() * 1000)
    frame_idx = 0
    rows = []

    cycle = list(MARKS)
    # Build one or two world textures (stairs flips floor texture).
    world_sz = 512
    world_a = synth_background(world_sz, world_sz, palette, seed=111)
    world_b = synth_background(world_sz, world_sz, palette, seed=222)
    world_center = (world_sz // 2, world_sz // 2)
    mark_world = scenario_mark_world_positions(scenario, world_center)

    segs = []
    for lap in range(laps):
        for mark in cycle:
            segs.append((lap, mark))

    # Player starts offset from first mark target.
    first_goal = segs[0][1]
    final_goal_rel = (1, 1)  # intended "reached" near-center offset
    player_x = mark_world[first_goal][0] - final_goal_rel[0]
    player_y = mark_world[first_goal][1] - 36

    for seg_i, (lap, goal_mark) in enumerate(segs):
        # Goal is where player must be so that target mark appears near center.
        goal_player_x = mark_world[goal_mark][0] - final_goal_rel[0]
        goal_player_y = mark_world[goal_mark][1] - final_goal_rel[1]
        start_player_x = player_x
        start_player_y = player_y
        seg_rows = []

        # Keep hold short; long holds create synthetic label lag with
        # immediate-advance cavebot settings.
        hold_n = max(1, int(arrival_hold_frames))
        move_n = max(2, int(frames_per_segment) - hold_n)

        for i in range(frames_per_segment):
            # Player movement in world coordinates.
            if i >= move_n:
                t = 1.0
            else:
                t = i / float(max(1, move_n - 1))
            px = int(round(start_player_x * (1.0 - t) + goal_player_x * t))
            py = int(round(start_player_y * (1.0 - t) + goal_player_y * t))

            # Floor changes for stairs scenario (texture flip by segment).
            world = world_a
            if scenario == "stairs_pingpong" and ((seg_i % 2) == 1):
                world = world_b
            frame, vx0, vy0 = crop_world(world, (px, py), w, h)

            # Draw all marks from world coords -> viewport coords.
            for m in MARKS:
                tp = templates[m]
                if tp is None:
                    continue
                mx, my = mark_world[m]
                rx = mx - vx0
                ry = my - vy0
                # Optional dropout only for current target while still moving.
                if m == goal_mark and i < move_n and rng.random() < dropout_rate:
                    continue
                overlay_mark(frame, tp, (rx, ry))

            frame_idx += 1
            fname = f"frame_{frame_idx:06d}.png"
            cv2.imwrite(str(frames_dir / fname), frame)
            goal_rel = [int(mark_world[goal_mark][0] - vx0), int(mark_world[goal_mark][1] - vy0)]
            nearest_dist = float(((goal_rel[0] - (w // 2)) ** 2 + (goal_rel[1] - (h // 2)) ** 2) ** 0.5)
            row = {
                "ts_ms": now_ms,
                "event": "tick",
                "frame": fname,
                "current_mark": goal_mark,
                "current_mark_index": cycle.index(goal_mark),
                "mark_list": cycle,
                "monster_count": 0,
                "kill_mode": False,
                "scan": {},
                "nearest_dist": nearest_dist,
                "nearest_rel": goal_rel,
                "goal_mark": goal_mark,
                "goal_rel": [w // 2 + final_goal_rel[0], h // 2 + final_goal_rel[1]],
                "segment_size": frames_per_segment,
                "segment_idx": i,
                "segment_end_reason": "mark_change",
                "next_mark_after_segment": cycle[(cycle.index(goal_mark) + 1) % len(cycle)],
            }
            seg_rows.append(row)
            now_ms += ts_step_ms

        if seg_rows:
            seg_rows[-1]["segment_end_reason"] = "mark_change" if seg_i < len(segs) - 1 else "stop"
        rows.extend(seg_rows)
        # Start next segment from this segment end.
        player_x, player_y = goal_player_x, goal_player_y

    with trace_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=True) + "\n")

    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-session", required=True, help="Recorded session used to learn terrain palette")
    ap.add_argument("--out-session", default="", help="Output session name under training_data/cavebot_sessions/")
    ap.add_argument("--scenario", choices=["figure8", "stairs_pingpong"], default="figure8")
    ap.add_argument("--laps", type=int, default=3)
    ap.add_argument("--frames-per-segment", type=int, default=16)
    ap.add_argument(
        "--arrival-hold-frames",
        type=int,
        default=1,
        help="Final frames per segment held at center (1 recommended to avoid label lag)",
    )
    ap.add_argument("--palette-k", type=int, default=8)
    ap.add_argument("--mark-pad", type=int, default=3, help="Pixels around detected mark removed from palette extraction")
    ap.add_argument("--dropout-rate", type=float, default=0.0, help="Chance to hide target mark in moving frames")
    args = ap.parse_args()

    src = Path(args.source_session)
    if not src.exists():
        raise SystemExit(f"Source session not found: {src}")

    marks_dir = Path("img") / "map_marks"
    templates = {m: cv2.imread(str(marks_dir / f"{m}.png"), cv2.IMREAD_UNCHANGED) for m in MARKS}
    missing = [m for m, tp in templates.items() if tp is None]
    if missing:
        raise SystemExit(f"Missing mark templates: {missing}")

    palette = extract_palette(
        src, templates, palette_k=args.palette_k, pad=args.mark_pad
    )

    session_name = args.out_session.strip() or f"synth_{args.scenario}_{int(time.time())}"
    out = Path("training_data") / "cavebot_sessions" / session_name
    n = write_session(
        out,
        templates=templates,
        palette=palette,
        scenario=args.scenario,
        laps=max(1, int(args.laps)),
        frames_per_segment=max(6, int(args.frames_per_segment)),
        arrival_hold_frames=max(1, int(args.arrival_hold_frames)),
        dropout_rate=float(args.dropout_rate),
    )
    print(f"Synthetic session written: {out}")
    print(f"Frames: {n}")
    print(f"Scenario: {args.scenario}")
    print(f"Palette colors: {len(palette)}")


if __name__ == "__main__":
    main()
