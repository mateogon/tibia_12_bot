import win32gui,win32api,win32con
import time
import inspect
from ..config import data

_ACTION_LOGGING_ENABLED = False
_ACTION_LOGGING_INCLUDE_CALLER = True
_ACTION_LOG_DEDUPE_MS = 350
_LAST_ACTION_LOG_LINE = ""
_LAST_ACTION_LOG_TS_MS = 0
_SUPPRESSED_ACTION_LOGS = 0


def configure_action_logging(enabled=False, include_caller=True):
    global _ACTION_LOGGING_ENABLED, _ACTION_LOGGING_INCLUDE_CALLER
    global _LAST_ACTION_LOG_LINE, _LAST_ACTION_LOG_TS_MS, _SUPPRESSED_ACTION_LOGS
    _ACTION_LOGGING_ENABLED = bool(enabled)
    _ACTION_LOGGING_INCLUDE_CALLER = bool(include_caller)
    # Reset dedupe state whenever logging mode changes.
    _LAST_ACTION_LOG_LINE = ""
    _LAST_ACTION_LOG_TS_MS = 0
    _SUPPRESSED_ACTION_LOGS = 0


def _caller_tag():
    if not _ACTION_LOGGING_INCLUDE_CALLER:
        return ""
    try:
        stack = inspect.stack()
        # [0]=_caller_tag, [1]=_log_action, [2]=click function, [3]=bot caller
        if len(stack) > 3:
            frame = stack[3]
            return f" caller={frame.function}:{frame.lineno}"
    except Exception:
        pass
    return ""


def _log_action(msg):
    global _LAST_ACTION_LOG_LINE, _LAST_ACTION_LOG_TS_MS, _SUPPRESSED_ACTION_LOGS
    if not _ACTION_LOGGING_ENABLED:
        return

    now_ms = int(time.time() * 1000)
    line = f"{msg}{_caller_tag()}"
    if line == _LAST_ACTION_LOG_LINE and (now_ms - _LAST_ACTION_LOG_TS_MS) < _ACTION_LOG_DEDUPE_MS:
        _SUPPRESSED_ACTION_LOGS += 1
        return

    if _SUPPRESSED_ACTION_LOGS > 0 and _LAST_ACTION_LOG_LINE:
        print(f"{_LAST_ACTION_LOG_LINE} [x{_SUPPRESSED_ACTION_LOGS + 1}]")
        _SUPPRESSED_ACTION_LOGS = 0
    else:
        print(line)

    _LAST_ACTION_LOG_LINE = line
    _LAST_ACTION_LOG_TS_MS = now_ms

def isTopWindow(hwnd):
    current_window = win32gui.GetForegroundWindow()
    return current_window == hwnd

def setForegroundWindow(hwnd):
    global current_window
    current_window = win32gui.GetForegroundWindow()
    if (current_window != hwnd):
        #shell.SendKeys('%')
        win32gui.SetForegroundWindow(hwnd)
        
def maximizeWindow(hwnd):
        tup = win32gui.GetWindowPlacement(hwnd)
        if tup[1] == win32con.SW_SHOWMINIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            time.sleep(0.2)
    
def revertForegroundWindow():
    if (win32gui.GetForegroundWindow() != current_window):
        #shell.SendKeys('%')
        win32gui.SetForegroundWindow(current_window)

def click(hwnd,x, y , x_offset=-8, y_offset=-8):
    _log_action(f"[ACTION] trying to left-click (legacy) client=({x},{y}) offset=({x_offset},{y_offset})")
    lParam = win32api.MAKELONG(x+x_offset, y+y_offset-18)
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN,
                         win32con.MK_LBUTTON, lParam)
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, None, lParam)
    
def rclick(hwnd,x, y, x_offset=-8, y_offset=-8):
    _log_action(f"[ACTION] trying to right-click (legacy) client=({x},{y}) offset=({x_offset},{y_offset})")
    lParam = win32api.MAKELONG(x+x_offset, y+y_offset-18)
    win32gui.PostMessage(hwnd, win32con.WM_RBUTTONDOWN,
                         win32con.MK_RBUTTON, lParam)
    win32gui.PostMessage(hwnd, win32con.WM_RBUTTONUP, None, lParam)
    
def shiftrclick(hwnd,x, y, x_offset=-8, y_offset=-8):
        win32api.SendMessage(hwnd, win32con.WM_KEYDOWN, 0x10, 0)
        time.sleep(.05)
        rclick(hwnd,x, y , x_offset, y_offset)
        win32api.SendMessage(hwnd, win32con.WM_KEYUP, 0x10, 0)

def press(hwnd,*args):
    for i in args:
        win32api.SendMessage(hwnd, win32con.WM_KEYDOWN, data.VK_CODE[i], 0)
        #time.sleep(.05)
        win32api.SendMessage(hwnd, win32con.WM_KEYUP, data.VK_CODE[i], 0)


def click_client(hwnd, cx, cy, log_action=False, log_context=""):
    if log_action or _ACTION_LOGGING_ENABLED:
        ctx = f" {log_context}" if log_context else ""
        _log_action(f"[ACTION] trying to left-click client=({int(cx)},{int(cy)}) hwnd={hwnd}{ctx}")
    lParam = win32api.MAKELONG(cx, cy)
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lParam)

def rclick_client(hwnd, cx, cy):
    _log_action(f"[ACTION] trying to right-click client=({int(cx)},{int(cy)}) hwnd={hwnd}")
    lParam = win32api.MAKELONG(cx, cy)
    win32gui.PostMessage(hwnd, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, lParam)
    win32gui.PostMessage(hwnd, win32con.WM_RBUTTONUP, 0, lParam)

def physical_click(hwnd, client_x, client_y, right=False):
        """
        Simulates a hardware-level click.
        Automatically converts Client coordinates to Global Screen coordinates
        to account for the Window Title Bar and Borders.
        """
        _log_action(
            f"[ACTION] trying to {'right' if right else 'left'}-click physical "
            f"client=({int(client_x)},{int(client_y)}) hwnd={hwnd}"
        )
        # 1. Global Screen Conversion
        # This fixes the "clicking a bit up" issue by adding the title bar height
        point = win32gui.ClientToScreen(hwnd, (int(client_x), int(client_y)))
        screen_x, screen_y = point[0], point[1]
        _log_action(f"[ACTION] physical click mapped to screen=({screen_x},{screen_y})")

        # 2. Teleport Cursor
        win32api.SetCursorPos((screen_x, screen_y))
        time.sleep(0.05) # Delay to ensure the game engine "sees" the mouse hover
        
        # 3. Inject Physical Mouse Event
        down = win32con.MOUSEEVENTF_RIGHTDOWN if right else win32con.MOUSEEVENTF_LEFTDOWN
        up = win32con.MOUSEEVENTF_RIGHTUP if right else win32con.MOUSEEVENTF_LEFTUP
        
        win32api.mouse_event(down, screen_x, screen_y, 0, 0)
        time.sleep(0.05)
        win32api.mouse_event(up, screen_x, screen_y, 0, 0)
