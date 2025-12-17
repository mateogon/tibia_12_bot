import cv2
import numpy as np

# --- CONFIGURATION ---
# Minimum width for a black line to be considered a health bar (Game standard is ~31px)
MIN_BAR_WIDTH = 20 

# Vertical distance to merge the top & bottom borders of the SAME bar
BORDER_MERGE_DIST = 8 

# Vertical distance to merge a Health Bar + Mana Bar (Player detection)
STACK_MERGE_DIST = 18 

# Offset to move from the Bar Center UP to the Name Center
# We determined -12 was good, but you mentioned it was slightly off. 
# -14 might center it better on the text.
NAME_OFFSET_Y = 14

def detect_monsters(full_image_bgr):
    """
    Detects monsters by scanning for the specific 31x1 pixel black borders 
    of their health bars. This ignores name colors completely.
    
    Returns: list of (x, y) tuples representing the center of the monster name.
    """
    # 1. Mask BLACK pixels (The border)
    # We use a strict tolerance (0-15) to catch the pure black border
    lower_black = np.array([0, 0, 0])
    upper_black = np.array([15, 15, 15])
    mask = cv2.inRange(full_image_bgr, lower_black, upper_black)
    
    # 2. MORPHOLOGY: The 'Barcode' Filter
    # Kernel: 20px wide, 1px tall. 
    # This deletes text, noise, and sprites, preserving ONLY horizontal lines.
    kernel_line = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 1))
    lines_mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_line)
    
    # 3. Find Contours of these lines
    contours, _ = cv2.findContours(lines_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Collect raw lines
    lines = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w > MIN_BAR_WIDTH:
            lines.append((x, y, w, h))

    if not lines:
        return []

    # Sort by Y position to enable linear merging
    lines.sort(key=lambda b: b[1])
    
    # --- PASS 1: Merge Top/Bottom Borders of a SINGLE bar ---
    unique_bars = []
    processed_indices = set()
    
    for i in range(len(lines)):
        if i in processed_indices: continue
        
        x1, y1, w1, h1 = lines[i]
        bar_center_x = x1 + w1 // 2
        
        # Look ahead for the "bottom border" pair
        has_pair = False
        for j in range(i + 1, min(i + 5, len(lines))):
             if j in processed_indices: continue
             x2, y2, w2, h2 = lines[j]
             
             # Check if this is the bottom border of the same bar
             # (Close in Y, aligned in X)
             if abs(y2 - y1) < BORDER_MERGE_DIST and abs(x2 - x1) < 10:
                 processed_indices.add(j)
                 has_pair = True
                 
                 # Use average Y for precision
                 avg_y = (y1 + y2) / 2
                 unique_bars.append({'x': bar_center_x, 'y': avg_y})
                 break
        
        if not has_pair:
             # Single line detected (still valid)
             unique_bars.append({'x': bar_center_x, 'y': y1})
             
        processed_indices.add(i)

    # --- PASS 2: Merge Vertical Stacks (Health + Mana) ---
    # Merge detecting the player (who has 2 bars) into a single target
    final_points = []
    
    # Sort again by Y for the stack check
    unique_bars.sort(key=lambda b: b['y'])
    merged_indices = set()
    
    for i in range(len(unique_bars)):
        if i in merged_indices: continue
        
        bar_a = unique_bars[i]
        
        found_stack = False
        # Look ahead for a "Mana Bar" right below
        for j in range(i + 1, min(i + 3, len(unique_bars))):
            if j in merged_indices: continue
            bar_b = unique_bars[j]
            
            # Check for stack: Close vertically, aligned horizontally
            if abs(bar_b['y'] - bar_a['y']) < STACK_MERGE_DIST and abs(bar_b['x'] - bar_a['x']) < 10:
                merged_indices.add(j)
                found_stack = True
                
                # Found a stack. We target the TOP bar (Health) and shift up to Name.
                final_points.append((int(bar_a['x']), int(bar_a['y'] - NAME_OFFSET_Y)))
                break
        
        if not found_stack:
            # Regular monster
            final_points.append((int(bar_a['x']), int(bar_a['y'] - NAME_OFFSET_Y)))

    return final_points