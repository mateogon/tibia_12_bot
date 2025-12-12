# region Imports
from tkinter import CENTER
import win32gui
import operator
import image as img
from abc import ABC
import cv2
import numpy as np
# endregion

class BaseElement(ABC):
    region = (0,0,0,0) #(x,y, x+w,y+h)
    detected = False
    LEFT = -8
    TOP = -8
    folder = "hud/"
    def __init__(self, name,hwnd,search_image='',search_region_function = lambda w,h: (0,0,0,0)):
        self.name = name
        self.hwnd = hwnd
        self.search_image = search_image
        self.search_region_function = search_region_function
        self.updateSearchRegion()
        
    def getImage(self):
        return img.screengrab_array(self.hwnd,self.region)
    def visualize(self):
        if (self.detected):
            img.screengrab_array(self.hwnd,self.region,True)
        else:
            print("cannot visualize: not detected")
    def printRegion(self):
        print("(x: {0[0]} y: {0[1]} x2: {0[2]} y2: {0[3]})".format(self.region))
    def getWidth(self):
        return abs(self.region[2]-self.region[0])
    def getHeight(self):
        return abs(self.region[3]-self.region[1])
    def getCenter(self):
        return (self.region[0]+int(self.getWidth()/2),self.region[1]+int(self.getHeight()/2))
    def getRelativeCenter(self):
        return (int(self.getWidth()/2),int(self.getHeight()/2))
    def getGameDimensions(self):
        left, top, right, bottom = win32gui.GetWindowRect(self.hwnd)
        game_h = abs(bottom - top)
        game_w = abs(right - left)
        return (game_w,game_h)
    def updateSearchRegion(self):
        w,h = self.getGameDimensions()
        self.search_region = self.search_region_function(w,h)
    def setNotDetected(self):
        self.detected = False
class BoundScreenElement(BaseElement):
    def __init__(self, name,hwnd,search_image_start, search_image_end,search_region_start_function = lambda w,h: (0,0,0,0),search_region_end_function = lambda w,h: (0,0,0,0),start_offsets = (0,0), end_offsets = (0,0)):
        self.search_image_start = search_image_start
        self.search_image_end = search_image_end
        self.search_region_start_function = search_region_start_function
        self.search_region_end_function = search_region_end_function
        self.start_offsets = start_offsets
        self.end_offsets = end_offsets
        super().__init__(name,hwnd)
        
    def update(self):
        game_w,game_h = self.getGameDimensions()
        region_start = self.search_region_start_function(game_w,game_h)
        region_end = self.search_region_end_function(game_w,game_h)
        found_start = img.locateImage(self.hwnd, self.folder+self.search_image_start, region_start, 0.90)
        found_end = img.locateImage(self.hwnd,self.folder+self.search_image_end, region_end, 0.90)
        if not found_start or not found_end:
            self.detected = False
            print("couldn't find BoundScreenElement "+ self.name+ " start or end")
            return False
        else:
            print("found BoundScreenElement "+ self.name+ " start or end")
        x1, y1, width, height = found_start
        x1 += region_start[0]-self.LEFT
        y1 += region_start[1]-self.TOP
        x2, y2, _, _ = found_end
        x2 += region_end[0]-self.LEFT
        y2 += region_end[1]-self.TOP

        self.region = (x1+width+self.start_offsets[0], y1+self.start_offsets[1], x2+self.end_offsets[0], y2+height+self.end_offsets[1])
        self.detected = True
        return True
    

