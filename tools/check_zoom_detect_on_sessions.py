import os
import cv2

from benchmark_minimap import detect_scale_terrain_vec


SESSIONS = [
    "training_data/minimap_zoom_sets/20260302_171107",
    "training_data/minimap_zoom_sets/20260302_171127",
    "training_data/minimap_zoom_sets/20260302_171212",
]


def main():
    for session in SESSIONS:
        print(f"\nSESSION {session}")
        prev = 4
        for zoom in (1, 2, 4):
            path = os.path.join(session, f"zoom_x{zoom}.png")
            img = cv2.imread(path)
            if img is None:
                print(f"  zoom_x{zoom}: missing image ({path})")
                continue
            detected, confident = detect_scale_terrain_vec(img, prev)
            print(
                f"  zoom_x{zoom}: detect={detected} confident={confident} prev={prev}"
            )
            prev = detected


if __name__ == "__main__":
    main()
