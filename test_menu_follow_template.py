# test_menu_follow_template.py
import time
import ctypes
import cv2
import numpy as np
import win32gui

import image as img
from window_interaction import click_client, rclick_client

TIBIA_TITLE_SUBSTR = "Tibia - Helios"
TEMPLATE_PATH = "img/hud/menu_follow.png"
THRESH = 0.88

REG_W = 320
REG_H = 320
MENU_PAINT_DELAY = 0.25


# ---------------- DPI AWARENESS ----------------
def set_dpi_awareness():
    # Best effort across Windows versions
    try:
        # Windows 8.1+
        shcore = ctypes.windll.shcore
        shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        return "shcore:SetProcessDpiAwareness(2)"
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # Vista+
            return "user32:SetProcessDPIAware()"
        except Exception:
            return "dpi:FAILED"


# ---------------- VIRTUAL SCREEN CLAMP ----------------
def get_virtual_screen_rect():
    SM_XVIRTUALSCREEN = 76
    SM_YVIRTUALSCREEN = 77
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79
    user32 = ctypes.windll.user32
    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return vx, vy, vx + vw, vy + vh


def clamp_to_virtual_screen(sx1, sy1, sx2, sy2):
    vx1, vy1, vx2, vy2 = get_virtual_screen_rect()
    sx1 = max(vx1, min(int(sx1), vx2 - 1))
    sy1 = max(vy1, min(int(sy1), vy2 - 1))
    sx2 = max(vx1, min(int(sx2), vx2))
    sy2 = max(vy1, min(int(sy2), vy2))
    return sx1, sy1, sx2, sy2


# ---------------- MSS CAPTURE (NO SWALLOW) ----------------
def mss_grab_screen_rect(sx1, sy1, sx2, sy2):
    import mss
    sx1, sy1, sx2, sy2 = clamp_to_virtual_screen(sx1, sy1, sx2, sy2)
    w = sx2 - sx1
    h = sy2 - sy1
    if w <= 0 or h <= 0:
        raise ValueError(f"invalid rect after clamp: ({sx1},{sy1})-({sx2},{sy2})")
    with mss.mss() as sct:
        mon = {"left": sx1, "top": sy1, "width": w, "height": h}
        shot = np.array(sct.grab(mon))  # BGRA
        bgr = shot[:, :, :3]            # BGR
        return np.ascontiguousarray(bgr, dtype=np.uint8)


# ---------------- TEMPLATE MATCH ----------------
def locate_template_in_crop(crop_bgr, templ_bgr, thresh=0.88):
    res = cv2.matchTemplate(crop_bgr, templ_bgr, cv2.TM_CCOEFF_NORMED)
    _minv, maxv, _minloc, maxloc = cv2.minMaxLoc(res)
    if maxv < thresh:
        return None, maxv
    th, tw = templ_bgr.shape[:2]
    x, y = maxloc
    return (x, y, tw, th), maxv


