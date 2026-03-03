# bg_capture.py
import time
import numpy as np
import cv2
import threading
import win32gui
import win32ui
from ctypes import windll

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
        self._gdi = None  # cached GDI resources for PrintWindow
        self.last_metrics = {
            "throttled": False,
            "capture_ms": 0.0,
            "crop_convert_ms": 0.0,
            "total_ms": 0.0,
        }
        self.metrics_seq = 0
        self._running = False
        self._thread = None
        self._lock = threading.RLock()
        self._last_geom = None  # (l,t,r,b,cw,ch)
        self._geom_changed_at = 0.0
        self._settle_s = 0.12

    def _release_gdi(self):
        # Caller should hold self._lock when invoking this method.
        if not self._gdi:
            return
        try:
            bmp = self._gdi.get("bmp")
            if bmp is not None:
                win32gui.DeleteObject(bmp.GetHandle())
        except Exception:
            pass
        try:
            saveDC = self._gdi.get("saveDC")
            if saveDC is not None:
                saveDC.DeleteDC()
        except Exception:
            pass
        try:
            mfcDC = self._gdi.get("mfcDC")
            if mfcDC is not None:
                mfcDC.DeleteDC()
        except Exception:
            pass
        try:
            hwndDC = self._gdi.get("hwndDC")
            if hwndDC is not None:
                win32gui.ReleaseDC(self.hwnd, hwndDC)
        except Exception:
            pass
        self._gdi = None

    def _ensure_gdi(self, w, h):
        # Caller should hold self._lock when invoking this method.
        if self._gdi and self._gdi.get("w") == w and self._gdi.get("h") == h:
            return

        self._release_gdi()

        hwndDC = win32gui.GetWindowDC(self.hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfcDC, w, h)
        saveDC.SelectObject(bmp)

        self._gdi = {
            "w": w,
            "h": h,
            "hwndDC": hwndDC,
            "mfcDC": mfcDC,
            "saveDC": saveDC,
            "bmp": bmp,
        }

    def _capture_window_rgb(self):
        with self._lock:
            l, t, r, b = win32gui.GetWindowRect(self.hwnd)
            w = r - l
            h = b - t
            _, _, cw, ch = win32gui.GetClientRect(self.hwnd)
            geom = (l, t, r, b, cw, ch)
            now = time.perf_counter()

            # During drag/resize the geometry changes rapidly. Skip capture until
            # it stabilizes to avoid PrintWindow/GDI instability.
            if self._last_geom is None:
                self._last_geom = geom
                self._geom_changed_at = now
                return None
            if geom != self._last_geom:
                self._last_geom = geom
                self._geom_changed_at = now
                self._release_gdi()
                return None
            if (now - self._geom_changed_at) < self._settle_s:
                return None

            if w <= 0 or h <= 0:
                return None
            if not win32gui.IsWindow(self.hwnd) or win32gui.IsIconic(self.hwnd):
                return None

            self._ensure_gdi(w, h)
            saveDC = self._gdi["saveDC"]
            bmp = self._gdi["bmp"]

            # PW_RENDERFULLCONTENT=2
            result = windll.user32.PrintWindow(self.hwnd, saveDC.GetSafeHdc(), 2)
            bmpinfo = bmp.GetInfo()
            bmpstr = bmp.GetBitmapBits(True)

            if result != 1:
                return None  # capture failed

            try:
                bw = int(bmpinfo.get("bmWidth", 0))
                bh = int(bmpinfo.get("bmHeight", 0))
                if bw <= 0 or bh <= 0:
                    return None
                arr = np.frombuffer(bmpstr, dtype=np.uint8)
                expected = bw * bh * 4
                if arr.size < expected:
                    return None
                arr = arr[:expected].reshape((bh, bw, 4))
                # BGRX -> RGB
                rgb = cv2.cvtColor(arr, cv2.COLOR_BGRA2RGB)
                return rgb
            except Exception:
                # Resize/race edge cases can invalidate backing bits briefly.
                return None

    def __del__(self):
        with self._lock:
            self._release_gdi()
    
    def _refresh_crop(self):
        with self._lock:
            win_l, win_t, win_r, win_b = win32gui.GetWindowRect(self.hwnd)
            c0_sx, c0_sy = win32gui.ClientToScreen(self.hwnd, (0, 0))
            off_x = c0_sx - win_l
            off_y = c0_sy - win_t
            _, _, cw, ch = win32gui.GetClientRect(self.hwnd)
            self._crop = (off_x, off_y, off_x + cw, off_y + ch)
            self._last_win_rect = (win_l, win_t, win_r, win_b)
            self._last_client_rect = (0, 0, cw, ch)

    def _maybe_refresh_crop(self):
        with self._lock:
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
        t_start = time.perf_counter()
        now = time.perf_counter()
        if (not force) and (now - self._last_t) < self.min_dt and self.frame_bgr is not None:
            self.last_metrics = {
                "throttled": True,
                "capture_ms": 0.0,
                "crop_convert_ms": 0.0,
                "total_ms": (time.perf_counter() - t_start) * 1000.0,
            }
            self.metrics_seq += 1
            return True

        t_cap0 = time.perf_counter()
        window_rgb = self._capture_window_rgb()
        t_cap1 = time.perf_counter()
        if window_rgb is None:
            self.last_metrics = {
                "throttled": False,
                "capture_ms": (t_cap1 - t_cap0) * 1000.0,
                "crop_convert_ms": 0.0,
                "total_ms": (time.perf_counter() - t_start) * 1000.0,
            }
            self.metrics_seq += 1
            return False

        # Crop is refreshed by Bot.updateWindowCoordinates() on any resize/move.
        # Avoid per-frame Win32 rect checks here.
        with self._lock:
            if self._crop is None:
                self._refresh_crop()
            x1, y1, x2, y2 = self._crop

        t_conv0 = time.perf_counter()
        client_rgb = window_rgb[y1:y2, x1:x2]
        if client_rgb.size == 0:
            self.last_metrics = {
                "throttled": False,
                "capture_ms": (t_cap1 - t_cap0) * 1000.0,
                "crop_convert_ms": 0.0,
                "total_ms": (time.perf_counter() - t_start) * 1000.0,
            }
            self.metrics_seq += 1
            return False
        # OpenCV conversion is typically faster and returns contiguous output.
        self.frame_bgr = cv2.cvtColor(client_rgb, cv2.COLOR_RGB2BGR)
        t_conv1 = time.perf_counter()
        self._last_t = now
        self.last_metrics = {
            "throttled": False,
            "capture_ms": (t_cap1 - t_cap0) * 1000.0,
            "crop_convert_ms": (t_conv1 - t_conv0) * 1000.0,
            "total_ms": (time.perf_counter() - t_start) * 1000.0,
        }
        self.metrics_seq += 1
        return True

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="BGCapture", daemon=True)
        self._thread.start()

    def _run_loop(self):
        while self._running:
            self.update(force=False)
            time.sleep(0.001)

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        with self._lock:
            self._release_gdi()


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
