"""Benchmark minimap movement detection and tracking.

Compares fast motion estimators against a slow brute-force reference on
recorded minimap frames from a cavebot session.

Usage:
  python benchmark_minimap_motion.py --session training_data/cavebot_sessions/20260302_022442
  python benchmark_minimap_motion.py --session training_data/cavebot_sessions/20260302_022442 --runs 10 --warmup 3 --max-shift 8
"""

import argparse
import collections
import glob
import json
import math
import os
import statistics
import time

import cv2
import numpy as np

from src.bot.config.constants import BotConstants


TERRAIN_BGR = np.array(
    BotConstants.OBSTACLES
    + BotConstants.WALKABLE
    + list(getattr(BotConstants, "LOW_CONF_OBSTACLES", [])),
    dtype=np.uint8,
)
TERRAIN_CODES = (
    (TERRAIN_BGR[:, 0].astype(np.uint32) << 16)
    | (TERRAIN_BGR[:, 1].astype(np.uint32) << 8)
    | TERRAIN_BGR[:, 2].astype(np.uint32)
)


def _load_frames(session_dir):
    frames_dir = os.path.join(session_dir, "frames")
    files = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    frames, names = [], []
    for fp in files:
        img = cv2.imread(fp)
        if img is not None:
            frames.append(img)
            names.append(os.path.basename(fp))
    return frames, names


