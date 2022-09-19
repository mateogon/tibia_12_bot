# region Imports
import win32gui
import operator
import image as img
from abc import ABC
# endregion

class BaseElement(ABC):
    region = (0,0,0,0) #(x,y, x+w,y+h)
    detected = False
    LEFT = -8
    TOP = -8
    def __init__(self, name,hwnd,search_image='',search_region_function = lambda w,h: (0,0,0,0)):
        self.name = name
        self.hwnd = hwnd
        self.search_image = search_image
        self.search_region_function = search_region_function
        self.updateSearchRegion()
        
    def getImage(self):
        return img.screengrab_array(self.hwnd,self.region)
    def visualize(self):
        img.screengrab_array(self.hwnd,self.region,True)
    def printRegion(self):
        print("(x: {0[0]} y: {0[1]} x2: {0[2]} y2: {0[3]})".format(self.region))
    def getWidth(self):
        return abs(self.region[2]-self.region[0])
    def getHeight(self):
        return abs(self.region[3]-self.region[1])
    def getGameDimensions(self):
        left, top, right, bottom = win32gui.GetWindowRect(self.hwnd)
        game_h = abs(bottom - top)
        game_w = abs(right - left)
        return (game_w,game_h)
    def updateSearchRegion(self):
        w,h = self.getGameDimensions()
        self.search_region = self.search_region_function(w,h)
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
        found_start = img.locateImage(self.hwnd, self.search_image_start, region_start, 0.96)
        found_end = img.locateImage(self.hwnd,self.search_image_end, region_end, 0.96)
        if not found_start or not found_end:
            print("couldn't find BoundScreenElement "+ self.name+ " start or end")
            return False
        x1, y1, width, height = found_start
        x1 += region_start[0]-self.LEFT
        y1 += region_start[1]-self.TOP
        x2, y2, _, _ = found_end
        x2 += region_end[0]-self.LEFT
        y2 += region_end[1]-self.TOP

        self.region = (x1+width+self.start_offsets[0], y1+self.start_offsets[1], x2+self.end_offsets[0], y2+height+self.end_offsets[1])
        self.detected = True
        return True
class ScreenElement(BaseElement):
    def __init__(self, name,hwnd,search_image,search_region_function = lambda w,h: (0,0,0,0),x_offset = 0,y_offset = 0,elem_width = 0, elem_height = 0):
        self.x_offset = x_offset
        self.y_offset = y_offset
        self.elem_width = elem_width
        self.elem_height = elem_height
        super().__init__(name,hwnd,search_image,search_region_function)
        
    def update(self):
        found = img.locateImage(self.hwnd, self.search_image, self.search_region, 0.96)
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
    right_region_function = lambda self,w,h: (w - 200, 0 , w, h)
    left_region_function = lambda self,w,h: (0, 0 , 200, h)
    
    def __init__(self, name,hwnd,search_image,button_position=None):
        self.button_position = button_position
        super().__init__(name,hwnd,search_image)
        
    def update(self):
        game_w,game_h = self.getGameDimensions()
        region = self.right_region_function(game_w,game_h)
        window_top = img.locateImage(self.hwnd, self.search_image, region, 0.96)
        window_bottom = img.locateManyImage(self.hwnd,'battle_list_end.png', region, 0.94)
        if not window_top:
            region = self.left_region_function(game_w,game_h)
            window_top = img.locateImage(self.hwnd, self.search_image, region, 0.96)
            window_bottom = img.locateManyImage(self.hwnd,'battle_list_end.png', region, 0.94)
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
            return True

class RelativeScreenElement(BaseElement):
    def __init__(self,name,hwnd,element,offsets):
        self.element = element
        self.offsets = offsets
        super().__init__(name,hwnd)
        
    def update(self):
        self.region = tuple(map(operator.add, self.element.region, self.offsets))
        return True
        