# pixel_bench_split.py
# Measures:
# - bg_capture update() time (PrintWindow + crop)
# - bg_cached pixel sampling time (NO update)
# - screen_dc pixel time
# And agreement when window is visible.

import time
import random
import statistics as stats
import win32gui
import win32ui

from bg_capture import BackgroundFrameGrabber

try:
    from choose_client_gui import choose_capture_window
    PICK_HWND = True
except Exception:
    PICK_HWND = False


class ScreenPixelSampler:
    def __init__(self):
        self._hdc = win32gui.GetDC(0)
        self._dc = win32ui.CreateDCFromHandle(self._hdc)

    def close(self):
        try:
            self._dc.DeleteDC()
        finally:
            win32gui.ReleaseDC(0, self._hdc)

    def get_rgb_client(self, hwnd, cx, cy):
        sx, sy = win32gui.ClientToScreen(hwnd, (cx, cy))
        color = self._dc.GetPixel(sx, sy)
        r = color & 0xff
        g = (color >> 8) & 0xff
        b = (color >> 16) & 0xff
        return (int(r), int(g), int(b))


def summarize_ns(ns_list):
    us = [x / 1000.0 for x in ns_list]
    return {
        "mean_us": stats.mean(us),
        "p50_us": stats.median(us),
        "p95_us": stats.quantiles(us, n=20)[18],
        "min_us": min(us),
        "max_us": max(us),
    }


def main():
    hwnd = choose_capture_window() if PICK_HWND else win32gui.GetForegroundWindow()
    print(f"HWND={hwnd} Title='{win32gui.GetWindowText(hwnd)}'")
    _, _, cw, ch = win32gui.GetClientRect(hwnd)
    print(f"Client size: {cw}x{ch}")

    margin = 10
    n_points = 2000
    rng = random.Random(12345)
    points = [
        (rng.randint(margin, max(margin, cw - margin - 1)),
         rng.randint(margin, max(margin, ch - margin - 1)))
        for _ in range(n_points)
    ]

    bg = BackgroundFrameGrabber(hwnd, max_fps=60)
    screen = ScreenPixelSampler()

    # --- Measure capture cost alone ---
    capture_ns = []
    for _ in range(100):
        t0 = time.perf_counter_ns()
        bg.update(force=True)
        t1 = time.perf_counter_ns()
        capture_ns.append(t1 - t0)
    cap = summarize_ns(capture_ns)

    # Ensure we have a cached frame
    bg.update(force=True)

    # --- Measure bg pixel sampling only (no update) ---
    bg_px_ns = []
    bg_colors = []
    f = bg.frame_bgr
    if f is None:
        print("ERROR: no bg frame")
        return

    for (cx, cy) in points:
        t0 = time.perf_counter_ns()
        b, g, r = f[cy, cx]
        t1 = time.perf_counter_ns()
        bg_px_ns.append(t1 - t0)
        bg_colors.append((int(r), int(g), int(b)))
    bgpx = summarize_ns(bg_px_ns)

    # --- Measure screen pixel sampling ---
    screen_ns = []
    screen_colors = []
    for (cx, cy) in points:
        t0 = time.perf_counter_ns()
        c = screen.get_rgb_client(hwnd, cx, cy)
        t1 = time.perf_counter_ns()
        screen_ns.append(t1 - t0)
        screen_colors.append(c)
    sc = summarize_ns(screen_ns)

    # --- Agreement (only meaningful if window is visible & unobstructed) ---
    mism = 0
    for a, b in zip(bg_colors, screen_colors):
        if a != b:
            mism += 1

    print("\n=== Background capture cost (force update) ===")
    print(f"mean={cap['mean_us']:.2f}us p50={cap['p50_us']:.2f}us p95={cap['p95_us']:.2f}us")

    print("\n=== bg cached pixel sample only (NO update) ===")
    print(f"mean={bgpx['mean_us']:.4f}us p50={bgpx['p50_us']:.4f}us p95={bgpx['p95_us']:.4f}us")

    print("\n=== screen dc pixel sample ===")
    print(f"mean={sc['mean_us']:.2f}us p50={sc['p50_us']:.2f}us p95={sc['p95_us']:.2f}us")

    print("\n=== Agreement bg vs screen ===")
    print(f"mismatches={mism}/{n_points}")

    screen.close()


if __name__ == "__main__":
    main()
