# region Imports
from tkinter import CENTER
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
        found_start = img.locateImage(self.hwnd, self.folder+self.search_image_start, region_start, 0.96)
        found_end = img.locateImage(self.hwnd,self.folder+self.search_image_end, region_end, 0.96)
        if not found_start or not found_end:
            self.detected = False
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
        self.areas = {3: False, 4:False,5:False,6:False,7:False,8:False,9:False} # 3x3, 4x4, 5x5, 6x6 tile areas around center tile(player)
        self.tiles_around_player = []
        super().__init__(name,hwnd)
        
    def update(self):
        game_w,game_h = self.getGameDimensions()
        region_start = self.search_region_start_function(game_w,game_h)
        region_end = self.search_region_end_function(game_w,game_h)
        found_start = img.locateImage(self.hwnd, self.folder+self.search_image_start, region_start, 0.96)
        found_end = img.locateImage(self.hwnd,self.folder+self.search_image_end, region_end, 0.96)
        if not found_start or not found_end:
            self.detected = False
            print("couldn't find GameScreen start or end")
            return False
        x1, y1, width, height = found_start
        x1 += region_start[0]-self.LEFT
        y1 += region_start[1]-self.TOP+54
        x2, y2, _, _ = found_end
        x2 += region_end[0]-self.LEFT
        y2 += region_end[1]-self.TOP-26
        pix = (0,0,0)
        flag = False
        for i in range(200, 1000):
            pix = img.GetPixelRGBColor(self.hwnd,(x1+i,y1))
            if (img.ColorDistance(pix,(22,22,22)) < 5):
                x1 = x1+i
                break
        for i in range(x1,x2,20):#fast scan to see where line ends
            pix = img.GetPixelRGBColor(self.hwnd,(i,y1))
            if (img.ColorDistance(pix,(22,22,22)) > 15):
                x2 = i
                break
        for i in range(x2,x2-30,-1):
            pix = img.GetPixelRGBColor(self.hwnd,(i,y1))
            if (img.ColorDistance(pix,(22,22,22)) < 5):
                x2 = i
                flag = True
                break
        self.region = (x1+self.start_offsets[0], y1+self.start_offsets[1], x2+self.end_offsets[0], y2+height+self.end_offsets[1])
        self.tile_h = self.getHeight()/self.tiles_y
        self.tile_w = self.getWidth()/self.tiles_x
        self.detected = flag
        self.updateAreas()
        self.updateTilesAroundPlayer()
        return flag
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
            #image = img.screengrab_array(self.hwnd,r,True)
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
        offset_x = int(self.tile_h/3) #offset because names are offset from tile
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

        window_top = img.locateImage(self.hwnd, self.folder+self.search_image, region, 0.90)
        window_bottom = img.locateManyImage(self.hwnd,self.folder+'battle_list_end.png', region, 0.85)
        if not window_top:
            region = self.left_region_function(game_w,game_h)
            window_top = img.locateImage(self.hwnd, self.folder+self.search_image, region, 0.90)
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
        
        