from pyrsistent import v
import win32gui
import win32con
import win32api
import win32ui
import os
import time
import data
import multiprocessing as mp
import win32clipboard
import pyautogui
exe = r"C:\Users\mateo\Desktop\HawkzOT\bin\client.exe"
conf = r"C:\Users\mateo\Desktop\HawkzOT\conf\clientoptions.json"

def changeData(lines):
    if number == 0:
        lines[email_line] = '        "loginEmailAddress": "'+email[0]+email[1]+'",'
    else:
        lines[email_line] = '        "loginEmailAddress": "'+email[0]+str(number)+email[1]+'",'
    return lines

email = ["email","@hotmail.com"]
password = 'password'
number = 0
clients = []
email_line = False
with open(conf, 'r') as file:
    # read a list of lines into data
    lines = file.readlines()
    for line in range(0, len(lines)):
        if "loginEmailAddress" in lines[line]:
            email_line = line
            print(line)
            break
for i in range(4):
    number = i
    lines = changeData(lines)
    # and write everything back
    with open(conf, 'w') as file:
        file.writelines( lines )
    os.startfile(exe)
    time.sleep(0.2)
    
def enumHandler(hwnd, lParam):
    if win32gui.GetClassName(hwnd) == "Qt5QWindowOwnDCIcon" and "Tibia" in win32gui.GetWindowText(hwnd) and "loaded" not in win32gui.GetWindowText(hwnd):
        clients.append(hwnd)
time.sleep(3)
win32gui.EnumWindows(enumHandler, None)

def pressOne(arg,hwnd):
    win32api.SendMessage(hwnd, win32con.WM_KEYDOWN, data.VK_CODE[arg], 0)
    time.sleep(.05)
    win32api.SendMessage(hwnd, win32con.WM_KEYUP, data.VK_CODE[arg], 0)
def press(*args):
    for i in args:
        win32api.SendMessage(hwnd, win32con.WM_KEYDOWN, data.VK_CODE[i], 0)
        time.sleep(.05)
        win32api.SendMessage(hwnd, win32con.WM_KEYUP, data.VK_CODE[i], 0)
win32clipboard.OpenClipboard()
try:
    clipdata = win32clipboard.GetClipboardData()
except:
    clipdata = False
win32clipboard.EmptyClipboard()
win32clipboard.SetClipboardText(password)
win32clipboard.CloseClipboard()
def login(hwnd):
    win32gui.SetForegroundWindow(hwnd)
    pressOne('enter',hwnd)
    time.sleep(0.4)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.1)
    pressOne('enter',hwnd)
for hwnd in clients:
    login(hwnd)
time.sleep(4)
for hwnd in clients:
    pressOne('enter',hwnd)
    
    
win32clipboard.OpenClipboard()
win32clipboard.EmptyClipboard()
if clipdata is not False:
    win32clipboard.SetClipboardText(clipdata)
win32clipboard.CloseClipboard()