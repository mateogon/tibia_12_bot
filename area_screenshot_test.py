import image as img
import win32gui
from choose_client_gui import choose_capture_window
from extras import *
import numpy as np
if __name__ == "__main__":
    hwnd = choose_capture_window()
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    height = bottom - top
    width = right - left
    area = (100, 100, width-100, height-100)
    avg1 = 0
    avg2 = 0
    t = 0
    start = timeInMillis()
    for i in range(0,100):
        t = timeInMillis() - start
        im1 = img.area_screenshot(hwnd,area)
        avg1+= t
        t = timeInMillis() - start
        im2 = img.area_screenshot2(hwnd,area)
        avg2+= t
        #print(np.array_equal(im1,im2))
    print("avg1: ",avg1/100)
    print("avg2: ",avg2/100)