def _load_trace_meta(session_dir):
    p = os.path.join(session_dir, "trace.jsonl")
    if not os.path.isfile(p):
        return {}
    out = {}
    with open(p, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                row = json.loads(ln)
            except Exception:
                continue
            fr = row.get("frame")
            if not fr:
                continue
            out[fr] = {
                "zoom_label": row.get("zoom_label"),
                "trace_dx": row.get("move_dx"),
                "trace_dy": row.get("move_dy"),
                "trace_conf": row.get("move_confidence"),
            }
    return out


def _to_gray_f32(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)


def _terrain_mask(img):
    codes = (
        (img[:, :, 0].astype(np.uint32) << 16)
        | (img[:, :, 1].astype(np.uint32) << 8)
        | img[:, :, 2].astype(np.uint32)
    )
    return np.isin(codes, TERRAIN_CODES, assume_unique=False)


def _phase_gray(prev_bgr, curr_bgr):
    p = _to_gray_f32(prev_bgr)
    c = _to_gray_f32(curr_bgr)
    shift, resp = cv2.phaseCorrelate(p, c)
    return float(shift[0]), float(shift[1]), float(resp)


def _phase_down2(prev_bgr, curr_bgr):
    p = cv2.resize(prev_bgr, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    c = cv2.resize(curr_bgr, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    p = _to_gray_f32(p)
    c = _to_gray_f32(c)
    shift, resp = cv2.phaseCorrelate(p, c)
    return float(shift[0] * 2.0), float(shift[1] * 2.0), float(resp)


def _phase_terrain(prev_bgr, curr_bgr):
    pm = _terrain_mask(prev_bgr)
    cm = _terrain_mask(curr_bgr)
    mask = pm & cm
    p = _to_gray_f32(prev_bgr)
    c = _to_gray_f32(curr_bgr)
    p[~mask] = 0.0
    c[~mask] = 0.0
    shift, resp = cv2.phaseCorrelate(p, c)
    return float(shift[0]), float(shift[1]), float(resp)


def _template_center(prev_bgr, curr_bgr, max_shift=8):
    p = _to_gray_f32(prev_bgr)
    c = _to_gray_f32(curr_bgr)
    h, w = p.shape[:2]
    m = int(max(2, min(max_shift, h // 4, w // 4)))
    templ = p[m : h - m, m : w - m]
    if templ.size == 0:
        return 0.0, 0.0, 0.0
    res = cv2.matchTemplate(c, templ, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    dx = float(max_loc[0] - m)
    dy = float(max_loc[1] - m)
    return dx, dy, float(max_val)


def _template_hybrid_gated(prev_bgr, curr_bgr, max_shift=8, delta_discont=24.0):
    """Mirror runtime logic: template-first, phase fallback, discontinuity gate."""
    map_delta = float(np.mean(cv2.absdiff(prev_bgr, curr_bgr)))
    likely_discontinuity = map_delta >= float(delta_discont)

    # Template first
    dx, dy, t_conf = _template_center(prev_bgr, curr_bgr, max_shift=max_shift)
    if abs(dx) <= (max_shift + 1) and abs(dy) <= (max_shift + 1):
        if likely_discontinuity and t_conf < 0.80:
            # keep evaluating fallback; do not trust template here
            pass
        elif t_conf >= 0.55:
            return dx, dy, float(t_conf), 1.0

    # Fallback phase
    px, py, p_conf = _phase_gray(prev_bgr, curr_bgr)
    if likely_discontinuity and p_conf < 0.10:
        return 0.0, 0.0, float(p_conf), 0.0
    if abs(px) > (max_shift * 1.8) or abs(py) > (max_shift * 1.8):
        return 0.0, 0.0, float(p_conf), 0.0
    return float(px), float(py), float(p_conf), 1.0


def _make_hybrid_fn(
    max_shift=8,
    delta_discont=24.0,
    template_conf=0.55,
    template_conf_discont=0.80,
    phase_conf_discont=0.10,
    allow_phase_on_discont=True,
):
    def _fn(prev_bgr, curr_bgr):
        map_delta = float(np.mean(cv2.absdiff(prev_bgr, curr_bgr)))
        likely_discont = map_delta >= float(delta_discont)

        dx, dy, t_conf = _template_center(prev_bgr, curr_bgr, max_shift=max_shift)
        if abs(dx) <= (max_shift + 1) and abs(dy) <= (max_shift + 1):
            if likely_discont:
                if t_conf >= float(template_conf_discont):
                    return dx, dy, float(t_conf), 1.0
            else:
                if t_conf >= float(template_conf):
                    return dx, dy, float(t_conf), 1.0

        if likely_discont and not allow_phase_on_discont:
            return 0.0, 0.0, float(t_conf), 0.0

        px, py, p_conf = _phase_gray(prev_bgr, curr_bgr)
        if likely_discont and p_conf < float(phase_conf_discont):
            return 0.0, 0.0, float(p_conf), 0.0
        if abs(px) > (max_shift * 1.8) or abs(py) > (max_shift * 1.8):
            return 0.0, 0.0, float(p_conf), 0.0
        return float(px), float(py), float(p_conf), 1.0

    return _fn


def _overlap_slices(h, w, dx, dy):
    if dx >= 0:
        x0p, x1p = 0, w - dx
        x0c, x1c = dx, w
    else:
        x0p, x1p = -dx, w
        x0c, x1c = 0, w + dx
    if dy >= 0:
        y0p, y1p = 0, h - dy
        y0c, y1c = dy, h
    else:
        y0p, y1p = -dy, h
        y0c, y1c = 0, h + dy
    if x1p <= x0p or y1p <= y0p:
        return None
    return (slice(y0p, y1p), slice(x0p, x1p), slice(y0c, y1c), slice(x0c, x1c))


def _bruteforce_shift(prev_bgr, curr_bgr, max_shift=8):
    p = _to_gray_f32(prev_bgr)
    c = _to_gray_f32(curr_bgr)
    pm = _terrain_mask(prev_bgr)
    cm = _terrain_mask(curr_bgr)
    h, w = p.shape[:2]

    best = (1e18, 0, 0)
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            sl = _overlap_slices(h, w, dx, dy)
            if sl is None:
                continue
            yp, xp, yc, xc = sl
            mask = pm[yp, xp] & cm[yc, xc]
            if int(mask.sum()) < 80:
                continue
            diff = np.abs(p[yp, xp] - c[yc, xc])
            val = float(np.mean(diff[mask]))
            if val < best[0]:
                best = (val, dx, dy)
    # confidence-like score: inverse error
    score = 1.0 / (1.0 + best[0])
    return float(best[1]), float(best[2]), float(score)


def _percentile(vals, p):
    if not vals:
        return 0.0
    arr = sorted(vals)
    idx = int(round((p / 100.0) * (len(arr) - 1)))
    return float(arr[idx])


def _run_method(pairs, fn, runs=5, warmup=2):
    lat_ms = []
    last = []
    for run_i in range(runs + warmup):
        out = []
        t0 = time.perf_counter()
        for prev, curr in pairs:
            got = fn(prev, curr)
            if len(got) == 3:
                out.append((float(got[0]), float(got[1]), float(got[2]), 1.0))
            else:
                out.append((float(got[0]), float(got[1]), float(got[2]), float(got[3])))
        t1 = time.perf_counter()
        if run_i >= warmup:
            lat_ms.append((t1 - t0) * 1000.0 / max(1, len(pairs)))
            last = out
    return {
        "avg_ms": float(statistics.mean(lat_ms)) if lat_ms else 0.0,
        "p50_ms": float(statistics.median(lat_ms)) if lat_ms else 0.0,
        "p95_ms": _percentile(lat_ms, 95),
        "std_ms": float(statistics.pstdev(lat_ms)) if len(lat_ms) > 1 else 0.0,
        "pred": last,
    }


def _score_against_ref(pred, ref):
    if not pred or not ref:
        return {}
    dx_err, dy_err, mag_err = [], [], []
    agree = 0
    oppose = 0
    moved_total = 0
    pos_p = np.zeros((len(pred), 2), dtype=np.float64)
    pos_r = np.zeros((len(ref), 2), dtype=np.float64)
    valid_count = 0
    for i in range(len(pred)):
        px, py, _, valid = pred[i]
        rx, ry, _ = ref[i]
        if valid >= 0.5:
            valid_count += 1
        dx_err.append(abs(px - rx))
        dy_err.append(abs(py - ry))
        mag_err.append(abs(math.hypot(px, py) - math.hypot(rx, ry)))
        if i > 0:
            pos_p[i] = pos_p[i - 1] + np.array([px, py])
            pos_r[i] = pos_r[i - 1] + np.array([rx, ry])
        # Direction agreement should be measured on the dominant movement axis
        # with a deadzone; tiny orthogonal noise should not count as disagreement.
        if math.hypot(rx, ry) >= 0.6:
            moved_total += 1
            if abs(rx) >= abs(ry):
                # X-dominant motion
                if abs(rx) < 0.35:
                    continue
                s_ref = np.sign(rx)
                s_pred = np.sign(px) if abs(px) >= 0.35 else 0
            else:
                # Y-dominant motion
                if abs(ry) < 0.35:
                    continue
                s_ref = np.sign(ry)
                s_pred = np.sign(py) if abs(py) >= 0.35 else 0

            if s_pred == s_ref:
                agree += 1
            elif s_pred == -s_ref:
                oppose += 1
    drift = np.linalg.norm(pos_p - pos_r, axis=1)
    return {
        "mae_dx": float(statistics.mean(dx_err)),
        "mae_dy": float(statistics.mean(dy_err)),
        "mae_mag": float(statistics.mean(mag_err)),
        "p95_dx": _percentile(dx_err, 95),
        "p95_dy": _percentile(dy_err, 95),
        "track_drift_mean": float(np.mean(drift)),
        "track_drift_p95": _percentile(drift.tolist(), 95),
        "dir_agree": float(100.0 * agree / moved_total) if moved_total > 0 else 100.0,
        "dir_oppose": float(100.0 * oppose / moved_total) if moved_total > 0 else 0.0,
        "moved_ref_frames": int(moved_total),
        "valid_rate": float(100.0 * valid_count / len(pred)) if pred else 0.0,
    }


def _composite_score(stats):
    # Higher is better: prioritize geometric accuracy and low drift,
    # then penalize invalid frames and runtime cost.
    return (
        1000.0
        - 130.0 * float(stats["mae_dx"])
        - 130.0 * float(stats["mae_dy"])
        - 10.0 * float(stats["track_drift_p95"])
        - 2.0 * max(0.0, 100.0 - float(stats["valid_rate"]))
        - 18.0 * float(stats["avg_ms"])
        + 0.4 * float(stats["dir_agree"])
        - 0.8 * float(stats["dir_oppose"])
    )


def _run_hybrid_sweep(
    pairs,
    ref,
    max_shift=8,
    runs=4,
    warmup=1,
):
    delta_vals = [20.0, 24.0, 28.0, 32.0]
    tconf_vals = [0.50, 0.55, 0.60]
    tconf_dis_vals = [0.75, 0.80, 0.85, 0.90]
    pconf_dis_vals = [0.05, 0.10, 0.15, 0.20]
    phase_on_dis_vals = [True, False]

    out = []
    total = (
        len(delta_vals)
        * len(tconf_vals)
        * len(tconf_dis_vals)
        * len(pconf_dis_vals)
        * len(phase_on_dis_vals)
    )
    idx = 0
    for d in delta_vals:
        for tc in tconf_vals:
            for tcd in tconf_dis_vals:
                for pcd in pconf_dis_vals:
                    for aphase in phase_on_dis_vals:
                        idx += 1
                        fn = _make_hybrid_fn(
                            max_shift=max_shift,
                            delta_discont=d,
                            template_conf=tc,
                            template_conf_discont=tcd,
                            phase_conf_discont=pcd,
                            allow_phase_on_discont=aphase,
                        )
                        st = _run_method(pairs, fn, runs=runs, warmup=warmup)
                        sc = _score_against_ref(st["pred"], ref)
                        rec = {**st, **sc}
                        rec["score"] = _composite_score(rec)
                        rec["delta_discont"] = d
                        rec["template_conf"] = tc
                        rec["template_conf_discont"] = tcd
                        rec["phase_conf_discont"] = pcd
                        rec["allow_phase_on_discont"] = aphase
                        out.append(rec)
                        if idx % 80 == 0 or idx == total:
                            print(f"[SWEEP] {idx}/{total}")
    out.sort(key=lambda r: r["score"], reverse=True)
    return out


def run_session(
    session_dir,
    runs=6,
    warmup=2,
    max_shift=8,
    sweep_hybrid=False,
    sweep_runs=4,
    sweep_warmup=1,
):
    frames, names = _load_frames(session_dir)
    if len(frames) < 2:
        print(f"Skipping {session_dir}: need at least 2 frames")
        return None
    pairs = list(zip(frames[:-1], frames[1:]))
    meta = _load_trace_meta(session_dir)

    print(f"Session: {session_dir}")
    print(f"Frames: {len(frames)} | Pairs: {len(pairs)}")
    zoom_hist = collections.Counter()
    for n in names:
        z = meta.get(n, {}).get("zoom_label")
        if z in (1, 2, 4):
            zoom_hist[int(z)] += 1
    if zoom_hist:
        print("Zoom labels:", dict(sorted(zoom_hist.items())))

    # Reference (slow)
    t0 = time.perf_counter()
    ref = [_bruteforce_shift(p, c, max_shift=max_shift) for p, c in pairs]
    t1 = time.perf_counter()
    ref_ms = (t1 - t0) * 1000.0 / len(pairs)
    print(f"Reference brute-force: {ref_ms:.3f}ms/pair (max_shift={max_shift})")

    methods = {
        "phase_gray": _phase_gray,
        "phase_down2": _phase_down2,
        "phase_terrain": _phase_terrain,
        "template_center": lambda p, c: _template_center(p, c, max_shift=max_shift),
        "hybrid_gated": lambda p, c: _template_hybrid_gated(p, c, max_shift=max_shift),
    }

    results = {}
    for name, fn in methods.items():
        st = _run_method(pairs, fn, runs=runs, warmup=warmup)
        sc = _score_against_ref(st["pred"], ref)
        results[name] = {**st, **sc}

    print("=== Motion Detect Benchmark ===")
    for name in ("phase_gray", "phase_down2", "phase_terrain", "template_center", "hybrid_gated"):
        r = results[name]
        speedup = (ref_ms / r["avg_ms"]) if r["avg_ms"] > 0 else 0.0
        print(
            f"{name:>14}: avg={r['avg_ms']:.3f}ms p95={r['p95_ms']:.3f} "
            f"| mae(dx,dy)=({r['mae_dx']:.3f},{r['mae_dy']:.3f}) "
            f"drift_p95={r['track_drift_p95']:.2f} dir_agree={r['dir_agree']:.1f}% "
            f"oppose={r['dir_oppose']:.1f}% valid={r['valid_rate']:.1f}% speedup={speedup:.1f}x"
        )

    best = sorted(
        results.items(),
        key=lambda kv: (kv[1]["mae_dx"] + kv[1]["mae_dy"] + 0.25 * kv[1]["avg_ms"]),
    )[0][0]
    print(f"Suggested best tradeoff: {best}")

    if sweep_hybrid:
        print("=== Hybrid Sweep (policy/threshold search) ===")
        ranked = _run_hybrid_sweep(
            pairs,
            ref,
            max_shift=max_shift,
            runs=sweep_runs,
            warmup=sweep_warmup,
        )
        topn = ranked[:12]
        for i, r in enumerate(topn, 1):
            print(
                f"{i:>2}) score={r['score']:.2f} mae=({r['mae_dx']:.3f},{r['mae_dy']:.3f}) "
                f"drift_p95={r['track_drift_p95']:.2f} valid={r['valid_rate']:.1f}% avg={r['avg_ms']:.3f}ms "
                f"d={r['delta_discont']} tc={r['template_conf']} tcd={r['template_conf_discont']} "
                f"pcd={r['phase_conf_discont']} phase_on_dis={r['allow_phase_on_discont']}"
            )
    return results


def main():
    ap = argparse.ArgumentParser(description="Benchmark minimap movement detection")
    ap.add_argument("--session", required=True, help="Session dir with frames/")
    ap.add_argument("--runs", type=int, default=8)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--max-shift", type=int, default=8)
    ap.add_argument("--sweep-hybrid", action="store_true", help="Run threshold/policy sweep for hybrid gated method")
    ap.add_argument("--sweep-runs", type=int, default=4, help="Runs per hybrid sweep candidate")
    ap.add_argument("--sweep-warmup", type=int, default=1, help="Warmup runs per hybrid sweep candidate")
    args = ap.parse_args()
    run_session(
        args.session,
        runs=args.runs,
        warmup=args.warmup,
        max_shift=args.max_shift,
        sweep_hybrid=bool(args.sweep_hybrid),
        sweep_runs=max(1, int(args.sweep_runs)),
        sweep_warmup=max(0, int(args.sweep_warmup)),
    )


if __name__ == "__main__":
    main()
