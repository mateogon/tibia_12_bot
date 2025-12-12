
import win32gui
import win32ui
from ctypes import windll
import pytesseract
import cv2
import numpy as np
import PIL
import os
from extras import timeit
from math import sqrt
from extras import timeInMillis
from typing import Dict
#from natsort import natsorted
pytesseract.pytesseract.tesseract_cmd = r"C:\\Tesseract-OCR\\tesseract.exe"

_CACHED_HWND = None
_CACHED_FRAME_BGR = None  # np.ndarray (H,W,3) BGR, client area
_TEMPLATE_CACHE: Dict[str, np.ndarray] = {}

def set_cached_frame(hwnd, frame_bgr):
    global _CACHED_HWND, _CACHED_FRAME_BGR
    _CACHED_HWND = hwnd
    _CACHED_FRAME_BGR = frame_bgr

def clear_cached_frame():
    global _CACHED_HWND, _CACHED_FRAME_BGR
    _CACHED_HWND = None
    _CACHED_FRAME_BGR = None

def _get_cached_region(hwnd, area):
    if _CACHED_FRAME_BGR is None or _CACHED_HWND != hwnd:
        return None
    x1, y1, x2, y2 = area
    h, w, _ = _CACHED_FRAME_BGR.shape
    x1 = max(0, min(w, x1)); x2 = max(0, min(w, x2))
    y1 = max(0, min(h, y1)); y2 = max(0, min(h, y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return _CACHED_FRAME_BGR[y1:y2, x1:x2]

def load_template(rel_path: str):
    """
    rel_path example: 'hud/stop.png' or 'buffs/haste.png'
    Returns BGR template (np.ndarray) or None.
    """
    key = rel_path.replace("\\", "/")
    t = _TEMPLATE_CACHE.get(key)
    if t is not None:
        return t
    t = cv2.imread("img/" + key)
    _TEMPLATE_CACHE[key] = t
    return t

def tesser_image(im, a, b, c, config):
    thresh = [cv2.THRESH_BINARY, cv2.THRESH_BINARY_INV,
              cv2.THRESH_TRUNC, cv2.THRESH_TOZERO, cv2.THRESH_TOZERO_INV]
    retval, img = cv2.threshold(im, a, b, thresh[c])
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    text = pytesseract.image_to_string(img, config=config)
    return text.strip()
    #

def screengrab_array(hwnd,area, show=False):
    im = area_screenshot(hwnd,area,show)
    
    if im is None:
        return None

    if show:
        visualize(im)
    return(im)

def visualize(img):
    cv2.imshow('im', img)
    if (cv2.waitKey(0) & 0xFF):
        cv2.destroyAllWindows()
        
def visualize_fast(img):
    cv2.imshow('im', img)
    
def area_screenshot(hwnd, area, show=False):
    return _get_cached_region(hwnd, area)


def compareImages(lista):
    #os.chdir(os.getcwd())
    images = []
    image_pixels = []
    for elem in lista:
        images.append(cv2.imread("img/"+elem))
    
    count = 0
    for img in images:
        rows,cols,_ = img.shape
        image_pixels.append([])
        for i in range(rows):
            for j in range(cols):
                b,g,r = img[i,j]
                image_pixels[count].append((r,g,b))
        count +=1 
    #print(image_pixels)
    intersection = image_pixels[0]
    for i in range(1,len(image_pixels)):
        intersection = list(set(intersection) & set(image_pixels[i]))
    print(intersection)

def listColors(file):
    colors = {}
    template = PIL.Image.open("img/"+file).convert('RGB')
    
    for x in range(0, template.width):
        for y in range(0, template.height):
            pix_color = template.getpixel((x,y))
            if pix_color in colors:
                colors[pix_color]+=1
            else:
                colors[pix_color]=1
    print(sorted(colors.items(), key=lambda x: x[1], reverse=True) )
    template.close()
    

def locateImage(hwnd, file, region, thresh, show=False):
    img_rgb = screengrab_array(hwnd, region, show)
    if img_rgb is None:
        return False

    if isinstance(file, str):
        template = load_template(file)
        if template is None:
            return False
    else:
        template = file

    h, w = template.shape[:2]
    
    try:
        res = cv2.matchTemplate(img_rgb, template, cv2.TM_CCOEFF_NORMED)
    except cv2.error:
        return False

    threshold = thresh
    loc = np.where(res >= threshold)
    pos = None  # Initialize pos in case loc is empty

    # FIX: Initialize the visualization image OUTSIDE the loop
    if show:
        img_rgb_vis = cv2.cvtColor(img_rgb, cv2.COLOR_BGR2GRAY)

    for pt in zip(*loc[::-1]):  # Switch columns and rows
        pos = pt
        if show:
            # Draw rectangle on the pre-initialized image
            cv2.rectangle(img_rgb_vis, pt, (pt[0] + w, pt[1] + h), (255, 0, 0), 1)

    try:
        if show:
            # Now this variable is guaranteed to exist if show=True
            visualize(img_rgb_vis)
            
        if pos is not None:
            return (pos[0], pos[1], w, h)
        else:
            return False
    except Exception as e:
        print(f"An error occurred: {e}")
        return False
        
def locateManyImage(hwnd, file, region, thresh, show=False):
    img_rgb = screengrab_array(hwnd, region)
    if img_rgb is None:
        return False

    template = load_template(file)
    if template is None:
        return False

    h, w = template.shape[:2]
    if show:
        img_rgb_vis = cv2.cvtColor( img_rgb, cv2.COLOR_BGR2GRAY)

    try:
        res = cv2.matchTemplate(img_rgb, template, cv2.TM_CCOEFF_NORMED)
    except cv2.error:
        return False

    threshold = thresh
    loc = np.where(res >= threshold)
    pos = []
    for pt in zip(*loc[::-1]):  # Switch collumns and rows
        if show:
            cv2.rectangle(img_rgb_vis, pt, (pt[0] + w, pt[1] + h), (255, 0, 0),1)
        pt = (pt[0], pt[1], w, h)
        pos.append(pt)
    try:
        if show:
            visualize(img_rgb_vis)
        return pos
    except:
        return False
    
def imageListExist(hwnd, lista, folder, region, thresh):
    d = {}
    img_rgb = screengrab_array(hwnd, region)
    if img_rgb is None:
        for f in lista: d[f] = False
        return d

    for file in lista:
        template = load_template(f"{folder}/{file}.png")
        if template is None:
            d[file] = False
            continue

        h, w = template.shape[:2]
        
        try:
            res = cv2.matchTemplate(img_rgb, template, cv2.TM_CCOEFF_NORMED)
            threshold = thresh
            loc = np.where(res >= threshold)
            if (len(loc[0])):
                d[file] = True
            else:
                d[file] = False
        except cv2.error:
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

def GetPixelRGBColor(hwnd, pos):
    cached = _get_cached_region(hwnd, (pos[0], pos[1], pos[0] + 1, pos[1] + 1))
    if cached is None:
        return (999, 999, 999)
    b, g, r = cached[0, 0]
    return (int(r), int(g), int(b))


def lookForColor(hwnd,color, region, dx=3, dy=3,test = False):
    begin_x, begin_y, end_x, end_y = region
    for x in range(begin_x, end_x, dx):
        for y in range(begin_y, end_y, dy):

            pix_color = GetPixelRGBColor(hwnd,(x, y))
            if (pix_color == color):
                    print(f"Found color {color} at ({x}, {y})")
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

def rgb(rgb):  # Function to translate color to RGB
    return "#%02x%02x%02x" % rgb

def sync_screenshot_with_pixel(hwnd, area, sample_point, offset_range=20):
    """
    Syncs the screenshot coordinates with the pixel RGB colors from GetPixelRGBColor.
    
    Parameters:
        hwnd: Window handle.
        area: Tuple (x, y, x2, y2) defining the crop region in the captured window image.
              (Coordinates here are relative to the full captured image.)
        sample_point: A tuple (x, y) within the cropped screenshot to sample (e.g., (10, 10)).
        offset_range: Range (in pixels) to test for the offset (default: ±20).
        
    Returns:
        best_offset: (dx, dy) that minimizes the difference between the screenshot's pixel color
                     and the GetPixelRGBColor output.
        best_error: The error value (sum of absolute differences) for that offset.
        screenshot_color: The color from the screenshot at sample_point.
        best_win_color: The GetPixelRGBColor output at the best offset.
    """
    # Capture screenshot of the area.
    screenshot = area_screenshot(hwnd, area, show=False)
    if screenshot is None:
        print("Screenshot capture failed.")
        return None
    
    # Note: numpy arrays use [row, col] ordering.
    screenshot_color = screenshot[sample_point[1], sample_point[0]]
    
    # Get the window's absolute coordinates.
    window_rect = win32gui.GetWindowRect(hwnd)
    # The top-left of our screenshot corresponds to (window_rect[0] + area[0], window_rect[1] + area[1])
    base_x = window_rect[0] + area[0]
    base_y = window_rect[1] + area[1]
    
    best_offset = (0, 0)
    best_error = float('inf')
    best_win_color = None
    
    # Test candidate offsets.
    for dx in range(-offset_range, offset_range + 1):
        for dy in range(-offset_range, offset_range + 1):
            test_x = base_x + sample_point[0] + dx
            test_y = base_y + sample_point[1] + dy
            win_color = GetPixelRGBColor(hwnd, (test_x, test_y))
            # Compute error (sum of absolute differences)
            error = sum(abs(int(sc) - int(wc)) for sc, wc in zip(screenshot_color, win_color))
            if error < best_error:
                best_error = error
                best_offset = (dx, dy)
                best_win_color = win_color
    
    return best_offset, best_error, tuple(screenshot_color), best_win_color
