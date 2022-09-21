import win32gui,win32api,win32con
import time
import data

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
    lParam = win32api.MAKELONG(x+x_offset, y+y_offset-18)
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN,
                         win32con.MK_LBUTTON, lParam)
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, None, lParam)
    
def rclick(hwnd,x, y, x_offset=-8, y_offset=-8):
    lParam = win32api.MAKELONG(x+x_offset, y+y_offset-18)
    win32gui.PostMessage(hwnd, win32con.WM_RBUTTONDOWN,
                         win32con.MK_RBUTTON, lParam)
    win32gui.PostMessage(hwnd, win32con.WM_RBUTTONUP, None, lParam)

def press(hwnd,*args):
    for i in args:
        win32api.SendMessage(hwnd, win32con.WM_KEYDOWN, data.VK_CODE[i], 0)
        time.sleep(.05)
        win32api.SendMessage(hwnd, win32con.WM_KEYUP, data.VK_CODE[i], 0)