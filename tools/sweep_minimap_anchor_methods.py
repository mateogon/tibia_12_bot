"""Sweep many minimap anchor-selection methods against x4 truth.

Usage:
  python sweep_minimap_anchor_methods.py --sessions \
    training_data/minimap_zoom_sets/20260302_171107 \
    training_data/minimap_zoom_sets/20260302_171127 \
    training_data/minimap_zoom_sets/20260302_171212
"""

import argparse
import json
import os
from collections import Counter, defaultdict

import cv2
import numpy as np

from src.bot.config.constants import BotConstants


PALETTE_U8 = np.array(BotConstants.OBSTACLES + BotConstants.WALKABLE, dtype=np.uint8)
PALETTE_F32 = PALETTE_U8.astype(np.float32)
TARGET_TP = np.array([0, 255, 255], dtype=np.int16)


def yellow_mask_bgr(img_bgr, tol=12):
    diff = np.abs(img_bgr.astype(np.int16) - TARGET_TP)
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
    return local


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
    if p + r == 0:
        return 0.0
    return 2.0 * p * r / (p + r)


def eval_offset(map_img, scale, dx, dy, truth_unw, truth_tp):
    local = sample_local_data(map_img, scale, dx=dx, dy=dy)
    pred_unw, pred_tp = extract_tiles(local)
    f1_unw = f1_score(pred_unw, truth_unw)
    f1_tp = f1_score(pred_tp, truth_tp)
    score = f1_unw if not truth_tp else (0.7 * f1_unw + 0.3 * f1_tp)
    return score, f1_unw, f1_tp


def dominant_boundary_residue(map_img, scale, axis):
    s = int(max(1, scale))
    if s <= 1:
        return 0
    h, w = map_img.shape[:2]
    cx, cy = w // 2, h // 2
    x_start, x_end = max(0, cx - 90), min(w, cx + 90)
    y_start, y_end = max(0, cy - 60), min(h, cy + 60)
    terrain_codes = (
        (PALETTE_U8[:, 0].astype(np.uint32) << 16)
        | (PALETTE_U8[:, 1].astype(np.uint32) << 8)
        | PALETTE_U8[:, 2].astype(np.uint32)
    )

    if axis == "x":
        strips = [
            (map_img[np.clip(cy - 40, 0, h - 1), x_start:x_end], x_start),
            (map_img[np.clip(cy + 40, 0, h - 1), x_start:x_end], x_start),
        ]
    else:
        strips = [
            (map_img[y_start:y_end, np.clip(cx + 45, 0, w - 1)].reshape(-1, 3), y_start),
            (map_img[y_start:y_end, np.clip(cx - 45, 0, w - 1)].reshape(-1, 3), y_start),
        ]

    residues = []
    for strip, base_idx in strips:
        if strip.size == 0 or len(strip) < 3:
            continue
        codes = (
            (strip[:, 0].astype(np.uint32) << 16)
            | (strip[:, 1].astype(np.uint32) << 8)
            | strip[:, 2].astype(np.uint32)
        )
        is_terrain = np.isin(codes, terrain_codes, assume_unique=False)
        changed = np.any(strip[1:] != strip[:-1], axis=1)
        valid = is_terrain[1:] & is_terrain[:-1] & changed
        edge_idx = np.flatnonzero(valid) + 1
        for i in edge_idx.tolist():
            residues.append(int((base_idx + i) % s))
    if not residues:
        return 0
    return int(Counter(residues).most_common(1)[0][0])


