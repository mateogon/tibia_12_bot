import json
import os
import glob
import shutil

# --- CONFIGURATION ---
TILE_SIZE = 72

# X: Same as before (detected center -> name center seems aligned horizontally)
# 72 / 4 = 18px
OFFSET_X = int(TILE_SIZE / 4)      

# Y: INCREASED based on your feedback.
# Previous was 36px. You said it was 1/3 tile (24px) too low.
# 36 + 24 = 60px total adjustment.
OFFSET_Y = 60  

DATA_FOLDER = "training_data"
BACKUP_FOLDER = os.path.join(DATA_FOLDER, "backup_original_coords")

def restore_backup():
    """Restores files from backup to ensure we work on fresh data."""
    if os.path.exists(BACKUP_FOLDER):
        print(f"[RESET] Restoring original files from {BACKUP_FOLDER}...")
        backup_files = glob.glob(os.path.join(BACKUP_FOLDER, "*.json"))
        for b_file in backup_files:
            shutil.copy2(b_file, DATA_FOLDER)
        print(f"[RESET] Restored {len(backup_files)} files. Ready to apply new fix.\n")
        return True
    return False

def main():
    # 1. Try to reset to original state first
    has_backup = restore_backup()

    # 2. If no backup exists, create one now (first run scenario)
    if not has_backup:
        if not os.path.exists(BACKUP_FOLDER):
            os.makedirs(BACKUP_FOLDER)
            print(f"[BACKUP] Creating initial backup in {BACKUP_FOLDER}...")

    # 3. Process files
    search_path = os.path.join(os.getcwd(), DATA_FOLDER, "*.json")
    files = glob.glob(search_path)
    
    if not files:
        print("No JSON files found.")
        return

    print(f"Applying Correction: X -{OFFSET_X}px | Y -{OFFSET_Y}px")

    count = 0
    for file_path in files:
        filename = os.path.basename(file_path)
        
        # Create backup if we didn't just restore (safety net)
        if not has_backup:
            backup_path = os.path.join(BACKUP_FOLDER, filename)
            if not os.path.exists(backup_path):
                shutil.copy2(file_path, backup_path)

        # Load
        with open(file_path, 'r') as f:
            data = json.load(f)

        original_coords = data.get("coordinates", [])
        new_coords = []

        # Apply Offset
        for x, y in original_coords:
            new_x = x - OFFSET_X
            new_y = y - OFFSET_Y
            
            # Clamp to 0
            new_x = max(0, new_x)
            new_y = max(0, new_y)
            
            new_coords.append([new_x, new_y])

        # Save
        data["coordinates"] = new_coords
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
            
        count += 1

    print(f"Done! Updated {count} files.")
    print("Check 'annotation_tool.py' again.")

if __name__ == "__main__":
    main()