def find_bounding_box_black_border(
    screenshot, color_min=(14,14,14), color_max=(24,24,24), 
    visualize=False, show_mask=False, border_frac=0.6
):
    mask = np.all((screenshot >= color_min) & (screenshot <= color_max), axis=2)
    H, W = mask.shape

    if show_mask:
        mask_vis = (mask.astype(np.uint8)) * 255
        mask_vis = cv2.cvtColor(mask_vis, cv2.COLOR_GRAY2BGR)
        cv2.imshow("DEBUG: Border Color Mask", mask_vis)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    # 1. Find the "border row" with most border pixels (top border)
    row_sum = mask.sum(axis=1)
    top_row = np.argmax(row_sum)
    # The left/right ends of the top border
    top_border_indices = np.where(mask[top_row])[0]
    left = top_border_indices[0]
    right = top_border_indices[-1]

    # 2. Find the "border column" with most border pixels (left border)
    col_sum = mask.sum(axis=0)
    left_col = np.argmax(col_sum)
    # The top/bottom ends of the left border
    left_border_indices = np.where(mask[:, left_col])[0]
    top = left_border_indices[0]
    bottom = left_border_indices[-1]

    # 3. For robustness, check the opposite borders:
    # Bottom border: look at the row with max sum near the bottom
    bottom_row = len(row_sum) - 1 - np.argmax(row_sum[::-1])
    bottom_border_indices = np.where(mask[bottom_row])[0]
    left2 = bottom_border_indices[0]
    right2 = bottom_border_indices[-1]

    # Right border: look at the col with max sum near the right
    right_col = len(col_sum) - 1 - np.argmax(col_sum[::-1])
    right_border_indices = np.where(mask[:, right_col])[0]
    top2 = right_border_indices[0]
    bottom2 = right_border_indices[-1]

    # 4. Final box is intersection of all
    final_left = min(left, left2)
    final_right = max(right, right2)
    final_top = min(top, top2)
    final_bottom = max(bottom, bottom2)

    if visualize:
        vis_img = screenshot.copy()
        cv2.rectangle(vis_img, (final_left, final_top), (final_right, final_bottom), (0,255,0), 2)
        cv2.imshow("Detected GameScreen Region", vis_img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    return final_left, final_top, final_right+1, final_bottom+1


class GameScreenElement(BaseElement):
    tiles_x = 15 #number of screen tiles in x
    tiles_y = 11 #number of screen tiles in y
    tile_h = 72 # tile height, default 72, calculated on update
    tile_w = 72 # tile width, default 72, calculated on update
    def __init__(self, name,hwnd,search_image_start, search_image_end,search_region_start_function = lambda w,h: (0,0,0,0),search_region_end_function = lambda w,h: (0,0,0,0),start_offsets = (0,0), end_offsets = (0,0)):
        self.search_image_start = search_image_start
        self.search_image_end = search_image_end
        self.search_region_start_function = search_region_start_function
        self.search_region_end_function = search_region_end_function
        self.start_offsets = start_offsets
        self.end_offsets = end_offsets
        self.areas = {3: False, 4:False,5:False,6:False,7:False,8:False,9:False}
        self.tiles_around_player = []
        
        # A place to store our stable check pixels.
        self.border_check_pixels = []

        super().__init__(name,hwnd)

    def _is_color_in_range(self, color):
        """
        Helper: Returns True if the color is within the valid Border Dark Grey range.
        ALL channels (R, G, and B) must be within 15-30.
        """
        r, g, b = color
        min_val, max_val = 15, 30
        return (min_val <= r <= max_val) and \
               (min_val <= g <= max_val) and \
               (min_val <= b <= max_val)

    def _update_border_check_pixels(self, visualize_check=False):
        """
        Stores 'Inside' points (Must be Border) and 'Outside' points (Must NOT be Border).
        """
        self.border_check_pixels.clear()
        if not self.detected:
            return

        x1, y1, x2, y2 = self.region
        width = x2 - x1
        height = y2 - y1
        off = 2 # Offset for outside pixels

        # --- Define Points: (Coordinates, Should_Be_Border_Color) ---
        
        # 1. POSITIVE ANCHORS (Must be Grey)
        self.border_check_pixels.append( ((x1, y1), True) )
        self.border_check_pixels.append( ((x1 + int(width / 2), y1), True) )
        self.border_check_pixels.append( ((x1, y1 + int(height / 2)), True) )

        # 2. NEGATIVE ANCHORS (Must NOT be Grey)
        self.border_check_pixels.append( ((x1 - off, y1), False) ) # Left of corner
        self.border_check_pixels.append( ((x1, y1 - off), False) ) # Above corner

        # --- VISUALIZATION LOGIC (FIXED) ---
        if visualize_check and self.detected:
            # We must capture the screenshot here to pass it to the debug function
            padding = 5
            c_left = x1 - padding
            c_top = y1 - padding
            c_right = x2 + padding
            c_bottom = y2 + padding
            
            screenshot = img.screengrab_array(self.hwnd, (c_left, c_top, c_right, c_bottom))
            
            if screenshot is not None:
                self.show_border_debug(screenshot, c_left, c_top)

    def show_border_debug(self, screenshot, x_offset, y_offset):
        """
        Visualizes the data strictly from the screenshot used for logic.
        """
        if screenshot is None: return

        # Create mask: White = Border Color, Black = Background
        lower_bound = np.array([15, 15, 15]) 
        upper_bound = np.array([30, 30, 30])
        mask = cv2.inRange(screenshot, lower_bound, upper_bound)
        debug_view = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

        for coords, should_be_border in self.border_check_pixels:
            # Convert absolute coord to relative image coord
            rel_x = coords[0] - x_offset
            rel_y = coords[1] - y_offset
            
            # Safety check to ensure we draw inside bounds
            if 0 <= rel_x < debug_view.shape[1] and 0 <= rel_y < debug_view.shape[0]:
                color = (0, 255, 0) if should_be_border else (0, 0, 255)
                cv2.circle(debug_view, (rel_x, rel_y), 2, color, -1)

        cv2.imshow("Border Integrity Check", debug_view)
        cv2.waitKey(1)

    def has_been_resized(self):
        """
        Checks border integrity using a fresh screenshot to match the visualization 1:1.
        """
        if not self.border_check_pixels:
            return True

        # 1. Define capture area. We pad slightly to catch the 'Outside' points.
        padding = 5
        x1, y1, x2, y2 = self.region
        
        # Calculate the region to grab (Absolute coordinates relative to window)
        capture_left = x1 - padding
        capture_top = y1 - padding
        capture_right = x2 + padding
        capture_bottom = y2 + padding
        
        # 2. Grab the image ONCE. This is what the bot effectively 'sees'.
        screenshot = img.screengrab_array(self.hwnd, (capture_left, capture_top, capture_right, capture_bottom))
        
        if screenshot is None:
            return False # Can't check, assume fine or handle error

        # 3. Visualize EXACTLY this data
        #self.show_border_debug(screenshot, capture_left, capture_top)

        import time
        if not hasattr(self, '_last_resize_debug_time'):
            self._last_resize_debug_time = 0
        
        # 4. Check the pixels in the NumPy array (much faster than GetPixel calls)
        # Note: screenshot is [row, col] -> [y, x]
        for coords, should_be_border in self.border_check_pixels:
            # Convert absolute coords to relative array indices
            img_y = coords[1] - capture_top
            img_x = coords[0] - capture_left
            
            # Boundary check
            if not (0 <= img_y < screenshot.shape[0] and 0 <= img_x < screenshot.shape[1]):
                continue

            # Get pixel color (OpenCV is BGR)
            b, g, r = screenshot[img_y, img_x]
            
            min_val, max_val = 15, 30
            is_border_color = (min_val <= r <= max_val) and \
                              (min_val <= g <= max_val) and \
                              (min_val <= b <= max_val)
            
            # Logic Check
            if should_be_border and not is_border_color:
                if (time.time() - self._last_resize_debug_time) > 0.5:
                    print(f"[RESIZE] Point {coords} LOST border. Got (R:{r},G:{g},B:{b})")
                    self._last_resize_debug_time = time.time()
                return True

            if not should_be_border and is_border_color:
                if (time.time() - self._last_resize_debug_time) > 0.5:
                    print(f"[RESIZE] Point {coords} GAINED border. Got (R:{r},G:{g},B:{b})")
                    self._last_resize_debug_time = time.time()
                return True

        return False
    def force_window_refresh(self):
        """
        Force the window to redraw, helping sync the system copy with live version.
        """
        import win32con
        import time
        try:
            # Send a paint message to force redraw
            win32gui.SendMessage(self.hwnd, win32con.WM_PAINT, 0, 0)
            # Small delay to allow processing
            time.sleep(0.01)
            
            # Alternative: Invalidate a small rect to trigger refresh
            rect = win32gui.GetWindowRect(self.hwnd)
            win32gui.InvalidateRect(self.hwnd, (0, 0, 10, 10), True)
            time.sleep(0.01)
        except:
            pass  # If it fails, continue without forcing refresh

    def update(self):
        visualize_resize_check = False
        game_w, game_h = self.getGameDimensions()
        region_start = self.search_region_start_function(game_w, game_h)
        region_end = self.search_region_end_function(game_w, game_h)
        found_start = img.locateImage(self.hwnd, self.folder+self.search_image_start, region_start, 0.96)
        found_end = img.locateImage(self.hwnd, self.folder+self.search_image_end, region_end, 0.96)
        if not found_start or not found_end:
            self.detected = False
            self.border_check_pixels.clear()
            print("couldn't find GameScreen start or end")
            return False

        x1, y1, width, height = found_start
        x1 += region_start[0] - self.LEFT
        y1 += region_start[1] - self.TOP + 54
        x2, y2, _, _ = found_end
        x2 += region_end[0] - self.LEFT
        y2 += region_end[1] - self.TOP - 26

        candidate_area = (x1, y1, x2, y2+height)
        screenshot = img.screengrab_array(self.hwnd, candidate_area)

        try:
            left, top, right, bottom = find_bounding_box_black_border(
                screenshot, color_min=(14,14,14), color_max=(24,24,24), visualize=False
            )
        except IndexError:
            print("[ERROR] Failed to find bounding box border in candidate area.")
            self.detected = False
            self.border_check_pixels.clear()
            return False

        abs_left = x1 + left
        abs_top = y1 + top
        abs_right = x1 + right
        abs_bottom = y1 + bottom

        self.region = (abs_left, abs_top, abs_right, abs_bottom)
        self.tile_h = self.getHeight() / self.tiles_y
        self.tile_w = self.getWidth() / self.tiles_x
        self.detected = True
        
        # --- Re-including the previously omitted methods ---
        self.updateAreas()
        self.updateTilesAroundPlayer()
        
        # After a successful update, store the new ground truth.
        self._update_border_check_pixels(visualize_check=visualize_resize_check)
        
        return True

    # --- ALL ORIGINAL HELPER METHODS ARE NOW INCLUDED ---

    def updateAreas(self):
        center_tile = (7,5)
        for i in range(1,8):
            if i != 7:
                x,y = center_tile
                start = (x-i,y-i) #top left
                end = (x+i+1,y+i+1) #bottom right
                r = (start[0]*self.tile_w ,start[1]*self.tile_h, end[0]*self.tile_w ,end[1]*self.tile_h)
                r = (int(self.region[0]+r[0]) ,int(self.region[1]+ r[1]) ,int(self.region[0]+ r[2]),int(self.region[1]+r[3]))
                self.areas[i+2]=r
            else:
                self.areas[i+2] = self.region

    def updateTilesAroundPlayer(self):
        region = self.getAreaAroundPlayer(3)
        tile_h = self.tile_h
        tile_w = self.tile_w
        self.tiles_around_player = []
        for x in range(0,3):
            self.tiles_around_player.append([])
            for y in range(0,3):
                self.tiles_around_player[x].append((region[0]+int(x*tile_w+int(tile_w/2)),region[1]+int(y*tile_h+int(tile_h/2))))
    
    def getNamesArea(self,area):
        r = self.areas[area]
        offset_x = int(self.tile_h/3)
        offset_y = offset_x*2
        r = (r[0],r[1]-offset_x,r[2],r[3]-offset_y)
        return r
    
    def getTileDimensions(self):
        return (self.tile_w, self.tile_h)
    
    def getAreaAroundPlayer(self,area):
        return self.areas[area]
    
class ScreenElement(BaseElement):
    def __init__(self, name,hwnd,search_image,search_region_function = lambda w,h: (0,0,0,0),x_offset = 0,y_offset = 0,elem_width = 0, elem_height = 0):
        self.x_offset = x_offset
        self.y_offset = y_offset
        self.elem_width = elem_width
        self.elem_height = elem_height
        super().__init__(name,hwnd,search_image,search_region_function)
        
    def update(self):
        self.updateSearchRegion()
        print("searching for {} in region {}".format(self.name,self.search_region))
        found = img.locateImage(self.hwnd, self.folder+self.search_image, self.search_region, 0.96)
        if found:
            x2, y2, img_w , img_h = found
            if (self.elem_width == 0):
                self.elem_width = img_w
                self.elem_height = img_h
            x = self.search_region[0] + x2 + self.x_offset - self.LEFT
            y = self.search_region[1] + y2 + self.y_offset - self.TOP
            self.region = (x, y, x+self.elem_width, y+self.elem_height)
            self.detected = True
            return True
        else:
            print("couldn't find {} position".format(self.name))
            self.detected = False
            return False
        
class ScreenWindow(ScreenElement):
    right_region_function = lambda self,w,h: (w - 400, 0 , w, h)
    left_region_function = lambda self,w,h: (0, 0 , 200, h)
    
    def __init__(self, name,hwnd,search_image,button_position=None):
        self.button_position = button_position
        super().__init__(name,hwnd,search_image)
        
    def update(self):
        game_w,game_h = self.getGameDimensions()
        region = self.right_region_function(game_w,game_h)
        #img.visualize_fast(img.area_screenshot(self.hwnd,region))

        window_top = img.locateImage(self.hwnd, self.folder+self.search_image, region, 0.85)
        window_bottom = img.locateManyImage(self.hwnd,self.folder+'battle_list_end.png', region, 0.85)
        if not window_top:
            region = self.left_region_function(game_w,game_h)
            window_top = img.locateImage(self.hwnd, self.folder+self.search_image, region, 0.85)
            window_bottom = img.locateManyImage(self.hwnd,self.folder+'battle_list_end.png', region, 0.85)
        if not window_top:
            print("couldn't find {} on screen".format(self.name))
            self.detected = False
            return False
        else:
            closest = None
            if (len(window_bottom) > 1):
                dist = 99999
                for end in window_bottom:
                    y_dif = end[1]-window_top[1]
                    if (y_dif < 0):
                        continue
                    if (y_dif < dist):
                        dist = y_dif
                        closest = end
            else:
                closest = window_bottom[0]
            window_bottom = closest
            top_x, top_y, top_width, top_height = window_top
            bottom_x,bottom_y,bottom_width,bottom_height = window_bottom
            self.region = (region[0]+top_x - self.LEFT, region[1] + top_y - self.TOP,
                           region[0]+top_x + top_width - self.LEFT, region[1] + bottom_y + bottom_height - self.TOP)
            self.detected = True
            print("found {} on screen".format(self.name))
            return True

class RelativeScreenElement(BaseElement):
    def __init__(self,name,hwnd,element,offsets):
        self.element = element
        self.offsets = offsets
        self.center = False
        super().__init__(name,hwnd)
        
    def update(self):
        self.region = tuple(map(operator.add, self.element.region, self.offsets))
        self.detected = self.element.detected
        self.center = self.getCenter()
        return self.detected
    #to test different offsets
    def add_offset(self,mod_offsets):
        self.offsets = tuple(map(operator.add, self.offsets, mod_offsets))
        self.update()
        
        