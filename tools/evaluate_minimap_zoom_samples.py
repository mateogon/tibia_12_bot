"""
Evaluate minimap zoom detection against manually labeled zoom samples.

Primary dataset:
  training_data/minimap_zoom_samples/*.json

Optional extra dataset:
  training_data/minimap_zoom_sets/*/metadata.json

The script sweeps detector variants and reports best methods overall,
by zoom label, and by black-ratio bucket.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys
import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.config.constants import BotConstants


@dataclass
class Sample:
    name: str
    image_path: str
    manual_zoom: int
    runtime_detected_zoom: Optional[int]
    black_ratio_meta: Optional[float]
    terrain_ratio_meta: Optional[float]
    sync_gold: bool
    source: str
    session: str
    ts: Optional[datetime]


@dataclass
class MethodScore:
    n: int = 0
    correct: int = 0
    by_zoom_total: Dict[int, int] = None
    by_zoom_correct: Dict[int, int] = None

    def __post_init__(self):
        if self.by_zoom_total is None:
            self.by_zoom_total = {1: 0, 2: 0, 4: 0}
        if self.by_zoom_correct is None:
            self.by_zoom_correct = {1: 0, 2: 0, 4: 0}

    def add(self, pred: int, truth: int):
        self.n += 1
        self.by_zoom_total[truth] += 1
        ok = int(pred == truth)
        self.correct += ok
        self.by_zoom_correct[truth] += ok

    @property
    def acc(self) -> float:
        return (self.correct / self.n) if self.n else 0.0


TERRAIN_BGR = np.array(BotConstants.OBSTACLES + BotConstants.WALKABLE, dtype=np.uint8)
TERRAIN_CODES = (
    (TERRAIN_BGR[:, 0].astype(np.uint32) << 16)
    | (TERRAIN_BGR[:, 1].astype(np.uint32) << 8)
    | TERRAIN_BGR[:, 2].astype(np.uint32)
)


def _parse_ts_from_name(name: str) -> Optional[datetime]:
    stem = os.path.splitext(os.path.basename(name))[0]
    parts = stem.split("_")
    if len(parts) < 3:
        return None
    key = f"{parts[0]}_{parts[1]}_{parts[2]}"
    try:
        return datetime.strptime(key, "%Y%m%d_%H%M%S_%f")
    except Exception:
        return None


def load_zoom_samples(samples_dir: str, sync_gold_only: bool) -> List[Sample]:
    rows: List[Sample] = []
    for jp in sorted(glob.glob(os.path.join(samples_dir, "*.json"))):
        try:
            d = json.load(open(jp, "r", encoding="utf-8"))
        except Exception:
            continue
        z = int(d.get("manual_zoom_level", 0) or 0)
        if z not in (1, 2, 4):
            continue
        sync_gold = bool(d.get("sync_gold") or d.get("quality_tag") == "sync_gold")
        if sync_gold_only and not sync_gold:
            continue
        img_name = d.get("image_file")
        if not img_name:
            continue
        img_path = os.path.join(samples_dir, img_name)
        if not os.path.isfile(img_path):
            continue
        rows.append(
            Sample(
                name=os.path.basename(jp),
                image_path=img_path,
                manual_zoom=z,
                runtime_detected_zoom=int(d.get("detected_zoom_level")) if d.get("detected_zoom_level") in (1, 2, 4) else None,
                black_ratio_meta=float(d.get("black_ratio")) if d.get("black_ratio") is not None else None,
                terrain_ratio_meta=float(d.get("terrain_ratio")) if d.get("terrain_ratio") is not None else None,
                sync_gold=sync_gold,
                source="zoom_samples",
                session=os.path.basename(samples_dir),
                ts=_parse_ts_from_name(os.path.basename(jp)),
            )
        )
    return rows


def load_zoom_sets(sets_root: str, sync_gold_only: bool) -> List[Sample]:
    rows: List[Sample] = []
    for mp in sorted(glob.glob(os.path.join(sets_root, "*", "metadata.json"))):
        session_dir = os.path.dirname(mp)
        session_name = os.path.basename(session_dir)
        try:
            d = json.load(open(mp, "r", encoding="utf-8"))
        except Exception:
            continue
        # zoom sets currently do not carry sync_gold. Keep only when filter disabled.
        if sync_gold_only:
            continue
        scales = d.get("scales") or {}
        for sk, info in scales.items():
            try:
                z = int(sk)
            except Exception:
                continue
            if z not in (1, 2, 4):
                continue
            frame = info.get("frame") or f"zoom_x{z}.png"
            img_path = os.path.join(session_dir, frame)
            if not os.path.isfile(img_path):
                continue
            rows.append(
                Sample(
                    name=f"{session_name}:{frame}",
                    image_path=img_path,
                    manual_zoom=z,
                    runtime_detected_zoom=None,
                    black_ratio_meta=None,
                    terrain_ratio_meta=None,
                    sync_gold=False,
                    source="zoom_set",
                    session=session_name,
                    ts=None,
                )
            )
    return rows


def _extract_strips(map_img: np.ndarray) -> List[np.ndarray]:
    mh, mw = map_img.shape[:2]
    cx, cy = mw // 2, mh // 2
    x_start, x_end = max(0, cx - 90), min(mw, cx + 90)
    y_start, y_end = max(0, cy - 60), min(mh, cy + 60)
    return [
        map_img[np.clip(cy - 40, 0, mh - 1), x_start:x_end],
        map_img[np.clip(cy + 40, 0, mh - 1), x_start:x_end],
        map_img[y_start:y_end, np.clip(cx + 45, 0, mw - 1)].reshape(-1, 3),
        map_img[y_start:y_end, np.clip(cx - 45, 0, mw - 1)].reshape(-1, 3),
    ]


def _dist_terrain_vec(strips: Sequence[np.ndarray]) -> List[int]:
    distances: List[int] = []
    for strip in strips:
        if strip.size == 0 or len(strip) < 3:
            continue
        codes = (
            (strip[:, 0].astype(np.uint32) << 16)
            | (strip[:, 1].astype(np.uint32) << 8)
            | strip[:, 2].astype(np.uint32)
        )
        is_terrain = np.isin(codes, TERRAIN_CODES, assume_unique=False)
        changed = np.any(strip[1:] != strip[:-1], axis=1)
        valid = is_terrain[1:] & is_terrain[:-1] & changed
        edge_idx = np.flatnonzero(valid) + 1
        if edge_idx.size < 2:
            continue
        diffs = np.diff(edge_idx)
        diffs = diffs[(diffs >= 1) & (diffs <= 16)]
        if diffs.size:
            distances.extend(diffs.tolist())
    return distances


def _dist_terrain_loop(strips: Sequence[np.ndarray]) -> List[int]:
    distances: List[int] = []
    for strip in strips:
        if strip.size == 0:
            continue
        is_terrain = np.any(np.all(strip[:, None] == TERRAIN_BGR, axis=-1), axis=-1)
        last_idx = -1
        for i in range(1, len(strip)):
            if is_terrain[i] and is_terrain[i - 1]:
                if not np.array_equal(strip[i], strip[i - 1]):
                    if last_idx != -1:
                        d = i - last_idx
                        if 1 <= d <= 16:
                            distances.append(int(d))
                    last_idx = i
    return distances


def _dist_color_edges(strips: Sequence[np.ndarray]) -> List[int]:
    distances: List[int] = []
    for strip in strips:
        if strip.size == 0 or len(strip) < 3:
            continue
        changed = np.any(strip[1:] != strip[:-1], axis=1)
        edge_idx = np.flatnonzero(changed) + 1
        if edge_idx.size < 2:
            continue
        diffs = np.diff(edge_idx)
        diffs = diffs[(diffs >= 1) & (diffs <= 16)]
        if diffs.size:
            distances.extend(diffs.tolist())
    return distances


def _black_ratio(map_img: np.ndarray) -> float:
    m = np.all(map_img <= np.array([8, 8, 8], dtype=np.uint8), axis=-1)
    return float(np.mean(m)) if m.size else 0.0


def _terrain_ratio(map_img: np.ndarray) -> float:
    px = map_img.astype(np.uint8)
    codes = (
        (px[:, :, 0].astype(np.uint32) << 16)
        | (px[:, :, 1].astype(np.uint32) << 8)
        | px[:, :, 2].astype(np.uint32)
    )
    return float(np.mean(np.isin(codes, TERRAIN_CODES, assume_unique=False))) if codes.size else 0.0


def _detect_runtime_current_emulated(map_img: np.ndarray, prev_scale: int) -> int:
    """Emulate current runtime detect_minimap_scale behavior on one frame."""
    try:
        mh, mw = map_img.shape[:2]
        cx, cy = mw // 2, mh // 2
        
        x_start, x_end = max(0, cx - 90), min(mw, cx + 90)
        y_start, y_end = max(0, cy - 60), min(mh, cy + 60)
        strips = [
            map_img[np.clip(cy - 40, 0, mh - 1), x_start:x_end],
            map_img[np.clip(cy + 40, 0, mh - 1), x_start:x_end],
            map_img[y_start:y_end, np.clip(cx + 45, 0, mw - 1)].reshape(-1, 3),
            map_img[y_start:y_end, np.clip(cx - 45, 0, mw - 1)].reshape(-1, 3),
        ]

        def get_color_runs(strips):
            counts = {1:0, 2:0, 4:0}
            for strip in strips:
                if strip.size == 0 or len(strip) < 3: continue
                rows = [strip] if strip.ndim == 2 else strip
                for row in rows:
                    if row.size == 0: continue
                    changed = np.concatenate(([True], np.any(row[1:] != row[:-1], axis=1), [True]))
                    idx = np.flatnonzero(changed)
                    runs = np.diff(idx)
                    for r in runs:
                        if r in counts:
                            counts[r] += 1
            return counts
            
        runs = get_color_runs(strips)
        s1 = runs[1] * 1.2
        s2 = runs[2] * 2.5
        s4 = runs[4] * 3.0
        
        scores = [(1, s1), (2, s2), (4, s4)]
        best_scale, best_score = max(scores, key=lambda kv: kv[1])
        
        if best_score < 20:
            return int(prev_scale)
        return int(best_scale)
        
    except Exception:
        return int(prev_scale)


def _decide_priority(distances: Sequence[int], prev_scale: int, min_edges: int) -> Tuple[int, bool]:
    if len(distances) < int(min_edges):
        return int(prev_scale), False
    counts = collections.Counter(distances)
    if counts[1] > 0 or counts[3] > 0:
        return 1, True
    if counts[2] > 0 or counts[6] > 0:
        return 2, True
    if counts[4] > 0:
        return 4, True
    return int(prev_scale), False


def _decide_majority(
    distances: Sequence[int],
    prev_scale: int,
    min_edges: int,
    req1: int,
    w1: float,
    w2: float,
    w4: float,
) -> Tuple[int, bool]:
    if len(distances) < int(min_edges):
        return int(prev_scale), False
    c = collections.Counter(distances)
    s1 = float(w1) * float(c[1] + c[3])
    s2 = float(w2) * float(c[2] + c[6])
    s4 = float(w4) * float(c[4])
    if int(req1) > 0 and (c[1] + c[3]) < int(req1):
        s1 = -1.0
    scores = [(1, s1), (2, s2), (4, s4)]
    best_scale, best_score = max(scores, key=lambda kv: kv[1])
    if best_score <= 0.0:
        return int(prev_scale), False
    return int(best_scale), True


def _run_method(
    samples: Sequence[Sample],
    features: Dict[str, dict],
    cfg: dict,
    high_black_thr: float,
) -> Tuple[MethodScore, Dict[str, MethodScore], List[Tuple[str, int, int, float]], Dict[Tuple[int, int], int]]:
    score = MethodScore()
    by_bucket = {"low": MethodScore(), "mid": MethodScore(), "high": MethodScore()}
    mismatches: List[Tuple[str, int, int, float]] = []
    confusion: Dict[Tuple[int, int], int] = collections.Counter()

    # Keep sequence behavior by session and timestamp.
    groups: Dict[str, List[Sample]] = collections.defaultdict(list)
    for s in samples:
        groups[s.session].append(s)
    for k in groups:
        groups[k].sort(key=lambda r: (r.ts or datetime.min, r.name))

    for _session, seq in sorted(groups.items()):
        prev = int(cfg.get("prev_init", 2))
        for s in seq:
            f = features[s.name]
            black = float(f["black_ratio"])
            source = str(cfg["source"])
            if cfg.get("black_switch_thr") is not None and black >= float(cfg["black_switch_thr"]):
                source = str(cfg.get("source_high_black", source))

            d = f[source]
            cdist = collections.Counter(d)
            if cfg["decide"] == "priority":
                pred, _ok = _decide_priority(d, prev_scale=prev, min_edges=int(cfg["min_edges"]))
            else:
                req1 = int(cfg.get("req1", 0))
                if cfg.get("black_req1_thr") is not None and black >= float(cfg["black_req1_thr"]):
                    req1 = int(cfg.get("req1_high_black", req1))
                pred, _ok = _decide_majority(
                    d,
                    prev_scale=prev,
                    min_edges=int(cfg["min_edges"]),
                    req1=req1,
                    w1=float(cfg["w1"]),
                    w2=float(cfg["w2"]),
                    w4=float(cfg["w4"]),
                )

            # Optional guardrails to reduce x1 over-prediction and unstable jumps.
            x1_hits = int(cdist[1] + cdist[3])
            x2_hits = int(cdist[2] + cdist[6])
            x4_hits = int(cdist[4])
            if int(cfg.get("gate_x1_min_hits", 0)) > 0 and pred == 1 and x1_hits < int(cfg.get("gate_x1_min_hits", 0)):
                pred = int(prev)
            if int(cfg.get("gate_x2_min_hits", 0)) > 0 and pred == 2 and x2_hits < int(cfg.get("gate_x2_min_hits", 0)):
                pred = int(prev)
            if int(cfg.get("gate_x4_min_hits", 0)) > 0 and pred == 4 and x4_hits < int(cfg.get("gate_x4_min_hits", 0)):
                pred = int(prev)
            if bool(cfg.get("hold_prev_if_weak", False)):
                max_hits = max(x1_hits, x2_hits, x4_hits)
                if max_hits < int(cfg.get("weak_hits_thr", 2)):
                    pred = int(prev)
            if bool(cfg.get("prevent_2_to_1_high_black", False)):
                if int(prev) == 2 and int(pred) == 1 and black >= float(cfg.get("prevent_2_to_1_thr", 0.70)):
                    pred = 2

            prev = int(pred)

            score.add(pred, s.manual_zoom)
            confusion[(int(s.manual_zoom), int(pred))] += 1
            if black < 0.50:
                by_bucket["low"].add(pred, s.manual_zoom)
            elif black < float(high_black_thr):
                by_bucket["mid"].add(pred, s.manual_zoom)
            else:
                by_bucket["high"].add(pred, s.manual_zoom)
            if pred != s.manual_zoom:
                mismatches.append((s.name, int(s.manual_zoom), int(pred), black))

    return score, by_bucket, mismatches, confusion


def _fmt_acc(n_ok: int, n_tot: int) -> str:
    if n_tot <= 0:
        return "n=0 acc=0.000"
    return f"n={n_tot} acc={n_ok/n_tot:.3f}"


def _method_name(cfg: dict) -> str:
    name = f"{cfg['decide']}_{cfg['source']}_m{cfg['min_edges']}"
    if cfg["decide"] == "majority":
        name += f"_r1{cfg.get('req1',0)}_w{cfg['w1']:.1f}-{cfg['w2']:.1f}-{cfg['w4']:.1f}"
    if cfg.get("black_switch_thr") is not None:
        name += f"_bh{cfg['black_switch_thr']:.2f}->{cfg.get('source_high_black')}"
    if cfg.get("black_req1_thr") is not None:
        name += f"_r1h{cfg['black_req1_thr']:.2f}:{cfg.get('req1_high_black',0)}"
    if int(cfg.get("gate_x1_min_hits", 0)) > 0:
        name += f"_gx1{int(cfg.get('gate_x1_min_hits', 0))}"
    if int(cfg.get("gate_x2_min_hits", 0)) > 0:
        name += f"_gx2{int(cfg.get('gate_x2_min_hits', 0))}"
    if int(cfg.get("gate_x4_min_hits", 0)) > 0:
        name += f"_gx4{int(cfg.get('gate_x4_min_hits', 0))}"
    if bool(cfg.get("hold_prev_if_weak", False)):
        name += f"_holdw{int(cfg.get('weak_hits_thr', 2))}"
    if bool(cfg.get("prevent_2_to_1_high_black", False)):
        name += f"_no21b{float(cfg.get('prevent_2_to_1_thr', 0.70)):.2f}"
    return name


def build_method_grid(exhaustive: bool = False) -> List[dict]:
    methods: List[dict] = []

    # Runtime-equivalent baseline.
    methods.append(
        {
            "name": "runtime_equiv",
            "source": "terrain_vec",
            "decide": "priority",
            "min_edges": 3,
            "prev_init": 2,
        }
    )

    for source in ("terrain_vec", "terrain_loop", "color_edges", "combined"):
        for min_edges in (2, 3, 4, 5):
            methods.append(
                {
                    "source": source,
                    "decide": "priority",
                    "min_edges": min_edges,
                    "prev_init": 2,
                }
            )

    for source in ("terrain_vec", "combined", "color_edges"):
        for min_edges in (2, 3, 4, 5):
            for req1 in (0, 2, 3, 4, 5, 6):
                for w1, w2, w4 in ((1.0, 1.0, 1.0), (0.8, 1.0, 1.2), (0.6, 1.0, 1.4)):
                    methods.append(
                        {
                            "source": source,
                            "decide": "majority",
                            "min_edges": min_edges,
                            "req1": req1,
                            "w1": w1,
                            "w2": w2,
                            "w4": w4,
                            "prev_init": 2,
                        }
                    )

    # Focused x1/x2 anti-confusion sweep.
    for req1 in (3, 4, 5, 6, 7):
        for gx1 in (0, 2, 3, 4):
            for holdw in (0, 2, 3):
                methods.append(
                    {
                        "source": "combined",
                        "decide": "majority",
                        "min_edges": 2,
                        "req1": req1,
                        "w1": 0.8,
                        "w2": 1.0,
                        "w4": 1.2,
                        "gate_x1_min_hits": gx1,
                        "hold_prev_if_weak": bool(holdw > 0),
                        "weak_hits_thr": int(max(2, holdw)),
                        "prevent_2_to_1_high_black": True,
                        "prevent_2_to_1_thr": 0.68,
                        "prev_init": 2,
                    }
                )

    # Black-heavy-aware variants.
    for thr in (0.65, 0.72, 0.80, 0.86):
        methods.append(
            {
                "source": "terrain_vec",
                "source_high_black": "combined",
                "black_switch_thr": thr,
                "decide": "priority",
                "min_edges": 3,
                "prev_init": 2,
            }
        )
        for req1_base, req1_hi in ((0, 3), (2, 4), (3, 5)):
            methods.append(
                {
                    "source": "combined",
                    "decide": "majority",
                    "min_edges": 3,
                    "req1": req1_base,
                    "w1": 0.8,
                    "w2": 1.0,
                    "w4": 1.2,
                    "black_req1_thr": thr,
                    "req1_high_black": req1_hi,
                    "prev_init": 2,
                }
                )

    if exhaustive:
        for source in ("combined", "terrain_vec", "color_edges"):
            for min_edges in (1, 2, 3, 4, 5, 6, 7, 8):
                for req1 in (0, 1, 2, 3, 4, 5, 6, 7, 8):
                    for w1 in (0.4, 0.6, 0.8, 1.0, 1.2):
                        for w2 in (0.8, 1.0, 1.2):
                            for w4 in (1.0, 1.2, 1.4, 1.6):
                                methods.append(
                                    {
                                        "source": source,
                                        "decide": "majority",
                                        "min_edges": min_edges,
                                        "req1": req1,
                                        "w1": w1,
                                        "w2": w2,
                                        "w4": w4,
                                        "prev_init": 2,
                                    }
                                )
                                methods.append(
                                    {
                                        "source": source,
                                        "decide": "majority",
                                        "min_edges": min_edges,
                                        "req1": req1,
                                        "w1": w1,
                                        "w2": w2,
                                        "w4": w4,
                                        "gate_x1_min_hits": 2,
                                        "hold_prev_if_weak": True,
                                        "weak_hits_thr": 2,
                                        "prevent_2_to_1_high_black": True,
                                        "prevent_2_to_1_thr": 0.70,
                                        "prev_init": 2,
                                    }
                                )

    out = []
    for m in methods:
        mm = dict(m)
        if "w1" not in mm:
            mm["w1"] = 1.0
            mm["w2"] = 1.0
            mm["w4"] = 1.0
        mm["name"] = mm.get("name") or _method_name(mm)
        out.append(mm)
    return out


def _confusion_from_mismatches(samples: Sequence[Sample]) -> Dict[Tuple[int, int], int]:
    out: Dict[Tuple[int, int], int] = collections.Counter()
    for s in samples:
        if s.runtime_detected_zoom in (1, 2, 4):
            out[(int(s.manual_zoom), int(s.runtime_detected_zoom))] += 1
    return out


def _print_confusion(title: str, conf: Dict[Tuple[int, int], int]) -> None:
    print(title)
    print("      pred:   1    2    4")
    for t in (1, 2, 4):
        a = int(conf.get((t, 1), 0))
        b = int(conf.get((t, 2), 0))
        c = int(conf.get((t, 4), 0))
        print(f"  true {t}: {a:4d} {b:4d} {c:4d}")


def _objective(score: MethodScore, optimize: str, x2_weight: float) -> float:
    z1 = (score.by_zoom_correct[1] / score.by_zoom_total[1]) if score.by_zoom_total[1] else 0.0
    z2 = (score.by_zoom_correct[2] / score.by_zoom_total[2]) if score.by_zoom_total[2] else 0.0
    z4 = (score.by_zoom_correct[4] / score.by_zoom_total[4]) if score.by_zoom_total[4] else 0.0
    if optimize == "overall":
        return score.acc
    if optimize == "balanced":
        return (z1 + z2 + z4) / 3.0
    if optimize == "x2_focus":
        return (z1 + (float(x2_weight) * z2) + z4) / (2.0 + float(x2_weight))
    return score.acc


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate minimap zoom detector on manual zoom samples.")
    ap.add_argument("--samples-dir", default="training_data/minimap_zoom_samples")
    ap.add_argument("--sets-dir", default="training_data/minimap_zoom_sets")
    ap.add_argument("--include-zoom-sets", action="store_true", help="Include labeled images from minimap_zoom_sets metadata.")
    ap.add_argument("--sync-gold-only", action="store_true", help="Use only sync_gold samples.")
    ap.add_argument("--top", type=int, default=20, help="Top methods to print.")
    ap.add_argument("--high-black-thr", type=float, default=0.75, help="Black-ratio threshold for high-black bucket.")
    ap.add_argument("--details", action="store_true", help="Print mismatch details for best method.")
    ap.add_argument(
        "--optimize",
        choices=["overall", "balanced", "x2_focus"],
        default="overall",
        help="Ranking objective for grid-search output.",
    )
    ap.add_argument("--x2-weight", type=float, default=2.5, help="Weight for x2 in --optimize x2_focus.")
    ap.add_argument("--exhaustive", action="store_true", help="Run a very large method grid.")
    ap.add_argument("--min-z1-acc", type=float, default=0.0, help="Filter methods with z1 acc below this.")
    ap.add_argument("--min-z2-acc", type=float, default=0.0, help="Filter methods with z2 acc below this.")
    ap.add_argument("--min-z4-acc", type=float, default=0.0, help="Filter methods with z4 acc below this.")
    ap.add_argument("--min-z1-acc-high-black", type=float, default=0.0, help="Filter methods with high-black z1 acc below this.")
    ap.add_argument("--min-z2-acc-high-black", type=float, default=0.0, help="Filter methods with high-black z2 acc below this.")
    ap.add_argument("--min-z4-acc-high-black", type=float, default=0.0, help="Filter methods with high-black z4 acc below this.")
    ap.add_argument(
        "--eval-runtime-current",
        action="store_true",
        help="Evaluate current runtime detector logic directly on sample images.",
    )
    args = ap.parse_args()

    samples = load_zoom_samples(args.samples_dir, sync_gold_only=bool(args.sync_gold_only))
    if args.include_zoom_sets:
        samples.extend(load_zoom_sets(args.sets_dir, sync_gold_only=bool(args.sync_gold_only)))
    if not samples:
        print("[ERR] No samples found.")
        return 1

    features: Dict[str, dict] = {}
    keep: List[Sample] = []
    for s in samples:
        img = cv2.imread(s.image_path, cv2.IMREAD_COLOR)
        if img is None:
            continue
        strips = _extract_strips(img)
        d_tv = _dist_terrain_vec(strips)
        d_tl = _dist_terrain_loop(strips)
        d_ce = _dist_color_edges(strips)
        features[s.name] = {
            "black_ratio": _black_ratio(img),
            "terrain_ratio": _terrain_ratio(img),
            "terrain_vec": d_tv,
            "terrain_loop": d_tl,
            "color_edges": d_ce,
            "combined": list(d_tv) + list(d_ce),
        }
        keep.append(s)
    samples = keep
    if not samples:
        print("[ERR] No readable sample images.")
        return 1

    methods = build_method_grid(exhaustive=bool(args.exhaustive))
    all_scores = []
    for cfg in methods:
        score, by_bucket, mismatches, confusion = _run_method(samples, features, cfg, high_black_thr=float(args.high_black_thr))
        obj = _objective(score, optimize=str(args.optimize), x2_weight=float(args.x2_weight))
        all_scores.append((cfg, score, by_bucket, mismatches, confusion, obj))

    def zacc(sc: MethodScore, z: int) -> float:
        return (sc.by_zoom_correct[z] / sc.by_zoom_total[z]) if sc.by_zoom_total[z] else 0.0

    filtered = []
    for row in all_scores:
        sc = row[1]
        if zacc(sc, 1) < float(args.min_z1_acc):
            continue
        if zacc(sc, 2) < float(args.min_z2_acc):
            continue
        if zacc(sc, 4) < float(args.min_z4_acc):
            continue
        hi_acc_z1 = zacc(row[2]["high"], 1)
        if hi_acc_z1 < float(args.min_z1_acc_high_black):
            continue
        hi_acc_z2 = zacc(row[2]["high"], 2)
        if hi_acc_z2 < float(args.min_z2_acc_high_black):
            continue
        hi_acc_z4 = zacc(row[2]["high"], 4)
        if hi_acc_z4 < float(args.min_z4_acc_high_black):
            continue
        filtered.append(row)
    ranked = filtered if filtered else all_scores
    ranked.sort(key=lambda x: (x[5], x[1].acc), reverse=True)

    n = len(samples)
    src_counts = collections.Counter(s.source for s in samples)
    print(f"Loaded samples: n={n} sources={dict(src_counts)} sync_gold={sum(1 for s in samples if s.sync_gold)}")

    # Runtime detector accuracy from metadata (when available).
    runtime_tot = 0
    runtime_ok = 0
    for s in samples:
        if s.runtime_detected_zoom in (1, 2, 4):
            runtime_tot += 1
            runtime_ok += int(s.runtime_detected_zoom == s.manual_zoom)
    if runtime_tot:
        print(f"Runtime detected_zoom_level baseline: {_fmt_acc(runtime_ok, runtime_tot)}")
        _print_confusion("Runtime confusion (true x pred):", _confusion_from_mismatches(samples))
    if args.eval_runtime_current:
        rt_score = MethodScore()
        rt_conf = collections.Counter()
        groups: Dict[str, List[Sample]] = collections.defaultdict(list)
        for s in samples:
            groups[s.session].append(s)
        for k in groups:
            groups[k].sort(key=lambda r: (r.ts or datetime.min, r.name))
        for _session, seq in sorted(groups.items()):
            prev = 2
            for s in seq:
                img = cv2.imread(s.image_path, cv2.IMREAD_COLOR)
                if img is None:
                    continue
                pred = int(_detect_runtime_current_emulated(img, prev))
                prev = int(pred)
                rt_score.add(pred, s.manual_zoom)
                rt_conf[(int(s.manual_zoom), int(pred))] += 1
        print(f"Runtime CURRENT emulated baseline: {_fmt_acc(rt_score.correct, rt_score.n)}")
        _print_confusion("Runtime CURRENT confusion (true x pred):", rt_conf)

    print(
        f"\nGrid size={len(all_scores)} filtered={len(filtered)} "
        f"(constraints: z1>={args.min_z1_acc:.2f}, z2>={args.min_z2_acc:.2f}, z4>={args.min_z4_acc:.2f}, "
        f"hi_z1>={args.min_z1_acc_high_black:.2f}, hi_z2>={args.min_z2_acc_high_black:.2f}, hi_z4>={args.min_z4_acc_high_black:.2f})"
    )
    print(f"Top methods (optimize={args.optimize}, x2_weight={args.x2_weight:.2f}):")
    for cfg, score, by_bucket, _m, _conf, obj in ranked[: max(1, int(args.top))]:
        name = cfg["name"]
        z1 = _fmt_acc(score.by_zoom_correct[1], score.by_zoom_total[1])
        z2 = _fmt_acc(score.by_zoom_correct[2], score.by_zoom_total[2])
        z4 = _fmt_acc(score.by_zoom_correct[4], score.by_zoom_total[4])
        hi = by_bucket["high"]
        hi_s = _fmt_acc(hi.correct, hi.n)
        h1 = _fmt_acc(hi.by_zoom_correct[1], hi.by_zoom_total[1])
        h2 = _fmt_acc(hi.by_zoom_correct[2], hi.by_zoom_total[2])
        h4 = _fmt_acc(hi.by_zoom_correct[4], hi.by_zoom_total[4])
        print(
            f"  {name}: n={score.n} acc={score.acc:.3f} obj={obj:.3f} | "
            f"z1={z1} z2={z2} z4={z4} | high_black={hi_s} (z1={h1} z2={h2} z4={h4})"
        )

    # Best by high-black bucket.
    best_hi = max(ranked, key=lambda x: (x[2]["high"].acc, x[2]["high"].n, x[1].acc))
    print(
        "\nBest high-black method: "
        f"{best_hi[0]['name']} "
        f"(n={best_hi[2]['high'].n} acc={best_hi[2]['high'].acc:.3f}, "
        f"overall={best_hi[1].acc:.3f})"
    )

    if args.details and ranked:
        cfg, score, _by_bucket, mism, conf, _obj = ranked[0]
        print(f"\nBest method details: {cfg['name']} overall_acc={score.acc:.3f}")
        _print_confusion("Best method confusion (true x pred):", conf)
        if not mism:
            print("  No mismatches.")
        else:
            print("  Mismatches (sample truth->pred black_ratio):")
            for name, truth, pred, br in mism[:80]:
                print(f"    {name}: {truth}->{pred} black={br:.3f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
