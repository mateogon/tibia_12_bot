"""
Print detailed tile-by-tile diff for one unwalkable sample JSON.

Example:
  python tools/report_unwalkable_sample.py --sample training_data/unwalkable_samples/20260303_195923_123729.json
"""

from __future__ import annotations

import argparse
import json
from typing import Iterable, List, Set, Tuple


Tile = Tuple[int, int]


def pairs_to_set(pairs: Iterable[Iterable[int]]) -> Set[Tile]:
    out: Set[Tile] = set()
    for p in pairs or []:
        if isinstance(p, (list, tuple)) and len(p) == 2:
            r, c = int(p[0]), int(p[1])
            if 0 <= r < 11 and 0 <= c < 15:
                out.add((r, c))
    return out


def fmt_tiles(tiles: Set[Tile], limit: int) -> str:
    seq: List[Tile] = sorted(list(tiles))
    if len(seq) <= limit:
        return str(seq)
    return str(seq[:limit]) + f" ... (+{len(seq)-limit} more)"


def main() -> int:
    ap = argparse.ArgumentParser(description="Show detailed unwalkable diff for one sample.")
    ap.add_argument("--sample", required=True, help="Path to one sample JSON")
    ap.add_argument("--limit", type=int, default=60, help="Max tiles listed per category")
    args = ap.parse_args()

    with open(args.sample, "r", encoding="utf-8") as f:
        d = json.load(f)

    truth = pairs_to_set((d.get("labels") or {}).get("unwalkable", []))
    auto = pairs_to_set((d.get("auto") or {}).get("unwalkable", []))
    coll = pairs_to_set((d.get("auto") or {}).get("collision_unwalkable", []))
    zoom = int(d.get("zoom_level") or d.get("map_scale") or 0)

    print(f"Sample: {args.sample}")
    print(f"Zoom: {zoom}x")
    print(f"Truth count: {len(truth)}")
    print(f"Auto count: {len(auto)}")
    print(f"Collision count: {len(coll)}")

    auto_tp = auto & truth
    auto_fp = auto - truth
    auto_fn = truth - auto
    coll_tp = coll & truth
    coll_fp = coll - truth
    coll_fn = truth - coll

    print("\nAUTO")
    print(f"  TP={len(auto_tp)} FP={len(auto_fp)} FN={len(auto_fn)}")
    print(f"  FP tiles: {fmt_tiles(auto_fp, args.limit)}")
    print(f"  FN tiles: {fmt_tiles(auto_fn, args.limit)}")

    print("\nCOLLISION")
    print(f"  TP={len(coll_tp)} FP={len(coll_fp)} FN={len(coll_fn)}")
    print(f"  FP tiles: {fmt_tiles(coll_fp, args.limit)}")
    print(f"  FN tiles: {fmt_tiles(coll_fn, args.limit)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

