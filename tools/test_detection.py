import cv2
import numpy as np
import json
import os
import glob
from math import sqrt

# --- CONFIGURATION ---
DATA_FOLDER = "training_data"
DEBUG_FOLDER = "debug_output"
MATCH_DISTANCE = 25 

# --- TUNING ---
# 1. Bar Width: 31px usually. We accept > 20.
MIN_BAR_WIDTH = 28 

# 2. Border Gap: The top and bottom black lines of ONE bar are ~4px apart.
BORDER_MERGE_DIST = 8 

# 3. Stack Gap: The Health Bar and Mana Bar are ~10-15px apart.
# If two bars are closer than this, we treat them as one player.
STACK_MERGE_DIST = 18 

def detect_health_bars_only(full_image_bgr):
    # 1. Mask BLACK pixels (0-15 tolerance)
    lower_black = np.array([0, 0, 0])
    upper_black = np.array([15, 15, 15])
    mask = cv2.inRange(full_image_bgr, lower_black, upper_black)
    
    # 2. MORPHOLOGY: The 'Barcode' Filter (20x1)
    # Removes text/noise, keeps horizontal lines
    kernel_line = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 1))
    lines_mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_line)
    
    # 3. Find Contours
    contours, _ = cv2.findContours(lines_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Collect raw lines
    lines = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w > MIN_BAR_WIDTH:
            lines.append((x, y, w, h))

    # Sort by Y position for easy merging
    lines.sort(key=lambda b: b[1])
    
    # --- PASS 1: Merge Top/Bottom Borders of a SINGLE bar ---
    unique_bars = []
    processed_indices = set()
    
    for i in range(len(lines)):
        if i in processed_indices: continue
        
        x1, y1, w1, h1 = lines[i]
        bar_center_x = x1 + w1 // 2
        
        # Look ahead for the "bottom border" of this same bar
        has_pair = False
        for j in range(i + 1, min(i + 5, len(lines))):
             if j in processed_indices: continue
             x2, y2, w2, h2 = lines[j]
             
             # Same Bar Check: Vertical gap < 8px, Horizontal align < 10px
             if abs(y2 - y1) < BORDER_MERGE_DIST and abs(x2 - x1) < 10:
                 processed_indices.add(j)
                 has_pair = True
                 
                 # Average the Y to get true bar center
                 avg_y = (y1 + y2) / 2
                 unique_bars.append({'x': bar_center_x, 'y': avg_y})
                 break
        
        if not has_pair:
             # It's a single line (maybe bottom border was faint). Still a bar.
             unique_bars.append({'x': bar_center_x, 'y': y1})
             
        processed_indices.add(i)

    # --- PASS 2: Merge Vertical Stacks (Health + Mana) ---
    # We now have a list of confirmed "Bars". 
    # Check if any two bars are stacked (Player Case).
    
    final_points = []
    # Sort by Y again just to be safe
    unique_bars.sort(key=lambda b: b['y'])
    
    merged_indices = set()
    
    for i in range(len(unique_bars)):
        if i in merged_indices: continue
        
        bar_a = unique_bars[i]
        
        # Look ahead for a "Mana Bar" right below this "Health Bar"
        found_stack = False
        for j in range(i + 1, min(i + 3, len(unique_bars))):
            if j in merged_indices: continue
            
            bar_b = unique_bars[j]
            
            # Stack Check: Vertical gap < 18px, Horizontal align < 10px
            if abs(bar_b['y'] - bar_a['y']) < STACK_MERGE_DIST and abs(bar_b['x'] - bar_a['x']) < 10:
                merged_indices.add(j)
                found_stack = True
                # We found a stack. We only keep the TOP one (Health Bar)
                # shifting it up slightly to target the Name
                final_points.append((int(bar_a['x']), int(bar_a['y'] - 12)))
                break
        
        if not found_stack:
            # It's a regular monster (1 bar)
            final_points.append((int(bar_a['x']), int(bar_a['y'] - 12)))

    return final_points, []

def draw_debug_image(img, gt, preds, matches):
    vis = img.copy()
    for (gx, gy) in gt: cv2.circle(vis, (gx, gy), 6, (0, 255, 0), 2) 
    for (px, py) in preds: cv2.circle(vis, (px, py), 3, (0, 0, 255), -1) 
    for (gx, gy, px, py) in matches: cv2.line(vis, (gx, gy), (px, py), (0, 255, 255), 2) 
    return vis

def main():
    if not os.path.exists(DEBUG_FOLDER): os.makedirs(DEBUG_FOLDER)
    files = sorted(glob.glob(os.path.join(DATA_FOLDER, "*.json")))
    if not files: return

    print(f"Testing BLACK LINES with PLAYER STACK FIX...")
    total_tp, total_fp, total_fn = 0, 0, 0

    for file_path in files:
        with open(file_path, 'r') as f: data = json.load(f)
        img_path = os.path.join(DATA_FOLDER, data.get("image_file", ""))
        image = cv2.imread(img_path)
        if image is None: continue

        gt_coords = data.get("coordinates", [])
        predictions, _ = detect_health_bars_only(image)
        
        matches = []
        gt_matched = [False] * len(gt_coords)
        pred_matched = [False] * len(predictions)
        
        for p_idx, (px, py) in enumerate(predictions):
            best_dist = float('inf')
            best_gt_idx = -1
            for g_idx, (gx, gy) in enumerate(gt_coords):
                if gt_matched[g_idx]: continue
                d = sqrt((px - gx)**2 + (py - gy)**2)
                if d < best_dist:
                    best_dist = d
                    best_gt_idx = g_idx
            
            if best_dist <= MATCH_DISTANCE:
                pred_matched[p_idx] = True
                gt_matched[best_gt_idx] = True
                matches.append((gt_coords[best_gt_idx][0], gt_coords[best_gt_idx][1], px, py))

        tp = sum(gt_matched)
        fn = len(gt_coords) - tp
        fp = len(predictions) - sum(pred_matched)
        total_tp += tp; total_fp += fp; total_fn += fn
        
        debug_img = draw_debug_image(image, gt_coords, predictions, matches)
        cv2.imwrite(os.path.join(DEBUG_FOLDER, os.path.basename(img_path)), debug_img)

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) else 0

    print("-" * 30)
    print(f"Precision: {precision:.2%}")
    print(f"Recall:    {recall:.2%}")
    print(f"F1 Score:  {f1:.2%}")
    print(f"Check '{DEBUG_FOLDER}' to verify alignment.")

if __name__ == "__main__":
    main()