import cv2
import numpy as np
from constants import BotConstants

# --- CONFIGURATION ---
MIN_BAR_WIDTH = 28 
BORDER_MERGE_DIST = 8 
STACK_MERGE_DIST = 18 

OFFSET_MONSTER = 32   
OFFSET_PLAYER  = 46   

def detect_monsters(full_image_bgr):
    """
    Detects monsters using the 'Black Line' method validated by HP color presence.
    """
    # 1. Mask BLACK pixels for the borders
    lower_black = np.array([0, 0, 0])
    upper_black = np.array([15, 15, 15])
    black_mask = cv2.inRange(full_image_bgr, lower_black, upper_black)
    
    # 2. CREATE HP COLOR MASK (The Validator)
    # We use the exact colors from BotConstants
    hp_mask = np.zeros(full_image_bgr.shape[:2], dtype=np.uint8)
    for color_rgb in BotConstants.HP_COLORS:
        # Convert RGB to BGR for OpenCV
        color_bgr = np.array([color_rgb[2], color_rgb[1], color_rgb[0]])
        # Find exact matches for this specific HP color
        temp_mask = cv2.inRange(full_image_bgr, color_bgr, color_bgr)
        hp_mask = cv2.bitwise_or(hp_mask, temp_mask)

    # 3. MORPHOLOGY: The 'Barcode' Filter for black lines
    kernel_line = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 1))
    lines_mask = cv2.morphologyEx(black_mask, cv2.MORPH_OPEN, kernel_line)
    
    # 4. Find Contours
    contours, _ = cv2.findContours(lines_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    lines = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w > MIN_BAR_WIDTH:
            # --- VALIDATION STEP ---
            # Check a small 1-pixel high strip just below/inside the black line
            # If there's NO HP color in this horizontal strip, skip it
            roi_hp = hp_mask[y:y+3, x:x+w] # Look 3 pixels deep to be sure
            if cv2.countNonZero(roi_hp) > 0:
                lines.append((x, y, w, h))

    if not lines:
        return []

    lines.sort(key=lambda b: b[1])
    
    # --- PASS 1: Merge Top/Bottom Borders of a SINGLE bar ---
    unique_bars = []
    processed_indices = set()
    
    for i in range(len(lines)):
        if i in processed_indices: continue
        x1, y1, w1, h1 = lines[i]
        bar_center_x = x1 + w1 // 2
        has_pair = False
        for j in range(i + 1, min(i + 5, len(lines))):
             if j in processed_indices: continue
             x2, y2, w2, h2 = lines[j]
             if abs(y2 - y1) < BORDER_MERGE_DIST and abs(x2 - x1) < 10:
                 processed_indices.add(j)
                 has_pair = True
                 avg_y = (y1 + y2) / 2
                 unique_bars.append({'x': bar_center_x, 'y': avg_y})
                 break
        if not has_pair:
             unique_bars.append({'x': bar_center_x, 'y': y1})
        processed_indices.add(i)

    # --- PASS 2: Merge Vertical Stacks (Health + Mana) ---
    final_points = []
    unique_bars.sort(key=lambda b: b['y'])
    merged_indices = set()
    
    for i in range(len(unique_bars)):
        if i in merged_indices: continue
        bar_a = unique_bars[i]
        found_stack = False
        for j in range(i + 1, min(i + 3, len(unique_bars))):
            if j in merged_indices: continue
            bar_b = unique_bars[j]
            if abs(bar_b['y'] - bar_a['y']) < STACK_MERGE_DIST and abs(bar_b['x'] - bar_a['x']) < 10:
                merged_indices.add(j)
                found_stack = True
                final_points.append((int(bar_a['x']), int(bar_a['y'] + OFFSET_PLAYER)))
                break
        if not found_stack:
            final_points.append((int(bar_a['x']), int(bar_a['y'] + OFFSET_MONSTER)))

    return final_points