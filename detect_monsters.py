import cv2
import numpy as np

# --- CONFIGURATION (Your Best Settings) ---
MIN_BAR_WIDTH = 28 
BORDER_MERGE_DIST = 8 
STACK_MERGE_DIST = 18 

# --- TARGETING OFFSETS (Distance from Health Bar DOWN to Feet) ---
# Positive = Move DOWN towards the feet.
OFFSET_MONSTER = 32   # For single-bar monsters
OFFSET_PLAYER  = 46   # For double-bar player (Health is higher up)

def detect_monsters(full_image_bgr):
    """
    Detects monsters using the 'Black Line' method with Min Width 28.
    Returns coordinates targeted at the monster's FEET.
    """
    # 1. Mask BLACK pixels (0-15 tolerance)
    lower_black = np.array([0, 0, 0])
    upper_black = np.array([15, 15, 15])
    mask = cv2.inRange(full_image_bgr, lower_black, upper_black)
    
    # 2. MORPHOLOGY: The 'Barcode' Filter (20x1)
    kernel_line = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 1))
    lines_mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_line)
    
    # 3. Find Contours
    contours, _ = cv2.findContours(lines_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Collect raw lines (Your tuned width check)
    lines = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w > MIN_BAR_WIDTH:
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
            
            # Stack Check (Player)
            if abs(bar_b['y'] - bar_a['y']) < STACK_MERGE_DIST and abs(bar_b['x'] - bar_a['x']) < 10:
                merged_indices.add(j)
                found_stack = True
                
                # PLAYER: 2 Bars found. Target the top one + Large Offset
                final_points.append((int(bar_a['x']), int(bar_a['y'] + OFFSET_PLAYER)))
                break
        
        if not found_stack:
            # MONSTER: 1 Bar found. Target + Standard Offset
            final_points.append((int(bar_a['x']), int(bar_a['y'] + OFFSET_MONSTER)))

    return final_points