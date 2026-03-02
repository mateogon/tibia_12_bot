"""Compare minimap tile extraction across zooms using x4 truth.

Workflow:
1) In bot GUI, run Auto Zoom Capture and switch zoom levels (x1/x2/x4) on same position.
2) This creates: training_data/minimap_zoom_sets/<session>/
3) Run:
   python benchmark_minimap_zoom_tiles.py --session training_data/minimap_zoom_sets/<session>
"""

import argparse
import json
import os

import cv2
import numpy as np

from src.bot.config.constants import BotConstants


def yellow_mask_bgr(img_bgr, tol=12):
    target = np.array([0, 255, 255], dtype=np.int16)
    diff = np.abs(img_bgr.astype(np.int16) - target)
    return np.all(diff <= int(max(0, tol)), axis=-1)


def sample_local_data(map_img, scale, dx=0, dy=0):
    h, w = map_img.shape[:2]
    cx, cy = (w // 2) + int(dx), (h // 2) + int(dy)
    s = int(max(1, scale))
    local = np.zeros((11, 15, 3), dtype=np.uint8)
    for r in range(11):
        for c in range(15):
            px = cx + (c - 7) * s
            py = cy + (r - 5) * s
            if 0 <= px < w and 0 <= py < h:
                local[r, c] = map_img[py, px]
            else:
                local[r, c] = [0, 0, 0]
    return local


def choose_runtime_anchor_now(map_img, scale):
    s = int(max(1, scale))
    offsets = [(0, 0)]
    if s <= 2:
        r = 2
        offsets = [(dx, dy) for dy in range(-r, r + 1) for dx in range(-r, r + 1)]

    terrain = np.array(BotConstants.OBSTACLES + BotConstants.WALKABLE, dtype=np.uint8)
    terrain_codes = (
        (terrain[:, 0].astype(np.uint32) << 16)
        | (terrain[:, 1].astype(np.uint32) << 8)
        | terrain[:, 2].astype(np.uint32)
    )

    best = (0, 0)
    best_score = None
    for dx, dy in offsets:
        local = sample_local_data(map_img, s, dx=dx, dy=dy)
        codes = (
            (local[:, :, 0].astype(np.uint32) << 16)
            | (local[:, :, 1].astype(np.uint32) << 8)
            | local[:, :, 2].astype(np.uint32)
        )
        terrain_hits = int(np.count_nonzero(np.isin(codes, terrain_codes, assume_unique=False)))
        yellow_hits = int(np.count_nonzero(yellow_mask_bgr(local, tol=12)))
        center_bias = -int(abs(dx) + abs(dy))
        score = (terrain_hits + yellow_hits, center_bias)
        if best_score is None or score > best_score:
            best_score = score
            best = (int(dx), int(dy))
    return best


def extract_tiles(local_data):
    obs = np.array(BotConstants.OBSTACLES, dtype=np.uint8)
    low_conf = np.array(getattr(BotConstants, "LOW_CONF_OBSTACLES", []), dtype=np.uint8)
    is_obstacle = np.zeros((11, 15), dtype=bool)
    is_low_conf = np.zeros((11, 15), dtype=bool)
    is_yellow = yellow_mask_bgr(local_data, tol=12)

    for r in range(11):
        for c in range(15):
            color = local_data[r, c]
            if np.any(np.all(color == obs, axis=-1)):
                is_obstacle[r, c] = True
            if low_conf.size > 0 and np.any(np.all(color == low_conf, axis=-1)):
                is_low_conf[r, c] = True
            if is_yellow[r, c]:
                is_obstacle[r, c] = False
                is_low_conf[r, c] = False

    visited = np.zeros((11, 15), dtype=bool)
    dirs = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    for r in range(11):
        for c in range(15):
            if not is_low_conf[r, c] or visited[r, c]:
                continue
            stack = [(r, c)]
            comp = []
            visited[r, c] = True
            while stack:
                cr, cc = stack.pop()
                comp.append((cr, cc))
                for dr, dc in dirs:
                    nr, nc = cr + dr, cc + dc
                    if 0 <= nr < 11 and 0 <= nc < 15 and not visited[nr, nc] and is_low_conf[nr, nc]:
                        visited[nr, nc] = True
                        stack.append((nr, nc))
            if len(comp) <= 3:
                for cr, cc in comp:
                    is_obstacle[cr, cc] = True

    unwalkable = {(int(r), int(c)) for r, c in zip(*np.where(is_obstacle))}
    tp = {(int(r), int(c)) for r, c in zip(*np.where(is_yellow))}
    return unwalkable, tp


def f1_score(pred, truth):
    if not pred and not truth:
        return 1.0
    if not pred or not truth:
        return 0.0
    inter = len(pred & truth)
    p = inter / max(1, len(pred))
    r = inter / max(1, len(truth))
    if (p + r) == 0:
        return 0.0
    return 2.0 * p * r / (p + r)


def eval_offset(map_img, scale, dx, dy, truth_unw, truth_tp):
    local = sample_local_data(map_img, scale, dx=dx, dy=dy)
    pred_unw, pred_tp = extract_tiles(local)
    f1_unw = f1_score(pred_unw, truth_unw)
    f1_tp = f1_score(pred_tp, truth_tp)
    if len(truth_tp) == 0:
        combined = f1_unw
    else:
        combined = (0.7 * f1_unw) + (0.3 * f1_tp)
    return {
        "dx": int(dx),
        "dy": int(dy),
        "f1_unwalkable": float(f1_unw),
        "f1_tp": float(f1_tp),
        "score": float(combined),
        "pred_unwalkable_count": int(len(pred_unw)),
        "pred_tp_count": int(len(pred_tp)),
        "pred_unwalkable": sorted([[int(r), int(c)] for r, c in pred_unw]),
        "pred_tp": sorted([[int(r), int(c)] for r, c in pred_tp]),
    }


def load_pair_set(items):
    out = set()
    for it in items or []:
        if isinstance(it, (list, tuple)) and len(it) == 2:
            out.add((int(it[0]), int(it[1])))
    return out


def main():
    ap = argparse.ArgumentParser(description="Minimap zoom tile alignment benchmark using x4 truth")
    ap.add_argument("--session", required=True, help="Path to training_data/minimap_zoom_sets/<session>")
    ap.add_argument("--search-tiles", type=int, default=2, help="Offset search radius in tile units")
    ap.add_argument("--save-report", action="store_true", help="Write benchmark_report.json in session dir")
    args = ap.parse_args()

    session = args.session
    meta_path = os.path.join(session, "metadata.json")
    if not os.path.isfile(meta_path):
        raise SystemExit(f"metadata.json not found: {meta_path}")

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    x4_meta = (meta.get("scales", {}) or {}).get("4", {})
    x4_frame = x4_meta.get("frame", "zoom_x4.png")
    x4_path = os.path.join(session, x4_frame)
    if not os.path.isfile(x4_path):
        raise SystemExit(f"x4 frame not found: {x4_path}")

    x4_img = cv2.imread(x4_path, cv2.IMREAD_COLOR)
    if x4_img is None:
        raise SystemExit(f"Could not read image: {x4_path}")

    truth_unw = load_pair_set((meta.get("x4_truth", {}) or {}).get("unwalkable"))
    truth_tp = load_pair_set((meta.get("x4_truth", {}) or {}).get("tp"))
    if not truth_unw and not truth_tp:
        local_x4 = sample_local_data(x4_img, 4, dx=0, dy=0)
        truth_unw, truth_tp = extract_tiles(local_x4)

    report = {
        "session": session,
        "truth_counts": {"unwalkable": len(truth_unw), "tp": len(truth_tp)},
        "scales": {},
    }

    print(f"[TRUTH] x4 tiles -> unwalkable={len(truth_unw)} tp={len(truth_tp)}")

    for scale in (1, 2):
        sc_meta = (meta.get("scales", {}) or {}).get(str(scale), {})
        frame = sc_meta.get("frame", f"zoom_x{scale}.png")
        path = os.path.join(session, frame)
        if not os.path.isfile(path):
            print(f"[x{scale}] missing frame: {path}")
            continue
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            print(f"[x{scale}] unreadable image: {path}")
            continue

        s = int(scale)
        r = int(max(0, args.search_tiles)) * s
        best = None
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                cur = eval_offset(img, s, dx, dy, truth_unw, truth_tp)
                if best is None or cur["score"] > best["score"]:
                    best = cur

        runtime_dx = int(sc_meta.get("anchor_dx", 0))
        runtime_dy = int(sc_meta.get("anchor_dy", 0))
        runtime_eval = eval_offset(img, s, runtime_dx, runtime_dy, truth_unw, truth_tp)
        runtime_now_dx, runtime_now_dy = choose_runtime_anchor_now(img, s)
        runtime_now_eval = eval_offset(img, s, runtime_now_dx, runtime_now_dy, truth_unw, truth_tp)
        report["scales"][str(scale)] = {
            "frame": frame,
            "runtime_anchor": {"dx": runtime_dx, "dy": runtime_dy},
            "runtime_eval": runtime_eval,
            "runtime_now_anchor": {"dx": runtime_now_dx, "dy": runtime_now_dy},
            "runtime_now_eval": runtime_now_eval,
            "best_eval": best,
        }

        print(
            f"[x{scale}] runtime(dx={runtime_dx},dy={runtime_dy}) "
            f"score={runtime_eval['score']:.3f} "
            f"| runtime_now(dx={runtime_now_dx},dy={runtime_now_dy}) "
            f"score={runtime_now_eval['score']:.3f} "
            f"| best(dx={best['dx']},dy={best['dy']}) score={best['score']:.3f} "
            f"f1_unw={best['f1_unwalkable']:.3f} f1_tp={best['f1_tp']:.3f}"
        )

    if args.save_report:
        out = os.path.join(session, "benchmark_report.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=True, indent=2)
        print(f"[REPORT] {out}")


if __name__ == "__main__":
    main()
