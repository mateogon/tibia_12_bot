"""
Evaluate unwalkable detection quality against annotated truth.

Data source:
  training_data/unwalkable_samples/*.json

This script now supports two modes:
1) Baseline report from saved JSON predictions (`auto.*`).
2) Offline experiment sweep from minimap images with multiple approaches.

Examples:
  python tools/evaluate_unwalkable_samples.py --data training_data/unwalkable_samples --details
  python tools/evaluate_unwalkable_samples.py --data training_data/unwalkable_samples --experiments --top-methods 12
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


try:
    import cv2
    import numpy as np
except Exception as e:  # pragma: no cover
    cv2 = None
    np = None
    _IMPORT_ERR = e
else:
    _IMPORT_ERR = None


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


Tile = Tuple[int, int]


@dataclass
class Score:
    n: int = 0
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, tp: int, fp: int, fn: int) -> None:
        self.n += 1
        self.tp += tp
        self.fp += fp
        self.fn += fn

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return (self.tp / d) if d else 1.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return (self.tp / d) if d else 1.0

    @property
    def f1(self) -> float:
        p = self.precision
        r = self.recall
        return (2 * p * r / (p + r)) if (p + r) else 0.0


def pairs_to_set(pairs: Iterable[Iterable[int]]) -> Set[Tile]:
    out: Set[Tile] = set()
    for p in pairs or []:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            continue
        r, c = int(p[0]), int(p[1])
        if 0 <= r < 11 and 0 <= c < 15:
            out.add((r, c))
    return out


def prf(pred: Set[Tile], truth: Set[Tile]) -> Tuple[int, int, int, float, float, float]:
    tp = len(pred & truth)
    fp = len(pred - truth)
    fn = len(truth - pred)
    prec = (tp / (tp + fp)) if (tp + fp) else 1.0
    rec = (tp / (tp + fn)) if (tp + fn) else 1.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
    return tp, fp, fn, prec, rec, f1


def load_samples(data_dir: str) -> List[dict]:
    paths = sorted(glob.glob(os.path.join(data_dir, "*.json")))
    rows: List[dict] = []
    for p in paths:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        d["_path"] = p
        rows.append(d)
    return rows


def zone_masks() -> Tuple[Set[Tile], Set[Tile], Set[Tile]]:
    center = {(r, c) for r in range(3, 8) for c in range(5, 10)}
    corners = (
        {(r, c) for r in range(0, 3) for c in range(0, 3)}
        | {(r, c) for r in range(0, 3) for c in range(12, 15)}
        | {(r, c) for r in range(8, 11) for c in range(0, 3)}
        | {(r, c) for r in range(8, 11) for c in range(12, 15)}
    )
    edge = {(r, c) for r in range(11) for c in range(15) if r in (0, 10) or c in (0, 14)}
    return center, corners, edge


def bucket(counter: Counter, center: Set[Tile], corners: Set[Tile], edge: Set[Tile]) -> Dict[str, float]:
    total = sum(counter.values())
    c = sum(v for k, v in counter.items() if k in center)
    co = sum(v for k, v in counter.items() if k in corners)
    e = sum(v for k, v in counter.items() if k in edge)
    return {
        "total": total,
        "center": c,
        "center_pct": (100.0 * c / total) if total else 0.0,
        "corners": co,
        "corners_pct": (100.0 * co / total) if total else 0.0,
        "edge": e,
        "edge_pct": (100.0 * e / total) if total else 0.0,
    }


def format_line(prefix: str, s: Score) -> str:
    return (
        f"{prefix}: n={s.n} tp={s.tp} fp={s.fp} fn={s.fn} "
        f"prec={s.precision:.3f} rec={s.recall:.3f} f1={s.f1:.3f}"
    )


def _parse_ts_from_name(path: str) -> Optional[datetime]:
    base = os.path.basename(path)
    stem = os.path.splitext(base)[0]
    # expected: YYYYMMDD_HHMMSS_micro...
    parts = stem.split("_")
    if len(parts) < 3:
        return None
    key = f"{parts[0]}_{parts[1]}_{parts[2]}"
    try:
        return datetime.strptime(key, "%Y%m%d_%H%M%S_%f")
    except Exception:
        return None


def _tiles_signature(tiles: Set[Tile]) -> str:
    return "|".join(f"{r},{c}" for r, c in sorted(tiles))


def _iter_components_8(tiles: Set[Tile]) -> List[List[Tile]]:
    rem = set(tiles)
    comps: List[List[Tile]] = []
    dirs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    while rem:
        start = next(iter(rem))
        stack = [start]
        rem.remove(start)
        comp = [start]
        while stack:
            r, c = stack.pop()
            for dr, dc in dirs:
                n = (r + dr, c + dc)
                if n in rem:
                    rem.remove(n)
                    stack.append(n)
                    comp.append(n)
        comps.append(comp)
    return comps


def _transform_tiles(tiles: Set[Tile], mode: str, dr: int = 0, dc: int = 0) -> Set[Tile]:
    out = {(r + int(dr), c + int(dc)) for (r, c) in tiles}
    out = {(r, c) for (r, c) in out if 0 <= r < 11 and 0 <= c < 15}
    if mode == "raw":
        return out
    if mode == "comp_ne":
        keep: Set[Tile] = set()
        for comp in _iter_components_8(out):
            # Keep one representative biased to north-east; useful for
            # zoom spill where true yellow often is the top-right tile.
            best = min(comp, key=lambda rc: (rc[0], -rc[1]))
            keep.add(best)
        return keep
    return out


def zoom_tp_consistency_report(rows: List[dict], sync_gold_only: bool, top_n: int) -> None:
    rows2 = []
    for d in rows:
        if sync_gold_only and not (d.get("sync_gold") or d.get("quality_tag") == "sync_gold"):
            continue
        z = int(d.get("zoom_level") or d.get("map_scale") or 0)
        if z not in (1, 2, 4):
            continue
        labels = d.get("labels") or {}
        auto = d.get("auto") or {}
        rows2.append(
            {
                "path": d["_path"],
                "ts": _parse_ts_from_name(d["_path"]),
                "zoom": z,
                "unw_truth": pairs_to_set(labels.get("unwalkable", [])),
                "tp_truth": pairs_to_set(labels.get("tp", [])),
                "tp_auto": pairs_to_set(auto.get("tp", [])),
            }
        )

    if not rows2:
        print("\nCross-zoom TP consistency: no eligible samples.")
        return

    # Group by unwalkable truth signature (same spot proxy).
    by_sig: Dict[str, List[dict]] = defaultdict(list)
    for r in rows2:
        sig = _tiles_signature(r["unw_truth"])
        by_sig[sig].append(r)

    eligible = []
    for sig, group in by_sig.items():
        zset = {g["zoom"] for g in group}
        if 4 in zset and (1 in zset or 2 in zset):
            eligible.append((sig, group))

    if not eligible:
        print("\nCross-zoom TP consistency: no groups with x4 and x1/x2 together.")
        return

    def nearest_ref(target: dict, refs: List[dict]) -> dict:
        if not refs:
            return None
        if target["ts"] is None:
            return refs[0]
        with_ts = [r for r in refs if r["ts"] is not None]
        if not with_ts:
            return refs[0]
        return min(with_ts, key=lambda r: abs((r["ts"] - target["ts"]).total_seconds()))

    # Compare x1/x2 auto-tp against nearest x4 auto-tp in same spot-group.
    pair_scores = {1: Score(), 2: Score()}
    pair_scores_truth = {1: Score(), 2: Score()}
    delta_fp = {1: Counter(), 2: Counter()}
    delta_fn = {1: Counter(), 2: Counter()}

    # Search best simple correction per zoom against x4 reference.
    correction_candidates: List[Tuple[str, int, int]] = [("raw", 0, 0)]
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            correction_candidates.append(("raw", dr, dc))
            correction_candidates.append(("comp_ne", dr, dc))
    corr_scores = {
        1: {c: Score() for c in correction_candidates},
        2: {c: Score() for c in correction_candidates},
    }

    pair_count = 0
    for _sig, group in eligible:
        refs4 = [g for g in group if g["zoom"] == 4]
        for z in (1, 2):
            tgts = [g for g in group if g["zoom"] == z]
            for t in tgts:
                ref = nearest_ref(t, refs4)
                if ref is None:
                    continue
                pair_count += 1
                pred = set(t["tp_auto"])
                truth_ref = set(ref["tp_auto"])
                tp, fp, fn, _p, _r, _f = prf(pred, truth_ref)
                pair_scores[z].add(tp, fp, fn)

                # Optional: compare to TP labels when available on both.
                if t["tp_truth"] and ref["tp_truth"]:
                    tp2, fp2, fn2, _p2, _r2, _f2 = prf(pred, t["tp_truth"])
                    pair_scores_truth[z].add(tp2, fp2, fn2)

                # Directional bias of errors vs nearest reference TP tile.
                for fpt in (pred - truth_ref):
                    if truth_ref:
                        nr = min(truth_ref, key=lambda rc: abs(rc[0] - fpt[0]) + abs(rc[1] - fpt[1]))
                        delta_fp[z][(int(fpt[0] - nr[0]), int(fpt[1] - nr[1]))] += 1
                for fnt in (truth_ref - pred):
                    if pred:
                        nr = min(pred, key=lambda rc: abs(rc[0] - fnt[0]) + abs(rc[1] - fnt[1]))
                        delta_fn[z][(int(fnt[0] - nr[0]), int(fnt[1] - nr[1]))] += 1

                for cand in correction_candidates:
                    mode, dr, dc = cand
                    pred2 = _transform_tiles(pred, mode=mode, dr=dr, dc=dc)
                    tp3, fp3, fn3, _p3, _r3, _f3 = prf(pred2, truth_ref)
                    corr_scores[z][cand].add(tp3, fp3, fn3)

    print("\nCross-zoom TP consistency (x1/x2 compared to x4 auto-TP baseline):")
    print(f"  groups={len(eligible)} paired_samples={pair_count}")
    for z in (1, 2):
        print(format_line(f"  zoom{z} vs x4", pair_scores[z]))
        top_fp = delta_fp[z].most_common(max(1, int(top_n)))
        top_fn = delta_fn[z].most_common(max(1, int(top_n)))
        print(f"    top FP deltas (dr,dc): {top_fp}")
        print(f"    top FN deltas (dr,dc): {top_fn}")

    for z in (1, 2):
        ranked = sorted(corr_scores[z].items(), key=lambda kv: kv[1].f1, reverse=True)
        best_c, best_s = ranked[0]
        base_s = corr_scores[z][("raw", 0, 0)]
        print(
            f"  zoom{z} best_correction={best_c} "
            f"f1={best_s.f1:.3f} (base={base_s.f1:.3f}, "
            f"delta={best_s.f1 - base_s.f1:+.3f})"
        )

    if pair_scores_truth[1].n or pair_scores_truth[2].n:
        print("\nCross-zoom TP vs local TP truth (where TP labels exist):")
        for z in (1, 2):
            if pair_scores_truth[z].n:
                print(format_line(f"  zoom{z} vs tp_truth", pair_scores_truth[z]))


def baseline_report(rows: List[dict], details: bool, top_n: int) -> None:
    per_zoom = defaultdict(lambda: {"auto": Score(), "coll": Score()})
    fn_auto = Counter()
    fn_coll = Counter()
    fp_auto = Counter()
    fp_coll = Counter()

    if details:
        print("Per-sample baseline metrics:")

    for d in rows:
        z = int(d.get("zoom_level") or d.get("map_scale") or 0)
        truth = pairs_to_set((d.get("labels") or {}).get("unwalkable", []))
        auto = pairs_to_set((d.get("auto") or {}).get("unwalkable", []))
        coll = pairs_to_set((d.get("auto") or {}).get("collision_unwalkable", []))

        atp, afp, afn, aprec, arec, af1 = prf(auto, truth)
        ctp, cfp, cfn, cprec, crec, cf1 = prf(coll, truth)

        per_zoom[z]["auto"].add(atp, afp, afn)
        per_zoom[z]["coll"].add(ctp, cfp, cfn)

        for t in (truth - auto):
            fn_auto[t] += 1
        for t in (truth - coll):
            fn_coll[t] += 1
        for t in (auto - truth):
            fp_auto[t] += 1
        for t in (coll - truth):
            fp_coll[t] += 1

        if details:
            name = os.path.basename(d["_path"])
            print(
                f"  {name} zoom={z} | "
                f"auto f1={af1:.3f} (p={aprec:.3f} r={arec:.3f}) | "
                f"coll f1={cf1:.3f} (p={cprec:.3f} r={crec:.3f})"
            )

    print("\nAggregated baseline by zoom:")
    for z in sorted(per_zoom.keys()):
        print(format_line(f"  zoom{z} auto", per_zoom[z]["auto"]))
        print(format_line(f"  zoom{z} coll", per_zoom[z]["coll"]))

    cset, coset, eset = zone_masks()
    print("\nBaseline error geography:")
    for name, cnt in [("FN auto", fn_auto), ("FN coll", fn_coll), ("FP auto", fp_auto), ("FP coll", fp_coll)]:
        b = bucket(cnt, cset, coset, eset)
        print(
            f"  {name}: total={b['total']} "
            f"center={b['center']}({b['center_pct']:.1f}%) "
            f"corners={b['corners']}({b['corners_pct']:.1f}%) "
            f"edge={b['edge']}({b['edge_pct']:.1f}%)"
        )

    print(f"\nTop {top_n} FN tiles (auto): {fn_auto.most_common(top_n)}")
    print(f"Top {top_n} FN tiles (coll): {fn_coll.most_common(top_n)}")


def extract_sampling_context(sample: dict, data_dir: str, phase_dx: int = 0, phase_dy: int = 0) -> Optional[dict]:
    files = sample.get("files") or {}
    map_file = files.get("minimap")
    if not map_file:
        return None
    img_path = os.path.join(data_dir, map_file)
    img = cv2.imread(img_path, cv2.IMREAD_COLOR)
    if img is None:
        return None

    h, w = img.shape[:2]
    s = int(max(1, sample.get("zoom_level") or sample.get("map_scale") or 2))
    auto = sample.get("auto") or {}
    adx = int(auto.get("anchor_dx", 0))
    ady = int(auto.get("anchor_dy", 0))
    cx = (w // 2) + adx + int(phase_dx)
    cy = (h // 2) + ady + int(phase_dy)

    local = np.zeros((11, 15, 3), dtype=np.uint8)
    for r in range(11):
        for c in range(15):
            px = int(cx + (c - 7) * s)
            py = int(cy + (r - 5) * s)
            if 0 <= px < w and 0 <= py < h:
                local[r, c] = img[py, px]
    return {
        "img": img,
        "local": local,
        "s": int(s),
        "cx": int(cx),
        "cy": int(cy),
    }


def yellow_mask(local: np.ndarray, tol: int = 12) -> np.ndarray:
    target = np.array([0, 255, 255], dtype=np.int16)
    diff = np.abs(local.astype(np.int16) - target)
    return np.all(diff <= int(max(0, tol)), axis=-1)


def palette_match_l1(local: np.ndarray, palette: Sequence[Sequence[int]], tol: int) -> np.ndarray:
    pal = np.array(list(palette), dtype=np.int16)
    if pal.size == 0:
        return np.zeros(local.shape[:2], dtype=bool)
    px = local.astype(np.int16)
    d = np.abs(px[:, :, None, :] - pal[None, None, :, :]).sum(axis=3)
    return np.min(d, axis=2) <= int(max(0, tol))


def low_conf_cluster_filter(is_obstacle: np.ndarray, is_low: np.ndarray, max_comp: int) -> np.ndarray:
    if max_comp <= 0:
        return is_obstacle
    h, w = is_obstacle.shape
    visited = np.zeros((h, w), dtype=bool)
    dirs = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    out = is_obstacle.copy()

    for r in range(h):
        for c in range(w):
            if not is_low[r, c] or visited[r, c]:
                continue
            stack = [(r, c)]
            comp = []
            visited[r, c] = True
            while stack:
                cr, cc = stack.pop()
                comp.append((cr, cc))
                for dr, dc in dirs:
                    nr, nc = cr + dr, cc + dc
                    if 0 <= nr < h and 0 <= nc < w and not visited[nr, nc] and is_low[nr, nc]:
                        visited[nr, nc] = True
                        stack.append((nr, nc))
            if len(comp) <= max_comp:
                for rr, cc in comp:
                    out[rr, cc] = True
    return out


def nearest_classify(local: np.ndarray, obs_palette: Sequence[Sequence[int]], walk_palette: Sequence[Sequence[int]], margin: int) -> np.ndarray:
    obs = np.array(list(obs_palette), dtype=np.int16)
    walk = np.array(list(walk_palette), dtype=np.int16)
    px = local.astype(np.int16)
    d_obs = np.abs(px[:, :, None, :] - obs[None, None, :, :]).sum(axis=3).min(axis=2)
    d_walk = np.abs(px[:, :, None, :] - walk[None, None, :, :]).sum(axis=3).min(axis=2)
    return (d_obs + int(margin)) < d_walk


def mask_to_tiles(mask: np.ndarray) -> Set[Tile]:
    ys, xs = np.where(mask)
    return {(int(r), int(c)) for r, c in zip(ys.tolist(), xs.tolist())}


def _block_match_ratio_l1(block_bgr: np.ndarray, palette: Sequence[Sequence[int]], tol: int) -> float:
    if block_bgr is None or block_bgr.size == 0:
        return 0.0
    pal = np.array(list(palette), dtype=np.int16)
    if pal.size == 0:
        return 0.0
    px = block_bgr.reshape(-1, 3).astype(np.int16)
    d = np.abs(px[:, None, :] - pal[None, :, :]).sum(axis=2)
    m = (np.min(d, axis=1) <= int(max(0, tol)))
    return float(np.mean(m)) if m.size else 0.0


def _block_yellow_ratio(block_bgr: np.ndarray, tol: int = 12) -> float:
    if block_bgr is None or block_bgr.size == 0:
        return 0.0
    target = np.array([0, 255, 255], dtype=np.int16)
    px = block_bgr.reshape(-1, 3).astype(np.int16)
    d = np.abs(px - target[None, :])
    m = np.all(d <= int(max(0, tol)), axis=1)
    return float(np.mean(m)) if m.size else 0.0


def classify_from_tile_blocks(
    ctx: dict,
    obs_palette: Sequence[Sequence[int]],
    low_palette: Sequence[Sequence[int]],
    obs_tol: int,
    low_tol: int,
    obs_ratio_thr: float,
    low_ratio_thr: float,
    yellow_ratio_thr: float,
    max_comp: int,
) -> np.ndarray:
    """
    Classify tiles by using all pixels in each minimap tile block (size s x s).
    """
    img = ctx["img"]
    s = int(max(1, ctx["s"]))
    cx = int(ctx["cx"])
    cy = int(ctx["cy"])
    h, w = img.shape[:2]

    is_obs = np.zeros((11, 15), dtype=bool)
    is_low = np.zeros((11, 15), dtype=bool)
    is_yellow = np.zeros((11, 15), dtype=bool)

    for r in range(11):
        for c in range(15):
            xc = int(cx + (c - 7) * s)
            yc = int(cy + (r - 5) * s)
            # Use full tile block around sampled center.
            x0 = int(xc - (s // 2))
            y0 = int(yc - (s // 2))
            x1 = int(x0 + s)
            y1 = int(y0 + s)
            x0c, y0c = max(0, x0), max(0, y0)
            x1c, y1c = min(w, x1), min(h, y1)
            if x1c <= x0c or y1c <= y0c:
                continue
            block = img[y0c:y1c, x0c:x1c]
            yr = _block_yellow_ratio(block, tol=12)
            if yr >= float(yellow_ratio_thr):
                is_yellow[r, c] = True
                continue
            orr = _block_match_ratio_l1(block, obs_palette, tol=obs_tol)
            lrr = _block_match_ratio_l1(block, low_palette, tol=low_tol)
            if orr >= float(obs_ratio_thr):
                is_obs[r, c] = True
            if lrr >= float(low_ratio_thr):
                is_low[r, c] = True

    is_obs[is_yellow] = False
    is_low[is_yellow] = False
    is_obs = low_conf_cluster_filter(is_obs, is_low, max_comp=max_comp)
    return is_obs


def run_experiments(rows: List[dict], data_dir: str, top_methods: int, details: bool) -> None:
    if cv2 is None or np is None:
        print(f"[ERR] experiments require numpy/cv2 in this Python env: {_IMPORT_ERR}")
        return
    try:
        from src.config.constants import BotConstants
    except Exception as e:
        print(f"[ERR] experiments require project constants import (src.config.constants): {e}")
        return

    obs_palette = BotConstants.OBSTACLES
    low_palette = getattr(BotConstants, "LOW_CONF_OBSTACLES", [])
    walk_palette = BotConstants.WALKABLE

    methods: List[Tuple[str, dict]] = []
    methods.append(("json_auto", {"kind": "json_auto"}))
    methods.append(("json_coll", {"kind": "json_coll"}))

    for pdx, pdy in [(0, 0), (-1, -1), (1, 1)]:
        methods.append((f"exact_phase({pdx},{pdy})", {"kind": "exact", "pdx": pdx, "pdy": pdy}))

    for tol in [16, 24, 32, 40, 48]:
        for max_comp in [0, 2, 3, 4]:
            methods.append((
                f"l1_obs{tol}_low{tol+10}_comp{max_comp}",
                {"kind": "l1", "obs_tol": tol, "low_tol": tol + 10, "max_comp": max_comp, "pdx": 0, "pdy": 0},
            ))

    for margin in [-10, 0, 10, 20]:
        methods.append((f"nearest_margin{margin}", {"kind": "nearest", "margin": margin, "pdx": 0, "pdy": 0}))

    for tol in [24, 32, 40]:
        for margin in [0, 10]:
            methods.append((
                f"hybrid_l1{tol}_m{margin}",
                {"kind": "hybrid", "obs_tol": tol, "low_tol": tol + 10, "max_comp": 3, "margin": margin, "pdx": 0, "pdy": 0},
            ))

    # New: full-tile-pixel methods (uses all pixels in minimap tile block, not 1 center pixel).
    for obs_tol in [16, 24, 32]:
        for obs_ratio in [0.20, 0.35, 0.50]:
            methods.append((
                f"block_obs{obs_tol}_r{obs_ratio:.2f}_comp4",
                {
                    "kind": "block",
                    "obs_tol": obs_tol,
                    "low_tol": obs_tol + 10,
                    "obs_ratio": obs_ratio,
                    "low_ratio": 0.20,
                    "yellow_ratio": 0.35,
                    "max_comp": 4,
                    "pdx": 0,
                    "pdy": 0,
                },
            ))

    total_by_method: Dict[str, Score] = {m: Score() for m, _ in methods}
    by_zoom_method: Dict[int, Dict[str, Score]] = defaultdict(lambda: {m: Score() for m, _ in methods})

    if details:
        print("\nExperiment per-sample best method:")

    for d in rows:
        z = int(d.get("zoom_level") or d.get("map_scale") or 0)
        truth = pairs_to_set((d.get("labels") or {}).get("unwalkable", []))

        ctx_cache: Dict[Tuple[int, int], Optional[dict]] = {}
        sample_scores: List[Tuple[str, float, float, float]] = []

        for method_name, cfg in methods:
            kind = cfg["kind"]
            pred: Set[Tile]

            if kind == "json_auto":
                pred = pairs_to_set((d.get("auto") or {}).get("unwalkable", []))
            elif kind == "json_coll":
                pred = pairs_to_set((d.get("auto") or {}).get("collision_unwalkable", []))
            else:
                key = (int(cfg.get("pdx", 0)), int(cfg.get("pdy", 0)))
                if key not in ctx_cache:
                    ctx_cache[key] = extract_sampling_context(d, data_dir, phase_dx=key[0], phase_dy=key[1])
                ctx = ctx_cache[key]
                if ctx is None:
                    pred = set()
                else:
                    local = ctx["local"]
                    y = yellow_mask(local, tol=12)
                    if kind == "exact":
                        is_obs = palette_match_l1(local, obs_palette, tol=0)
                        is_obs[y] = False
                        pred = mask_to_tiles(is_obs)
                    elif kind == "l1":
                        is_obs = palette_match_l1(local, obs_palette, tol=int(cfg["obs_tol"]))
                        is_low = palette_match_l1(local, low_palette, tol=int(cfg["low_tol"]))
                        is_obs[y] = False
                        is_low[y] = False
                        is_obs = low_conf_cluster_filter(is_obs, is_low, int(cfg["max_comp"]))
                        pred = mask_to_tiles(is_obs)
                    elif kind == "nearest":
                        is_obs = nearest_classify(local, obs_palette, walk_palette, int(cfg["margin"]))
                        is_obs[y] = False
                        pred = mask_to_tiles(is_obs)
                    elif kind == "hybrid":
                        a = palette_match_l1(local, obs_palette, tol=int(cfg["obs_tol"]))
                        low = palette_match_l1(local, low_palette, tol=int(cfg["low_tol"]))
                        a[y] = False
                        low[y] = False
                        a = low_conf_cluster_filter(a, low, int(cfg["max_comp"]))
                        b = nearest_classify(local, obs_palette, walk_palette, int(cfg["margin"]))
                        b[y] = False
                        is_obs = a | b
                        pred = mask_to_tiles(is_obs)
                    elif kind == "block":
                        is_obs = classify_from_tile_blocks(
                            ctx=ctx,
                            obs_palette=obs_palette,
                            low_palette=low_palette,
                            obs_tol=int(cfg["obs_tol"]),
                            low_tol=int(cfg["low_tol"]),
                            obs_ratio_thr=float(cfg["obs_ratio"]),
                            low_ratio_thr=float(cfg["low_ratio"]),
                            yellow_ratio_thr=float(cfg["yellow_ratio"]),
                            max_comp=int(cfg["max_comp"]),
                        )
                        pred = mask_to_tiles(is_obs)
                    else:
                        pred = set()

            tp, fp, fn, p, r, f = prf(pred, truth)
            total_by_method[method_name].add(tp, fp, fn)
            by_zoom_method[z][method_name].add(tp, fp, fn)
            sample_scores.append((method_name, f, p, r))

        if details and sample_scores:
            sample_scores.sort(key=lambda x: x[1], reverse=True)
            best = sample_scores[0]
            print(
                f"  {os.path.basename(d['_path'])} zoom={z} -> "
                f"best={best[0]} f1={best[1]:.3f} p={best[2]:.3f} r={best[3]:.3f}"
            )

    ranked = sorted(total_by_method.items(), key=lambda kv: kv[1].f1, reverse=True)
    k = max(1, int(top_methods))

    print("\nTop methods (overall):")
    for name, score in ranked[:k]:
        print(format_line(f"  {name}", score))

    print("\nBest method per zoom:")
    for z in sorted(by_zoom_method.keys()):
        items = sorted(by_zoom_method[z].items(), key=lambda kv: kv[1].f1, reverse=True)
        best_name, best_score = items[0]
        print(format_line(f"  zoom{z} best={best_name}", best_score))
        # Show runner-up too for learning signal.
        if len(items) > 1:
            name2, score2 = items[1]
            print(format_line(f"      runner_up={name2}", score2))


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate unwalkable detection vs annotated truth.")
    ap.add_argument("--data", default="training_data/unwalkable_samples", help="Directory with sample *.json files")
    ap.add_argument("--details", action="store_true", help="Print per-sample metrics")
    ap.add_argument("--top", type=int, default=12, help="Top-N hotspot tiles")
    ap.add_argument("--experiments", action="store_true", help="Run offline detector approach sweeps")
    ap.add_argument("--top-methods", type=int, default=10, help="Top methods to print for sweeps")
    ap.add_argument(
        "--zoom-tp-consistency",
        action="store_true",
        help="Analyze TP/yellow differences across zoom levels (x1/x2 against x4 baseline)",
    )
    ap.add_argument(
        "--sync-gold-only",
        action="store_true",
        help="When used with --zoom-tp-consistency, evaluate only samples tagged sync_gold",
    )
    args = ap.parse_args()

    rows = load_samples(args.data)
    if not rows:
        print(f"[ERR] No sample JSON files found in: {args.data}")
        return 1

    baseline_report(rows, details=args.details, top_n=max(1, int(args.top)))

    if args.experiments:
        run_experiments(rows, data_dir=args.data, top_methods=args.top_methods, details=args.details)
    if args.zoom_tp_consistency:
        zoom_tp_consistency_report(rows, sync_gold_only=bool(args.sync_gold_only), top_n=max(1, int(args.top)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
