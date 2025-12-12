# coords.py
import win32gui

def client_to_screen(hwnd, x, y):
    sx, sy = win32gui.ClientToScreen(hwnd, (x, y))
    return sx, sy

def screen_to_client(hwnd, x, y):
    cx, cy = win32gui.ScreenToClient(hwnd, (x, y))
    return cx, cy
