# bg_preview.py
# Shows the background-captured (PrintWindow) client frame in an OpenCV window.
# Run: python bg_preview.py

import time
import cv2
import win32gui
from bg_capture import BackgroundFrameGrabber

try:
    from choose_client_gui import choose_capture_window
    PICK_HWND = True
except Exception:
    PICK_HWND = False


def get_hwnd():
    if PICK_HWND:
        return choose_capture_window()
    return win32gui.GetForegroundWindow()


def main():
    hwnd = get_hwnd()
    title = win32gui.GetWindowText(hwnd)
    print(f"HWND={hwnd} Title='{title}'")

    bg = BackgroundFrameGrabber(hwnd, max_fps=90)

    cv2.namedWindow("bg_capture (client)", cv2.WINDOW_NORMAL)

    last = time.perf_counter()
    frames = 0
    fps = 0.0

    while True:
        ok = bg.update()
        if ok and bg.frame_bgr is not None:
            frame = bg.frame_bgr

            # FPS counter
            frames += 1
            now = time.perf_counter()
            if now - last >= 0.5:
                fps = frames / (now - last)
                frames = 0
                last = now

            overlay = frame.copy()
            cv2.putText(
                overlay,
                f"bg fps: {fps:.1f}  size: {overlay.shape[1]}x{overlay.shape[0]}",
                (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.imshow("bg_capture (client)", overlay)
        else:
            # If capture fails, show a black frame
            blank = 255 * (0 * 1)  # no-op to avoid extra deps

        key = cv2.waitKey(1) & 0xFF
        if key == 27 or key == ord("q"):  # ESC or q
            break
        if key == ord("r"):  # force refresh
            bg.update(force=True)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