def candidate_features(map_img, scale, dx, dy, x_res, y_res):
    s = int(max(1, scale))
    local = sample_local_data(map_img, s, dx=dx, dy=dy)
    codes = (
        (local[:, :, 0].astype(np.uint32) << 16)
        | (local[:, :, 1].astype(np.uint32) << 8)
        | local[:, :, 2].astype(np.uint32)
    )
    terrain_codes = (
        (PALETTE_U8[:, 0].astype(np.uint32) << 16)
        | (PALETTE_U8[:, 1].astype(np.uint32) << 8)
        | PALETTE_U8[:, 2].astype(np.uint32)
    )
    terrain_hits = float(np.count_nonzero(np.isin(codes, terrain_codes, assume_unique=False)))
    yellow_hits = float(np.count_nonzero(yellow_mask_bgr(local, tol=12)))
    center_bias = -float(abs(dx) + abs(dy))

    # Distances from center samples to boundaries.
    gray = cv2.cvtColor(map_img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 20, 60)
    dt = cv2.distanceTransform((edges == 0).astype(np.uint8), cv2.DIST_L2, 3)
    h, w = map_img.shape[:2]
    cx, cy = (w // 2) + int(dx), (h // 2) + int(dy)
    vals = []
    for r in range(11):
        for c in range(15):
            px = cx + (c - 7) * s
            py = cy + (r - 5) * s
            if 0 <= px < w and 0 <= py < h:
                vals.append(float(dt[py, px]))
    edge_med = float(np.median(vals)) if vals else 0.0

    # Phase consistency from transition residues.
    if s > 1:
        center_x_res = int(((w // 2 + dx) % s))
        center_y_res = int(((h // 2 + dy) % s))
        target_x_res = int((x_res + (s // 2)) % s)
        target_y_res = int((y_res + (s // 2)) % s)
        phase_x = -float(min((center_x_res - target_x_res) % s, (target_x_res - center_x_res) % s))
        phase_y = -float(min((center_y_res - target_y_res) % s, (target_y_res - center_y_res) % s))
    else:
        phase_x = 0.0
        phase_y = 0.0

    return {
        "terrain": terrain_hits,
        "yellow": yellow_hits,
        "center_bias": center_bias,
        "edge_med": edge_med,
        "phase_x": phase_x,
        "phase_y": phase_y,
    }


def normalize_feature_rows(rows, keys):
    arr = {k: np.array([r[k] for r in rows], dtype=np.float64) for k in keys}
    norm = {}
    for k, v in arr.items():
        lo, hi = float(np.min(v)), float(np.max(v))
        if hi - lo < 1e-9:
            norm[k] = np.zeros_like(v)
        else:
            norm[k] = (v - lo) / (hi - lo)
    out = []
    for i in range(len(rows)):
        r = dict(rows[i])
        for k in keys:
            r[f"n_{k}"] = float(norm[k][i])
        out.append(r)
    return out


def load_truth(meta):
    pairs_unw = (meta.get("x4_truth", {}) or {}).get("unwalkable") or []
    pairs_tp = (meta.get("x4_truth", {}) or {}).get("tp") or []
    truth_unw = {(int(p[0]), int(p[1])) for p in pairs_unw if len(p) == 2}
    truth_tp = {(int(p[0]), int(p[1])) for p in pairs_tp if len(p) == 2}
    return truth_unw, truth_tp


def main():
    ap = argparse.ArgumentParser(description="Sweep minimap anchor methods")
    ap.add_argument("--sessions", nargs="+", required=True)
    ap.add_argument("--radius", type=int, default=2, help="candidate offset radius in pixels")
    args = ap.parse_args()

    method_weights = {
        "terrain_only": {"n_terrain": 1.0, "n_center_bias": 0.2},
        "terrain_yellow": {"n_terrain": 1.0, "n_yellow": 0.5, "n_center_bias": 0.2},
        "edge_only": {"n_edge_med": 1.0, "n_center_bias": 0.2},
        "phase_only": {"n_phase_x": 0.9, "n_phase_y": 1.2, "n_center_bias": 0.1},
        "hybrid_a": {"n_terrain": 0.9, "n_yellow": 0.4, "n_phase_x": 0.8, "n_phase_y": 1.2, "n_center_bias": 0.2},
        "hybrid_b": {"n_terrain": 0.7, "n_edge_med": 0.9, "n_phase_x": 0.8, "n_phase_y": 1.3, "n_center_bias": 0.2},
        "hybrid_c": {"n_terrain": 0.8, "n_yellow": 0.3, "n_edge_med": 0.6, "n_phase_x": 1.0, "n_phase_y": 1.4, "n_center_bias": 0.2},
    }

    summary = defaultdict(lambda: {"score_sum": 0.0, "f1u_sum": 0.0, "f1t_sum": 0.0, "dy_err_sum": 0.0, "n": 0})

    for session in args.sessions:
        meta_path = os.path.join(session, "metadata.json")
        if not os.path.isfile(meta_path):
            print(f"[SKIP] no metadata: {session}")
            continue
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        truth_unw, truth_tp = load_truth(meta)
        if not truth_unw and not truth_tp:
            print(f"[SKIP] no truth tiles in {session}")
            continue

        print(f"\nSESSION {session}")
        for scale in (1, 2):
            frame = ((meta.get("scales", {}) or {}).get(str(scale), {}) or {}).get("frame", f"zoom_x{scale}.png")
            path = os.path.join(session, frame)
            img = cv2.imread(path, cv2.IMREAD_COLOR)
            if img is None:
                print(f"  [x{scale}] missing/unreadable: {path}")
                continue

            # Exhaustive best for reference.
            best = None
            r = int(max(0, args.radius))
            x_res = dominant_boundary_residue(img, scale, axis="x")
            y_res = dominant_boundary_residue(img, scale, axis="y")
            rows = []
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    score, f1u, f1t = eval_offset(img, scale, dx, dy, truth_unw, truth_tp)
                    if best is None or score > best["score"]:
                        best = {"dx": dx, "dy": dy, "score": score}
                    feats = candidate_features(img, scale, dx, dy, x_res, y_res)
                    rows.append({
                        "dx": dx, "dy": dy, "score_true": score, "f1u_true": f1u, "f1t_true": f1t, **feats
                    })

            rows = normalize_feature_rows(rows, ["terrain", "yellow", "center_bias", "edge_med", "phase_x", "phase_y"])
            print(f"  [x{scale}] best=({best['dx']},{best['dy']}) score={best['score']:.3f}")

            for name, w in method_weights.items():
                pred = None
                pred_val = None
                for row in rows:
                    val = 0.0
                    for k, wk in w.items():
                        val += float(wk) * float(row.get(k, 0.0))
                    if pred is None or val > pred_val:
                        pred = row
                        pred_val = val
                if pred is None:
                    continue
                dy_err = abs(int(pred["dy"]) - int(best["dy"]))
                summary[name]["score_sum"] += float(pred["score_true"])
                summary[name]["f1u_sum"] += float(pred["f1u_true"])
                summary[name]["f1t_sum"] += float(pred["f1t_true"])
                summary[name]["dy_err_sum"] += float(dy_err)
                summary[name]["n"] += 1
                print(
                    f"    {name:12s} -> ({int(pred['dx'])},{int(pred['dy'])}) "
                    f"score={pred['score_true']:.3f} dy_err={dy_err}"
                )

    print("\n=== Aggregate ===")
    ranked = []
    for name, s in summary.items():
        n = max(1, int(s["n"]))
        ranked.append((
            float(s["score_sum"] / n),
            -float(s["dy_err_sum"] / n),
            name,
            n,
            float(s["f1u_sum"] / n),
            float(s["f1t_sum"] / n),
            float(s["dy_err_sum"] / n),
        ))
    ranked.sort(reverse=True)
    for avg_score, _neg_dy, name, n, f1u, f1t, dyerr in ranked:
        print(
            f"{name:12s} n={n:2d} avg_score={avg_score:.3f} "
            f"avg_f1_unw={f1u:.3f} avg_f1_tp={f1t:.3f} avg_dy_err={dyerr:.3f}"
        )


if __name__ == "__main__":
    main()
