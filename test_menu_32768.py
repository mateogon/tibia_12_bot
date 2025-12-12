# test_menu_follow_template.py
import time
import cv2
import numpy as np
import win32gui

import image as img  # your module
from window_interaction import click_client, rclick_client

# ----------------- CONFIG -----------------
TIBIA_TITLE_SUBSTR = "Tibia - Helios"
TEMPLATE_PATH = "img/hud/menu_follow.png"   # make this file (tight crop of the "Follow" row)
THRESH = 0.88

# region relative to right click point (CLIENT coords)
REG_W = 320
REG_H = 320

MENU_PAINT_DELAY = 0.25  # start small; increase if menu is slow
# -----------------------------------------


def find_tibia_hwnd():
    found = []

    def cb(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        if TIBIA_TITLE_SUBSTR.lower() in title.lower():
            found.append(hwnd)

    win32gui.EnumWindows(cb, None)
    return found[0] if found else None


def locate_template_in_crop(crop_bgr, templ_bgr, thresh=0.88):
    res = cv2.matchTemplate(crop_bgr, templ_bgr, cv2.TM_CCOEFF_NORMED)
    _minv, maxv, _minloc, maxloc = cv2.minMaxLoc(res)
    if maxv < thresh:
        return None, maxv
    th, tw = templ_bgr.shape[:2]
    x, y = maxloc
    return (x, y, tw, th), maxv


def clamp_region_to_client(hwnd, rx1, ry1, rx2, ry2):
    c_left, c_top, c_right, c_bottom = win32gui.GetClientRect(hwnd)
    client_w = c_right - c_left
    client_h = c_bottom - c_top

    rx1 = max(0, min(int(rx1), client_w - 1))
    ry1 = max(0, min(int(ry1), client_h - 1))
    rx2 = max(0, min(int(rx2), client_w))
    ry2 = max(0, min(int(ry2), client_h))

    return rx1, ry1, rx2, ry2, client_w, client_h


def main():
    hwnd = find_tibia_hwnd()
    if not hwnd:
        print("Tibia window not found")
        return

    templ = cv2.imread(TEMPLATE_PATH)
    if templ is None:
        print(f"Template not found: {TEMPLATE_PATH}")
        return
    templ = np.ascontiguousarray(templ, dtype=np.uint8)

    print("1) Hover your mouse over a PARTY NAME row in Tibia (inside the game content, not border/titlebar).")
    print("2) Press ENTER in this console to right-click that point and attempt Follow by template.")
    input()

    # Cursor pos in SCREEN coords
    cx, cy = win32gui.GetCursorInfo()[2]

    # Convert screen -> client
    click_x, click_y = win32gui.ScreenToClient(hwnd, (cx, cy))

    # Client size
    c_left, c_top, c_right, c_bottom = win32gui.GetClientRect(hwnd)
    client_w = c_right - c_left
    client_h = c_bottom - c_top

    print(f"[DBG] cursor screen=({cx},{cy}) click client=({click_x},{click_y}) client_wh=({client_w},{client_h})")

    # Sanity: click must be inside client
    if not (0 <= click_x < client_w and 0 <= click_y < client_h):
        print("[DBG] Click is outside CLIENT rect. Move mouse fully inside the Tibia client area.")
        return

    # Open context menu at that client point
    rclick_client(hwnd, click_x, click_y)
    time.sleep(MENU_PAINT_DELAY)

    # Define menu search region in CLIENT coords (down-right from click)
    rx1 = click_x + 5
    ry1 = click_y + 5
    rx2 = rx1 + REG_W
    ry2 = ry1 + REG_H

    rx1, ry1, rx2, ry2, client_w, client_h = clamp_region_to_client(hwnd, rx1, ry1, rx2, ry2)
    print(f"[DBG] region client=({rx1},{ry1},{rx2},{ry2})")

    if rx2 <= rx1 or ry2 <= ry1:
        print("[DBG] Region collapsed after clamp. Move mouse away from edges or reduce REG_W/REG_H.")
        return

    region = (rx1, ry1, rx2, ry2)

    crop = img.screengrab_array(hwnd, region)  # expected CLIENT coords
    if crop is None:
        print("[DBG] Failed to capture crop. Testing full-client capture...")

        full = img.screengrab_array(hwnd, (0, 0, client_w, client_h))
        if full is None:
            print("[DBG] Full-client capture also FAILED. screengrab_array cannot capture this hwnd right now.")
            print("[DBG] Causes: minimized window, capture backend mismatch, or screengrab expects different coord space.")
            return

        cv2.imwrite("debug_full_client.png", full)
        print("[DBG] Saved debug_full_client.png (capture works). Your region coords/space are wrong for screengrab_array.")
        return

    crop = np.ascontiguousarray(crop, dtype=np.uint8)
    cv2.imwrite("debug_menu_crop.png", crop)

    hit, score = locate_template_in_crop(crop, templ, THRESH)
    print(f"[DBG] match score={score:.3f}")

    if not hit:
        print("NO HIT. Saved debug_menu_crop.png. Fix template image or adjust REG_W/REG_H / MENU_PAINT_DELAY.")
        return

    hx, hy, hw, hh = hit

    # Convert hit -> client coords
    target_client_x = rx1 + hx + hw // 2
    target_client_y = ry1 + hy + hh // 2

    # Visualize
    dbg = crop.copy()
    cv2.rectangle(dbg, (hx, hy), (hx + hw, hy + hh), (0, 0, 255), 2)
    cv2.drawMarker(dbg, (hx + hw // 2, hy + hh // 2), (255, 0, 0), cv2.MARKER_CROSS, 15, 2)
    cv2.imwrite("debug_menu_crop_hit.png", dbg)

    # Click Follow row (CLIENT coords)
    click_client(hwnd, target_client_x, target_client_y)
    print("Clicked detected Follow. Saved debug_menu_crop.png + debug_menu_crop_hit.png")


if __name__ == "__main__":
    main()
