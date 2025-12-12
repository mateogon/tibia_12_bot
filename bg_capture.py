# bg_capture.py
import time
import numpy as np
import win32gui
import win32ui
from ctypes import windll
import PIL.Image

class BackgroundFrameGrabber:
    """
    Captures a window offscreen using PrintWindow and caches the CLIENT-area frame.
    All coordinates are CLIENT coordinates.
    """
    def __init__(self, hwnd, max_fps=30):
        self.hwnd = hwnd
        self.max_fps = max_fps
        self.min_dt = 1.0 / max_fps
        self._last_t = 0.0
        self.frame_bgr = None

        self._crop = None  # (x1,y1,x2,y2) window-relative
        self._last_win_rect = None
        self._last_client_rect = None

    def _capture_window_rgb(self):
        l, t, r, b = win32gui.GetWindowRect(self.hwnd)
        w = r - l
        h = b - t

        hwndDC = win32gui.GetWindowDC(self.hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfcDC, w, h)
        saveDC.SelectObject(bmp)

        # PW_RENDERFULLCONTENT=2 (what you were using)
        result = windll.user32.PrintWindow(self.hwnd, saveDC.GetSafeHdc(), 2)

        bmpinfo = bmp.GetInfo()
        bmpstr = bmp.GetBitmapBits(True)

        # Cleanup GDI
        win32gui.DeleteObject(bmp.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(self.hwnd, hwndDC)

        if result != 1:
            return None  # capture failed

        im = PIL.Image.frombuffer(
            "RGB",
            (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
            bmpstr,
            "raw",
            "BGRX",
            0,
            1
        )
        return np.array(im)  # RGB
    
    def _refresh_crop(self):
        win_l, win_t, win_r, win_b = win32gui.GetWindowRect(self.hwnd)
        c0_sx, c0_sy = win32gui.ClientToScreen(self.hwnd, (0, 0))
        off_x = c0_sx - win_l
        off_y = c0_sy - win_t
        _, _, cw, ch = win32gui.GetClientRect(self.hwnd)
        self._crop = (off_x, off_y, off_x + cw, off_y + ch)

        self._last_win_rect = (win_l, win_t, win_r, win_b)
        self._last_client_rect = (0, 0, cw, ch)

    def _maybe_refresh_crop(self):
        win_rect = win32gui.GetWindowRect(self.hwnd)
        client_rect = win32gui.GetClientRect(self.hwnd)
        if self._crop is None or win_rect != self._last_win_rect or client_rect != self._last_client_rect:
            self._refresh_crop()

    def _window_to_client_crop(self, window_rgb):
        # Convert client origin to WINDOW-relative coordinates
        win_l, win_t, _, _ = win32gui.GetWindowRect(self.hwnd)
        c0_sx, c0_sy = win32gui.ClientToScreen(self.hwnd, (0, 0))
        off_x = c0_sx - win_l
        off_y = c0_sy - win_t

        # Client size
        _, _, cw, ch = win32gui.GetClientRect(self.hwnd)
        x1, y1 = off_x, off_y
        x2, y2 = off_x + cw, off_y + ch

        # Crop client area out of full window capture
        client_rgb = window_rgb[y1:y2, x1:x2]
        return client_rgb

    def update(self, force=False):
        now = time.perf_counter()
        if (not force) and (now - self._last_t) < self.min_dt and self.frame_bgr is not None:
            return True

        window_rgb = self._capture_window_rgb()
        if window_rgb is None:
            return False

        self._maybe_refresh_crop()
        x1, y1, x2, y2 = self._crop

        client_rgb = window_rgb[y1:y2, x1:x2]
        self.frame_bgr = client_rgb[:, :, ::-1].copy()
        self._last_t = now
        return True


    def get_pixel_rgb(self, cx, cy):
        """
        Returns (r,g,b) from cached CLIENT frame.
        Call update() periodically.
        """
        f = self.frame_bgr
        if f is None:
            return (999, 999, 999)
        h, w, _ = f.shape
        if cx < 0 or cy < 0 or cx >= w or cy >= h:
            return (999, 999, 999)
        b, g, r = f[cy, cx]
        return (int(r), int(g), int(b))
    
    def get_region_bgr(self, area):
        """
        area: (x1,y1,x2,y2) in CLIENT coords, x2/y2 exclusive
        returns np.ndarray BGR or None
        """
        f = self.frame_bgr
        if f is None:
            return None

        x1, y1, x2, y2 = area
        h, w, _ = f.shape

        # clamp
        x1 = max(0, min(w, x1))
        x2 = max(0, min(w, x2))
        y1 = max(0, min(h, y1))
        y2 = max(0, min(h, y2))

        if x2 <= x1 or y2 <= y1:
            return None

        return f[y1:y2, x1:x2]