import cv2
import numpy as np
import json
import os
import glob
from collections import Counter

DATA_FOLDER = "training_data"

def main():
    files = glob.glob(os.path.join(DATA_FOLDER, "*.json"))
    if not files:
        print("No data found.")
        return

    print(f"Scanning {len(files)} images for monster colors...")
    
    # Counter for all colors found under the green dots
    color_counter = Counter()

    for file_path in files:
        with open(file_path, 'r') as f:
            data = json.load(f)
            
        img_path = os.path.join(DATA_FOLDER, data.get("image_file", ""))
        image = cv2.imread(img_path)
        if image is None: continue

        coords = data.get("coordinates", [])
        
        for (cx, cy) in coords:
            # We look at a small 3x3 window around the center to catch the bar/name
            # Careful not to go out of bounds
            y_start, y_end = max(0, cy-1), min(image.shape[0], cy+2)
            x_start, x_end = max(0, cx-1), min(image.shape[1], cx+2)
            
            roi = image[y_start:y_end, x_start:x_end]
            
            # Reshape to list of pixels
            pixels = roi.reshape(-1, 3)
            
            for p in pixels:
                # Convert numpy array to tuple (B, G, R) so it can be hashed
                b, g, r = int(p[0]), int(p[1]), int(p[2])
                
                # Filter out pure black/dark background to reduce noise
                if b < 20 and g < 20 and r < 20: continue
                
                color_counter[(b, g, r)] += 1

    print("\n--- TOP 20 DETECTED COLORS (BGR) ---")
    print("Copy these into your HP_COLORS list:\n")
    
    most_common = color_counter.most_common(20)
    
    # Format for Python list
    print("NEW_HP_COLORS = [")
    for color, count in most_common:
        print(f"    {color}, # Count: {count}")
    print("]")
    
    print("\n-----------------------------------")
    print("Note: OpenCV uses (Blue, Green, Red).")

if __name__ == "__main__":
    main()