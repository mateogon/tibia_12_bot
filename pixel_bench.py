# pixel_bench_bg.py
# Benchmarks:
# 1) bg cached pixel (PrintWindow -> crop client -> sample)
# 2) screen rgb (desktop DC; only correct if window visible)
# 3) your legacy GetPixelRGBColor* variants
# Also checks color agreement vs bg cached (background truth).

# Run: python pixel_bench_bg.py

import time
import random
import statistics as stats
import win32gui

import image as img
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


# --- Fast screen sampler (visible-only) ---
import win32ui

class ScreenPixelSampler:
    def __init__(self):
        self._hdc = win32gui.GetDC(0)          # screen DC
        self._dc = win32ui.CreateDCFromHandle(self._hdc)

    def close(self):
        try:
            self._dc.DeleteDC()
        finally:
            win32gui.ReleaseDC(0, self._hdc)

    def get_rgb_client(self, hwnd, cx, cy):
        sx, sy = win32gui.ClientToScreen(hwnd, (cx, cy))
        color = self._dc.GetPixel(sx, sy)      # 0x00bbggrr
        r = color & 0xff
        g = (color >> 8) & 0xff
        b = (color >> 16) & 0xff
        return (int(r), int(g), int(b))


def bench(fn, hwnd, points, coord_mode):
    times_ns = []
    results = []

    win_l, win_t, win_r, win_b = win32gui.GetWindowRect(hwnd)

    for (cx, cy) in points:
        if coord_mode == "client":
            x, y = cx, cy
        elif coord_mode == "screen":
            x, y = win32gui.ClientToScreen(hwnd, (cx, cy))
        elif coord_mode == "window":
            sx, sy = win32gui.ClientToScreen(hwnd, (cx, cy))
            x, y = sx - win_l, sy - win_t
        else:
            raise ValueError("bad coord_mode")

        t0 = time.perf_counter_ns()
        out = fn(hwnd, (x, y)) if fn.__name__.startswith("GetPixel") else fn(hwnd, x, y)
        t1 = time.perf_counter_ns()

        times_ns.append(t1 - t0)
        results.append(out)

    return times_ns, results


def summarize(times_ns):
    us = [t / 1000.0 for t in times_ns]
    return {
        "mean_us": stats.mean(us),
        "p50_us": stats.median(us),
        "p95_us": stats.quantiles(us, n=20)[18],  # ~95th
        "min_us": min(us),
        "max_us": max(us),
    }


def main():
    hwnd = get_hwnd()
    title = win32gui.GetWindowText(hwnd)
    print(f"HWND={hwnd} Title='{title}'")

    _, _, cw, ch = win32gui.GetClientRect(hwnd)
    print(f"Client size: {cw}x{ch}")

    # Points (avoid edges)
    margin = 10
    n_points = 200
    rng = random.Random(12345)
    points = [
        (rng.randint(margin, max(margin, cw - margin - 1)),
         rng.randint(margin, max(margin, ch - margin - 1)))
        for _ in range(n_points)
    ]

    # --- Background cached source (ground truth for "background works") ---
    bg = BackgroundFrameGrabber(hwnd, max_fps=60)
    ok = bg.update(force=True)
    if not ok:
        print("ERROR: PrintWindow capture failed. bg capture unavailable.")
        return

    def get_pixel_bg(hwnd, cx, cy):
        # amortized: one capture per frame budget, many pixel reads free
        bg.update()
        return bg.get_pixel_rgb(cx, cy)

    # --- Screen DC source (only correct if unobstructed) ---
    screen = ScreenPixelSampler()

    def get_pixel_screen(hwnd, cx, cy):
        return screen.get_rgb_client(hwnd, cx, cy)

    # --- Tests ---
    tests = []
    tests.append(("bg_cached (client)", get_pixel_bg, "client"))
    tests.append(("screen_dc (client)", get_pixel_screen, "client"))

    legacy = []
    for name in ["GetPixelRGBColor", "GetPixelRGBColor2", "GetPixelRGBColor22"]:
        if hasattr(img, name):
            legacy.append((name, getattr(img, name)))

    for name, fn in legacy:
        tests.append((f"{name} (client)", fn, "client"))
        tests.append((f"{name} (screen)", fn, "screen"))
        tests.append((f"{name} (window)", fn, "window"))

    # --- Run ---
    results_by_test = {}
    for test_name, fn, mode in tests:
        times_ns, colors = bench(fn, hwnd, points, mode)
        results_by_test[test_name] = (times_ns, colors)

    # Reference for agreement: background cached
    ref_times, ref_colors = results_by_test["bg_cached (client)"]

    print("\n=== Timing (microseconds per call) ===")
    for test_name, (times_ns, _) in results_by_test.items():
        s = summarize(times_ns)
        print(f"{test_name:28s}  mean={s['mean_us']:.2f}  p50={s['p50_us']:.2f}  p95={s['p95_us']:.2f}  min={s['min_us']:.2f}  max={s['max_us']:.2f}")

    print("\n=== Color agreement vs bg_cached ===")
    for test_name, (_, colors) in results_by_test.items():
        if test_name == "bg_cached (client)":
            continue
        mismatches = []
        for i, (a, b) in enumerate(zip(ref_colors, colors)):
            if a != b:
                mismatches.append((i, points[i], a, b))

        print(f"{test_name:28s}  mismatches={len(mismatches)}/{n_points}")
        for j in range(min(5, len(mismatches))):
            idx, (cx, cy), ref, got = mismatches[j]
            print(f"  idx={idx:3d} point(client)=({cx},{cy}) ref={ref} got={got}")

    # Optional: capture cost estimate (separate from per-pixel read)
    # Measures a forced capture time for PrintWindow+crop.
    capture_ns = []
    for _ in range(50):
        t0 = time.perf_counter_ns()
        bg.update(force=True)
        t1 = time.perf_counter_ns()
        capture_ns.append(t1 - t0)

    cap_us = [t / 1000.0 for t in capture_ns]
    print("\n=== bg capture cost (forced update) ===")
    print(f"mean={stats.mean(cap_us):.2f}us  p50={stats.median(cap_us):.2f}us  min={min(cap_us):.2f}us  max={max(cap_us):.2f}us")

    screen.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