# ---------------- WINDOW FIND ----------------
def find_tibia_hwnd():
    found = []
    def cb(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        if TIBIA_TITLE_SUBSTR.lower() in title.lower():
            found.append(hwnd)
    win32gui.EnumWindows(cb, None)
    return found[0] if found else None


def main():
    dpi_mode = set_dpi_awareness()
    print(f"[DBG] dpi_awareness={dpi_mode}")
    vx1, vy1, vx2, vy2 = get_virtual_screen_rect()
    print(f"[DBG] virtual_screen=({vx1},{vy1})-({vx2},{vy2})")

    hwnd = find_tibia_hwnd()
    if not hwnd:
        print("Tibia window not found")
        return

    templ = cv2.imread(TEMPLATE_PATH)
    if templ is None:
        print(f"Template not found: {TEMPLATE_PATH}")
        return
    templ = np.ascontiguousarray(templ, dtype=np.uint8)

    print("1) Hover mouse over a PARTY NAME row in Tibia (inside game content).")
    print("2) Press ENTER to right-click that point and attempt Follow by template.")
    input()

    # cursor pos in SCREEN coords
    cx, cy = win32gui.GetCursorInfo()[2]

    # window rect in SCREEN coords
    wx1, wy1, wx2, wy2 = win32gui.GetWindowRect(hwnd)

    # Convert screen->client
    click_x, click_y = win32gui.ScreenToClient(hwnd, (cx, cy))

    # client rect
    _cl, _ct, cr, cb = win32gui.GetClientRect(hwnd)
    cw, ch = cr, cb

    print(f"[DBG] hwnd={hwnd} win_rect=({wx1},{wy1},{wx2},{wy2})")
    print(f"[DBG] cursor screen=({cx},{cy}) click client=({click_x},{click_y}) client_wh=({cw},{ch})")

    # A) MSS tiny grab around cursor in SCREEN coords (proves MSS works at all)
    try:
        a = mss_grab_screen_rect(cx - 40, cy - 40, cx + 40, cy + 40)
        cv2.imwrite("dbg_A_cursor_mss.png", a)
        print("[DBG] A) MSS cursor grab OK -> dbg_A_cursor_mss.png")
    except Exception as e:
        print(f"[DBG] A) MSS cursor grab FAILED: {repr(e)}")

    # Right click in CLIENT coords (your message-based click)
    rclick_client(hwnd, click_x, click_y)
    time.sleep(MENU_PAINT_DELAY)

    # Region in CLIENT coords (search where menu should be)
    rx1 = click_x + 5
    ry1 = click_y + 5
    rx2 = rx1 + REG_W
    ry2 = ry1 + REG_H
    print(f"[DBG] region client=({rx1},{ry1},{rx2},{ry2})")

    # Convert client region -> screen region
    sx1, sy1 = win32gui.ClientToScreen(hwnd, (rx1, ry1))
    sx2, sy2 = win32gui.ClientToScreen(hwnd, (rx2, ry2))
    print(f"[DBG] region screen(before clamp)=({sx1},{sy1},{sx2},{sy2})")

    # B) MSS grab for that computed menu region in SCREEN coords
    crop_mss = None
    try:
        crop_mss = mss_grab_screen_rect(sx1, sy1, sx2, sy2)
        cv2.imwrite("dbg_B_menu_region_mss.png", crop_mss)
        print("[DBG] B) MSS menu-region grab OK -> dbg_B_menu_region_mss.png")
    except Exception as e:
        print(f"[DBG] B) MSS menu-region grab FAILED: {repr(e)}")

    # C) Your window grab for the same region (CLIENT coords)
    crop_win = None
    try:
        crop_win = img.screengrab_array(hwnd, (rx1, ry1, rx2, ry2))
        if crop_win is None:
            print("[DBG] C) screengrab_array returned None")
        else:
            crop_win = np.ascontiguousarray(crop_win, dtype=np.uint8)
            cv2.imwrite("dbg_C_menu_region_windowgrab.png", crop_win)
            print("[DBG] C) window grab OK -> dbg_C_menu_region_windowgrab.png")
    except Exception as e:
        print(f"[DBG] C) window grab exception: {repr(e)}")

    # Choose crop for template match: prefer MSS if available
    crop = crop_mss if crop_mss is not None else crop_win
    if crop is None:
        print("[DBG] No usable crop from MSS or window grab. Capture stack is broken in this environment.")
        return

    hit, score = locate_template_in_crop(crop, templ, THRESH)
    print(f"[DBG] match score={score:.3f}")

    if not hit:
        cv2.imwrite("debug_menu_crop.png", crop)
        print("NO HIT. Saved debug_menu_crop.png")
        return

    hx, hy, hw, hh = hit

    # Convert hit point back to CLIENT coords for click
    # If crop came from MSS, we know its top-left screen is (sx1,sy1) after clamp.
    # Recompute clamped screen rect so mapping is exact.
    csx1, csy1, csx2, csy2 = clamp_to_virtual_screen(sx1, sy1, sx2, sy2)
    target_sx = csx1 + hx + hw // 2
    target_sy = csy1 + hy + hh // 2
    target_cx, target_cy = win32gui.ScreenToClient(hwnd, (target_sx, target_sy))

    dbg = crop.copy()
    cv2.rectangle(dbg, (hx, hy), (hx + hw, hy + hh), (0, 0, 255), 2)
    cv2.drawMarker(dbg, (hx + hw // 2, hy + hh // 2), (255, 0, 0), cv2.MARKER_CROSS, 15, 2)
    cv2.imwrite("debug_menu_crop_hit.png", dbg)

    click_client(hwnd, target_cx, target_cy)
    print(f"[DBG] clicked client=({target_cx},{target_cy}) from screen=({target_sx},{target_sy})")
    print("Saved debug_menu_crop_hit.png")

if __name__ == "__main__":
    main()
