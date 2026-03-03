import argparse
import glob
import json
import os
from math import sqrt

import cv2

from src.bot.vision.detect_monsters import detect_monsters


def match_points(gt, pred, max_dist):
    gt_used = [False] * len(gt)
    pred_used = [False] * len(pred)
    matches = []

    for pi, (px, py) in enumerate(pred):
        best_gi = -1
        best_d = float("inf")
        for gi, (gx, gy) in enumerate(gt):
            if gt_used[gi]:
                continue
            d = sqrt((px - gx) ** 2 + (py - gy) ** 2)
            if d < best_d:
                best_d = d
                best_gi = gi
        if best_gi >= 0 and best_d <= max_dist:
            gt_used[best_gi] = True
            pred_used[pi] = True
            matches.append((best_gi, pi))

    tp = len(matches)
    fp = len(pred) - tp
    fn = len(gt) - tp
    return tp, fp, fn


def compute_metrics(total_tp, total_fp, total_fn):
    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def load_samples(data_dir):
    samples = []
    for jpath in sorted(glob.glob(os.path.join(data_dir, "*.json"))):
        with open(jpath, "r", encoding="utf-8") as f:
            meta = json.load(f)
        img_name = meta.get("image_file")
        if not img_name:
            continue
        ipath = os.path.join(data_dir, img_name)
        if not os.path.exists(ipath):
            continue
        img = cv2.imread(ipath)
        if img is None:
            continue
        gt = [tuple(map(int, p)) for p in meta.get("coordinates", [])]
        samples.append((os.path.basename(jpath), img, gt))
    return samples


def evaluate(samples, max_dist, dx=0, dy=0):
    total_tp = total_fp = total_fn = 0
    for _name, img, gt in samples:
        pred = detect_monsters(img, return_debug=False)
        shifted = [(int(x + dx), int(y + dy)) for (x, y) in pred]
        tp, fp, fn = match_points(gt, shifted, max_dist=max_dist)
        total_tp += tp
        total_fp += fp
        total_fn += fn
    return total_tp, total_fp, total_fn, compute_metrics(total_tp, total_fp, total_fn)


def evaluate_as_name_labels(samples, max_dist, dx=0, dy=0, name_y_shifts=(-44, -58)):
    """
    Convert feet detections to approximate name coordinates.
    For each prediction, try all provided Y shifts and keep whichever can match best.
    """
    total_tp = total_fp = total_fn = 0
    for _name, img, gt in samples:
        pred = detect_monsters(img, return_debug=False)
        gt_used = [False] * len(gt)
        tp = 0
        for (px, py) in pred:
            best_gi = -1
            best_d = float("inf")
            for ys in name_y_shifts:
                qx = int(px + dx)
                qy = int(py + ys + dy)
                for gi, (gx, gy) in enumerate(gt):
                    if gt_used[gi]:
                        continue
                    d = sqrt((qx - gx) ** 2 + (qy - gy) ** 2)
                    if d < best_d:
                        best_d = d
                        best_gi = gi
            if best_gi >= 0 and best_d <= max_dist:
                gt_used[best_gi] = True
                tp += 1
        fp = len(pred) - tp
        fn = len(gt) - tp
        total_tp += tp
        total_fp += fp
        total_fn += fn
    return total_tp, total_fp, total_fn, compute_metrics(total_tp, total_fp, total_fn)


def main():
    ap = argparse.ArgumentParser(description="Evaluate current monster detector against training_data labels.")
    ap.add_argument("--data", default="training_data", help="Directory with *.png + *.json labels")
    ap.add_argument("--match-distance", type=float, default=25.0, help="Pixel distance threshold for a match")
    ap.add_argument("--dx", type=int, default=0, help="Apply x offset to detector output before matching")
    ap.add_argument("--dy", type=int, default=0, help="Apply y offset to detector output before matching")
    ap.add_argument("--sweep-offset", action="store_true", help="Sweep dx/dy in [-60..60] and print best F1")
    ap.add_argument("--radius", type=int, default=60, help="Sweep radius for dx/dy when --sweep-offset is set")
    ap.add_argument("--label-space", choices=("feet", "name"), default="feet", help="Ground-truth label space")
    args = ap.parse_args()

    samples = load_samples(args.data)
    if not samples:
        print(f"No valid labeled samples found in '{args.data}'.")
        raise SystemExit(1)

    print(f"Samples: {len(samples)} from {args.data}")
    eval_fn = evaluate_as_name_labels if args.label_space == "name" else evaluate

    if args.sweep_offset:
        best = None
        r = max(0, int(args.radius))
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                tp, fp, fn, (p, rc, f1) = eval_fn(samples, args.match_distance, dx=dx, dy=dy)
                cand = (f1, p, rc, dx, dy, tp, fp, fn)
                if best is None or cand > best:
                    best = cand
        f1, p, rc, dx, dy, tp, fp, fn = best
        print(f"[BEST] dx={dx} dy={dy} | TP={tp} FP={fp} FN={fn} | P={p:.3f} R={rc:.3f} F1={f1:.3f}")
    else:
        tp, fp, fn, (p, rc, f1) = eval_fn(samples, args.match_distance, dx=args.dx, dy=args.dy)
        print(f"dx={args.dx} dy={args.dy} | TP={tp} FP={fp} FN={fn} | P={p:.3f} R={rc:.3f} F1={f1:.3f}")


if __name__ == "__main__":
    main()
