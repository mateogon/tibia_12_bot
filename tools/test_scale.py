import cv2
import numpy as np
import time
import pyautogui
from collections import Counter
import math

# --- STEP 1: CONFIGURE YOUR REGION ---
# Update these to match roughly where your minimap is.
# (Left, Top, Width, Height)
MINIMAP_REGION = (1760, 30, 110, 110) 

def get_gcd(numbers):
    """Finds the Greatest Common Divisor of a list of numbers."""
    if not numbers: return 1
    result = numbers[0]
    for n in numbers[1:]:
        result = math.gcd(result, n)
    return result

def algo_gcd_runs(img, name):
    """
    Scans the image for horizontal color runs.
    Calculates the GCD of these run lengths.
    """
    # 1. Convert to Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 2. Crop center (avoiding borders)
    h, w = gray.shape
    roi = gray[20:h-20, 20:w-20]
    
    run_lengths = []
    
    # 3. Scan a few rows
    for y in range(0, roi.shape[0], 5): # Scan every 5th row
        curr_run = 1
        for x in range(1, roi.shape[1]):
            if roi[y, x] == roi[y, x-1]:
                curr_run += 1
            else:
                # We only care about runs that are likely tiles (up to 32px)
                # And ignore 1px noise if we suspect we are in zoom 2/4
                if curr_run < 32:
                    run_lengths.append(curr_run)
                curr_run = 1
                
    if not run_lengths:
        print(f"  [{name}] FAIL: No color changes found. Is the image black?")
        return 1

    # 4. Frequency Analysis
    # We take the most common run lengths to filter out noise
    counts = Counter(run_lengths)
    common_runs = [k for k, v in counts.most_common(5)]
    
    # 5. Calculate GCD of the most common runs
    # If we have runs of length 4, 8, 12 -> GCD is 4 (Zoom 4)
    # If we have runs of length 2, 4, 6 -> GCD is 2 (Zoom 2)
    final_gcd = get_gcd(common_runs)
    
    print(f"  [{name}] Common Runs: {common_runs} -> Detected Scale: {final_gcd}")
    return final_gcd

def run_test():
    print("--- DIAGNOSTIC SCALE TEST ---")
    print(f"Target Region: {MINIMAP_REGION}")
    
    zooms = ["ZOOM_MAX_1px", "ZOOM_MID_2px", "ZOOM_OUT_4px"]
    
    for z_name in zooms:
        input(f"\nSet Tibia to {z_name} and press ENTER...")
        
        # Capture
        screenshot = pyautogui.screenshot(region=MINIMAP_REGION)
        img_bgr = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        
        # SAVE THE IMAGE FOR DEBUGGING
        filename = f"debug_{z_name}.png"
        cv2.imwrite(filename, img_bgr)
        print(f"  > Saved {filename}. CHECK THIS IMAGE!")
        
        # Analyze
        algo_gcd_runs(img_bgr, z_name)

if __name__ == "__main__":
    run_test()