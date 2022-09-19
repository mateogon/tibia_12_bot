
import win32gui
import win32ui
from ctypes import windll
import pytesseract
import cv2
import numpy as np
import PIL
import os
from math import sqrt
#from natsort import natsorted
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
left = -8
top = -8
# endregion
def tesser_image(im, a, b, c, config):
    thresh = [cv2.THRESH_BINARY, cv2.THRESH_BINARY_INV,
              cv2.THRESH_TRUNC, cv2.THRESH_TOZERO, cv2.THRESH_TOZERO_INV]
    retval, img = cv2.threshold(im, a, b, thresh[c])
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    text = pytesseract.image_to_string(img, config=config)
    return text.strip()
    #

def screengrab_array(hwnd,area, show=False):
    im = area_screenshot(hwnd,area)
    im = np.array(im)
    if show:
        visualize(im)
    return(im)

def visualize(img):
    cv2.imshow('im', img)
    if (cv2.waitKey(0) & 0xFF):
        cv2.destroyAllWindows()

def area_screenshot(hwnd,area):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    game_h = abs(bottom - top)
    game_w = abs(right - left)
    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()

    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, game_w, game_h)

    saveDC.SelectObject(saveBitMap)
    result = windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 0)
    bmpinfo = saveBitMap.GetInfo()
    bmpstr = saveBitMap.GetBitmapBits(True)

    im = PIL.Image.frombuffer(
        'RGB',
        (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
        bmpstr, 'raw', 'BGRX', 0, 1)

    win32gui.DeleteObject(saveBitMap.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC
    win32gui.ReleaseDC(hwnd, hwndDC)

    if result == 1:
        im = im.crop(area)
        im = np.array(im)
        im = im[:, :, ::-1]
        im = PIL.Image.fromarray(im)
        # im.show()
        return im
    else:
        print("image crop failed")

def locateImage(hwnd,file, region, thresh, show=False):
    img_rgb = screengrab_array(hwnd,region)
    template = cv2.imread('img/'+file)
    height, width, channels = template.shape
    h, w = template.shape[:-1]
    res = cv2.matchTemplate(img_rgb, template, cv2.TM_CCOEFF_NORMED)
    threshold = thresh
    loc = np.where(res >= threshold)
    for pt in zip(*loc[::-1]):  # Switch collumns and rows
        if (show):
            cv2.rectangle(img_rgb, pt, (pt[0] + w, pt[1] + h), (255, 0, 0), 1)
        pos = pt
    try:
        # print(time.time()-start_time)
        #img = PIL.Image.fromarray(img_rgb).show()
        if (show):
            visualize(img_rgb)
        return (pos[0]+left, pos[1]+top, w, h)

    except:
        return False

def locateManyImage(hwnd,file, region, thresh):
    img_rgb = screengrab_array(hwnd,region)

    template = cv2.imread('img/'+file)
    height, width, channels = template.shape
    h, w = template.shape[:-1]
    res = cv2.matchTemplate(img_rgb, template, cv2.TM_CCOEFF_NORMED)
    threshold = thresh
    loc = np.where(res >= threshold)
    pos = []
    for pt in zip(*loc[::-1]):  # Switch collumns and rows
        #cv2.rectangle(img_rgb, pt, (pt[0] + w, pt[1] + h), (255, 0, 0),1)
        pt = (pt[0]+left, pt[1]+top, w, h)
        pos.append(pt)
    try:
        # print(time.time()-start_time)
        #img = PIL.Image.fromarray(img_rgb).show()
        return pos
    except:
        return False

def imageListExist(hwnd,lista, folder, region, thresh):
    d = {}
    img_rgb = screengrab_array(hwnd,region)
    os.chdir(os.getcwd())
    for file in lista:
        template = cv2.imread('img/'+folder+'/' + file + '.png')
        if template is None:
            print("image not found: "+'img/'+folder+'/' + file + '.png')
            continue
        height, width, channels = template.shape
        h, w = template.shape[:-1]
        res = cv2.matchTemplate(img_rgb, template, cv2.TM_CCOEFF_NORMED)
        threshold = thresh
        loc = np.where(res >= threshold)
        if (len(loc[0])):
            d[file] = True
        else:
            d[file] = False
    return d

def distance(x1, y1, x2, y2):
    return ((x1-x2)**2+(y1-y2)**2)**(1/2)

def ColorDistance(rgb1, rgb2):
    # print(rgb1,rgb2)
    r, g, b = rgb1
    cr, cg, cb = rgb2
    color_diff = sqrt((r - cr)**2 + (g - cg)**2 + (b - cb)**2)
    return color_diff

def GetPixelRGBColor2(hwnd,pos):
    rect = win32gui.GetWindowRect(hwnd)
    w = abs(rect[2] - rect[0])
    h = abs(rect[3] - rect[1])
    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()
    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
    saveDC.SelectObject(saveBitMap)

    try:
        ret = win32gui.GetPixel(hwndDC, pos[0], pos[1])
        r, g, b = ret & 0xff, (ret >> 8) & 0xff, (ret >> 16) & 0xff
    except:
        r, b, g = 999, 999, 999

    mfcDC.DeleteDC()
    saveDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)
    win32gui.ReleaseDC(hwnd, hwndDC)
    win32gui.DeleteObject(saveBitMap.GetHandle())

    return (r, g, b)

def GetPixelRGBColor(hwnd,pos):
    hwndDC = win32gui.GetWindowDC(hwnd)
    try:
        ret = win32gui.GetPixel(hwndDC, pos[0], pos[1])
        r, g, b = ret & 0xff, (ret >> 8) & 0xff, (ret >> 16) & 0xff
    except:
        r, b, g = 999, 999, 999
    win32gui.ReleaseDC(hwnd, hwndDC)
    return (r, g, b)

def lookForColor(hwnd,color, region, dx=3, dy=3):
    begin_x, begin_y, end_x, end_y = region

    for x in range(begin_x, end_x, dx):
        for y in range(begin_y, end_y, dy):
            pix_color = GetPixelRGBColor(hwnd,(x, y))
            if (pix_color == color):
                return True
    return False

def lookForColors(hwnd,colors, region, dx=3, dy=3,absolute = False):
    begin_x, begin_y, end_x, end_y = region
    positions = []
   # i = 0
    for x in range(begin_x, end_x, dx):
        for y in range(begin_y, end_y, dy):
            pix_color = GetPixelRGBColor(hwnd,(x, y))
            # if (pix_color in colors):
            if (pix_color in colors):
                # print(i)
                if absolute:
                    positions.append((x,y))
                else:
                    positions.append((x-begin_x,y-begin_y))

    return positions