# region Imports
import win32gui
from ctypes import windll
import time
import pytesseract
import cv2
import imutils
import numpy as np

import PIL
import os
import keyboard as kb
from pynput import keyboard
from math import sqrt
from tkinter import BooleanVar
# data
from collections import deque
import winsound
#from natsort import natsorted
import win32com.client as comclt
from scipy.ndimage import morphology
from scipy.spatial import distance
from scipy.stats import moment
wsh= comclt.Dispatch("WScript.Shell")
pytesseract.pytesseract.tesseract_cmd = r"C:\\Tesseract-OCR\\tesseract.exe"

#LOCAL
import data
import image as img
from screen_elements import *
from window_interaction import *
from extras import *
from client_manager import *
from choose_client_gui import choose_capture_window
from main_GUI import *
from tkinter import BooleanVar,StringVar,IntVar,PhotoImage
from functools import partial
# endregion

class Bot:
    
    def __init__(self):
        self.base_directory = os.getcwd()
        self.hwnd = choose_capture_window()
        self.character_name = self.getCharacterName()
        if (self.character_name == None):
            print("You are not logged in.")
            exit()
            
        client_rect = win32gui.GetClientRect(self.hwnd)
        self.width = client_rect[2]
        self.height = client_rect[3]
        print("width: "+str(self.width) + " height: "+str(self.height))
        self.left, self.top, self.right, self.bottom = win32gui.GetWindowRect(self.hwnd)
        print("left: "+str(self.left) + " top: "+str(self.top) + " right: "+str(self.right) + " bottom: "+str(self.bottom))

        #self.height = abs(self.bottom - self.top)
        #self.width = abs(self.right - self.left)
        #green (0, 192, 0)
        #light green (96,192,96)
        #yellow (192,192,0)
        #light red (192, 0, 0)
        #red (192, 48, 48)
        #dark red (96, 0, 0)
        
        self.hp_colors =((0, 192, 0),(96,192,96),(192,192,0),(192, 0, 0),(192, 48, 48),(96, 0, 0),(192, 192, 192))
        self.low_hp_colors = ((192,192,0),(192, 0, 0),(192, 48, 48),(96, 0, 0))
        
        self.party_colors = {"cross": {"leader2" :(190, 137, 26) ,"leader": (242, 9, 3), "follower":(255, 4, 1)},
                             "check": {"leader2" :(255, 149, 16) ,"leader": (27, 254, 21), "follower":(13, 255, 11)}}
        self.party_colors_current = "cross"

        # region Scren Elements Init
        self.s_Stop = ScreenElement("Stop",self.hwnd,'stop.png',lambda w,h: (w - 200, 0 , w, int(h/2)))
        
        self.s_ActionBar = BoundScreenElement("ActionBar",self.hwnd,'action_bar_start.png','action_bar_end.png',lambda w,h: (0, int(h/4), int(w/3), h),lambda w,h: (int(2*w/3), int(h/4), w, h),(2,0))
        self.s_GameScreen = GameScreenElement("GameScreen",self.hwnd,'hp_start.png','action_bar_end.png',lambda w,h: (150, 0, 300, 150),lambda w,h: (int(2*w/3), int(h/4), w, h),(2,0))

        self.s_BattleList = ScreenWindow("BattleList",self.hwnd,'battle_list.png',2)
        self.s_Skills = ScreenWindow("Skills",self.hwnd,'skills.png',1)
        self.s_Party = ScreenWindow("Party",self.hwnd,'party_list.png',10)
        
        self.s_Map = RelativeScreenElement("Map",self.hwnd,self.s_Stop,(-118,-259,-52,-161)) #
        self.s_Bless = RelativeScreenElement("Bless",self.hwnd,self.s_Stop,(-104,-144,-135,-147))
        self.s_Buffs = RelativeScreenElement("Buffs",self.hwnd,self.s_Stop,(-118,0,-53,-1))
        self.s_Health = RelativeScreenElement("Health",self.hwnd,self.s_Stop,(-103,+18,-53,+14))
        self.s_Mana = RelativeScreenElement("Mana",self.hwnd,self.s_Stop,(-103,+31,-53,+27))
        self.s_Capacity = RelativeScreenElement("Capacity",self.hwnd,self.s_Stop,(-45,-13,-52,-15))
        self.s_WindowButtons = RelativeScreenElement("WindowButtons",self.hwnd,self.s_Stop,(-118,71,-52,164))
        
        self.ScreenElements = [self.s_Stop]
        self.BoundScreenElements = [self.s_GameScreen,self.s_ActionBar]
        self.ScreenWindows = [self.s_BattleList,self.s_Skills,self.s_Party]
        self.RelativeScreenElements = [self.s_Map,self.s_Bless,self.s_Buffs,self.s_Health,self.s_Mana,self.s_Capacity,self.s_WindowButtons]
        #element order is important
        self.ElementsLists = [self.ScreenElements,self.BoundScreenElements,self.RelativeScreenElements,self.ScreenWindows,]
        
        # endregion
        
        #GUI variables
        self.loop = True
        self.cavebot = False
        self.attack = True
        self.attack_spells = True
        self.check_monster_queue = True
        self.res = False
        self.amp_res = False
        self.follow_party = False
        self.hp_heal = True
        self.mp_heal = True
        
        self.use_haste = True
        self.use_food = True
        
        self.manage_equipment = False
        self.use_ring = False
        self.use_amulet = False
        self.loot_on_spot = False
        self.single_spot_hunting = False
        self.waypoint_folder = "test"
        self.hppc = 100
        self.mppc = 100
        
        self.player_list = {}
        self.player_list["Mateogon"] = {"vocation" :"knight", "spell_area" : 3}
        self.player_list["Mateo Gon"] = {"vocation" :"knight", "spell_area" : 3}
        self.player_list["Master Liqui"] = {"vocation" :"knight", "spell_area" : 3}
        self.player_list["Thyrion"] = {"vocation" :"paladin", "spell_area" : 5}
        self.player_list["Zane"] = {"vocation" :"sorcerer", "spell_area" : 3}
        self.player_list["Helios"] = {"vocation" :"druid", "spell_area" : 6}
        self.player_list["Kaz"] = {"vocation" :"druid", "spell_area" : 6}
        self.party_leader = "Mateogon"
        self.vocation = self.player_list[self.character_name]["vocation"]
        self.party = {}
        self.party_positions = []
        #hp history for burst damage
        self.hp_queue = deque([], maxlen=3)
        for i in range(0, 3):
            self.hp_queue.append(100)
        #monster around previous 10 seconds
        self.monster_queue_time = 0
        self.monster_queue = deque([], maxlen=10)
        for i in range(0, 10):
            self.monster_queue.append(0)
        #buff dict
        self.buffs = {}
        

        #boolean to alternate between 2 spells
        self.spell_alternate = True
        self.last_attack_time = timeInMillis()
        self.normal_delay = getNormalDelay() #for randomness
        self.exeta_res_time = time.time()
        self.exeta_res_cast_time = 3
        self.amp_res_time = time.time()
        self.amp_res_cast_time = 6
        #configs
        self.mp_thresh = 30
        self.safe_mp_thresh = self.mp_thresh + 15
        self.mana_hotkey = 'F3'
        self.hp_thresh_high = 90
        self.hp_thresh_low = 70
        self.heal_high_hotkey = 'F1'
        self.heal_low_hotkey = 'F2'
        
        #self.areaspell1_hotkey = 'F5'
        self.areaspell_area = self.player_list[self.character_name]["spell_area"]
        #self.areaspell2_hotkey = 'F6'
        self.min_monsters_around_spell = 3
        self.area_spells_hotkeys = ['F5','F6','F7']
        self.area_spells_slots = [4,5,6]
        self.target_spells_hotkeys = ['F8','F9']
        self.target_spells_slots = [7,8]
        self.utito_slot = 16
        self.utito_time = 0
        self.use_utito = True
        self.use_area_rune = False
        self.area_rune_hotkey = 'F10'
        self.area_rune_slot = 9
        #try:
            #self.monsters_around_image = False#PhotoImage(file="monsters_around.png")
        #except:
            #image = np.zeros([100,100,3],dtype=np.uint8)
            #image.fill(0) # or img[:] = 255
            #cv2.imwrite("monsters_around.png",image)
            #self.monsters_around_image = PhotoImage(file="monsters_around.png")
        self.exeta_res_hotkey = 'F11'
        self.exeta_res_slot = 10
        self.amp_res_slot = 15
        self.haste_hotkey = 'F12'
        self.haste_slot = 11
        self.eat_hotkey = '+'
        self.food_slot = 12
        self.sio_slot = 14
        self.magic_shield_slot = 16
        self.cancel_magic_shield_slot = 32
        self.magic_shield_enabled = False
        # starts at 0
        self.ring_slot = 21
        self.amulet_slot = 20
        self.weapon_slot = 18
        self.helmet_slot = 17
        self.armor_slot = 19
        self.shield_slot = 22
        self.equipment_slots = [self.weapon_slot,self.helmet_slot,self.armor_slot,self.amulet_slot,self.ring_slot,self.shield_slot]#,]
        self.last_equip_time = timeInMillis()
        self.slot_status = []
        for i in range(0,30):
            self.slot_status.append(False)
        #cavebot
        self.manual_loot = False
        self.lure = False
        self.last_walk_time = timeInMillis()
        self.last_lure_click_time = timeInMillis()
        self.kill_amount = 4
        self.kill_stop_amount = 1
        self.kill_stop_time = 120
        self.lure_amount = 2
        self.kill = False
        self.kill_start_time = time.time()
        self.mark_list = ["skull","lock","cross"]
        self.monster_positions = []
        self.monsters_around = 0
        self.key_pressed = False
        '''
        for file in os.listdir(os.getcwd() + "\\img\\map_marks"):
                fname = os.fsdecode(file)
                if fname.endswith(".png"):
                    fname = fname.replace(".png", "")
                    self.mark_list.append(fname)
        '''   
        self.current_mark_index = 0
        self.current_mark = self.mark_list[self.current_mark_index]
        self.previous_marks = {}
        self.monster_around_scale_ratio = 2
        for mark in self.mark_list:
            self.previous_marks[mark] = False
        self.chat_status_region = False
        self.current_map_image = None
        #GUI
        self.GUI = ModernBotGUI(self, self.character_name, self.vocation)

        
    def updateWindowCoordinates(self):
        maximizeWindow(self.hwnd)
        l, t, r, b = win32gui.GetWindowRect(self.hwnd)
        if (self.left, self.top, self.right, self.bottom) != (l, t, r, b):
            print("window rect changed")
            self.left, self.top, self.right, self.bottom = l, t, r, b
            self.height = abs(self.bottom - self.top)
            self.width = abs(self.right - self.left)
            self.updateAllElements()
            self.getPartyList()
        else:
            if self.checkActionbarMoved():
                print("actionbar moved, updating screen elements")
                self.updateBoundElements()
                
                
    def getCharacterName(self):
        title = win32gui.GetWindowText(self.hwnd)
        return title.split(" - ")[1]
    def checkAndDetectElements(self):
        if (self.checkAnyUndetectedElements()):
            print("elements not detected, updating")
            self.updateNotDetectedElements()
            
    def checkAnyUndetectedElements(self):
        for elem_type in self.ElementsLists:
            for elem in elem_type:
                if not elem.detected:
                    print("element not detected: "+elem.name)
                    return True
        return False
    def updateAllElements(self):
        #start = timeInMillis()
        print("Updating all elements")
        for elem_type in self.ElementsLists:
            for elem in elem_type:
                if elem_type == self.ScreenElements:
                    if not elem.update():
                        elem.update()
                elif elem_type == self.BoundScreenElements:
                    if not elem.update():
                        pass
                    else:
                        pass
                elif elem_type == self.ScreenWindows:
                    while not elem.update():
                        if elem.button_position:
                            print("clicking button for window: "+ elem.name + " position: "+str(elem.button_position))
                            self.clickWindowButton(elem.button_position)
                            time.sleep(1)
                        else:
                            print("window button position is None")
                            break      
                elif elem_type == self.RelativeScreenElements:
                    if not elem.update():
                        pass
        #print("Updating all elements took: "+str(timeInMillis()-start)+"ms")
        self.updateChatStatusButtonRegion()
    def updateNotDetectedElements(self):
        for elem_type in self.ElementsLists:
            for elem in elem_type:
                if elem_type != self.ScreenWindows:
                    if not elem.detected:
                        elem.update()
                else:
                    while not elem.detected:
                        elem.update()
                        if elem.button_position:
                            print("clicking button for window: "+ elem.name + " position: "+str(elem.button_position))
                            self.clickWindowButton(elem.button_position)
                            #time.sleep(0.5)
                        else:
                            print("window button position is None")
                            break      
                        
    def updateBoundElements(self):
        for elem in self.BoundScreenElements:
            elem.update()
            
    def checkActionbarMoved(self):
        if self.s_ActionBar.detected:
            #(117, 117, 117) at (-14,81) and (-13,81)
            #(120, 120, 120) at (-12,81)
            x,y,_,_ = self.s_ActionBar.region
            dx = -15
            dy = 75
            #dx = -14
            #dy = 82
            #x += dx
            #y += dy
            #colors = {(117, 117, 117) : [] ,(120, 120, 120) : []}
            #print("original:")
            #print((x,y))
            #print(img.GetPixelRGBColor(self.hwnd, (x,y)))
            #img.lookForColor(self.hwnd, (117,117,117) ,(x-5,y-5,x+5,y+5), 1, 1,True)
            pixel_color = img.GetPixelRGBColor(self.hwnd, (x,y))
            if pixel_color !=  (114, 115, 115):#(117,117,117):
                print(pixel_color)
                return True
        return False
    def updateChatStatusButtonRegion(self):
        #region = (self.width-300, self.height-30, self.width-100, self.height)
        region = (self.width-500, self.height-300, self.width, self.height)
        button = img.locateImage(self.hwnd,'hud/chat_enabled_button.png', region, 0.96,True)
        if (button):
            x, y, b_w, b_h = button
            x = x+region[0]-self.left
            y = y+region[1]-self.top
            self.chat_status_region = [x, y, x+(b_w*2), y+b_h]
    def clickWindowButton(self,pos):
        '''pos: starts from 1'''
        region = self.s_WindowButtons.region
        w,h = self.s_WindowButtons.getWidth(),self.s_WindowButtons.getHeight()
        
        row_amount = 5
        column = (pos - 1) % row_amount
        row = int((pos - 1) / row_amount)
        
        button_width,button_height = 19, 19 # pixels
        in_between = 3 #pixels
        distance = button_width + in_between
        area = (region[0]+column*distance, region[1]+row*distance,region[0]+column*distance+button_width, region[1]+row*distance+button_height)
        x = int((area[2]+area[0])/2)
        y = int((area[3]+area[1])/2)
        print((x,y))
        click(self.hwnd,x,y)
    
    def getActionbarSlotPosition(self,pos):
        box_width = 34
        
        y = self.s_ActionBar.region[1]
        x = self.s_ActionBar.region[0]+(box_width*(pos))+2*pos
        return (x,y)
    def clickActionbarSlot(self,pos):
        x,y = self.getActionbarSlotPosition(pos)
        print("clicking actionbar slot: "+str(pos) + " at: "+str((x,y)))
        click(self.hwnd,x,y)
    def updateActionbarSlotStatus(self):
        for i in range(0,30):
            self.slot_status[i] = self.isActionbarSlotSet(i)
    def isActionbarSlotSet(self,i):
        x,y = self.getActionbarSlotPosition(i)
        #img.screengrab_array(self.hwnd,(x,y,x+34,y+34),True)
        color = img.GetPixelRGBColor(self.hwnd,(x,y))
        if color == (16, 17, 17):
            return False
        else:
            return True
        
    def isActionbarSlotEnabled(self,i):
        
        x,y = self.getActionbarSlotPosition(i)
        img.screengrab_array(self.hwnd,(x,y,x+34,y+34))
        color = img.GetPixelRGBColor(self.hwnd,(x,y))
        if color == (114,115,115):
            return False
        elif color == (41,41,41):
            return True
        else:
            print("color of actionbar slot outside of possible values")
            print(color)
            return False
    
    def checkActionBarSlotCooldown(self,pos):

        x,y = self.getActionbarSlotPosition(pos)
        x2,y2 = x+34,y+34
        #full slot
        #image = img.screengrab_array(self.hwnd,(x,y,x2,y2),True)
        #center region to check cooldown time
        #image = img.screengrab_array(self.hwnd,(x+15,y+18,x2-15,y2-12))
        #comp = np.all(image == (223, 223, 223), axis=-1) 
        val = img.lookForColor(self.hwnd,(223,223,223),(x+15,y+18,x2-15,y2-12),1,1)

        return not val
        #if (np.count_nonzero(comp) > 0):
            #print("pos "+str(pos) + " IS on cooldown")
            #return False
        #print("pos "+str(pos) + " is NOT on cooldown")
        #return True
    def getGameRegionSquares(self):
        gr_w, gr_h = self.s_GameScreen.getWidth(),self.s_GameScreen.getHeight()
        sqr_w = int(gr_w/15)#int(gr_w/30)#
        sqr_h = int(gr_h/11)#int(gr_h/30)#
        print((sqr_w,sqr_h))
        game_region_squares = np.empty([15,11], dtype=object)
        image = self.s_GameScreen.getImage()
        for y in range(0,11):
            cv2.line(image, (0,y*sqr_h), (gr_w,y*sqr_h), (255,255,255), 1)  
            for x in range(0,15):
                cv2.line(image, (x*sqr_w,0), (x*sqr_w,gr_h), (255,255,255), 1)
                game_region_squares[x,y] = (x*sqr_w,y*sqr_h)
        #
        # img.visualize(image)
        return (game_region_squares,sqr_w,sqr_h)

    def lootAround(self,left = False):
        
        columns = self.s_GameScreen.tiles_around_player
        #print(self.s_GameScreen.tiles_around_player)
        #setForegroundWindow(self.hwnd)
        #win32api.PostMessage(self.hwnd, win32con.WM_KEYDOWN, 0x10, 0)
        region = self.s_GameScreen.getAreaAroundPlayer(3)
        #image = img.screengrab_array(self.hwnd, region, False)
        for i in range(0,len(columns)):
            positions = columns[i]
            for j in range(0,len(positions)):
                if i == 1 and j == 1:
                    pass
                else:
                    for i in range(0,5):
                        #win32api.SetCursorPos((positions[j][0],positions[j][1]))
                        if not left:
                            rclick(self.hwnd,positions[j][0],positions[j][1])
                        else:
                            click(self.hwnd,positions[j][0],positions[j][1])
                        #cv2.circle(image,(positions[j][0]-region[0],positions[j][1]-region[1]), 3, (255,0,0), -1)
                        time.sleep(0.03)
                #time.sleep(0.1)
                    
        #img.visualize_fast(image)
        #win32api.PostMessage(self.hwnd, win32con.WM_KEYUP, 0x10, 0)

    
    def getMonstersAround(self,area,test = False , test2 = False):
        #contours,_ = self.getMonstersAroundContours(area,test, test2)
        #print(len(contours[0])-1)
        #return len(contours[0])-1
        count = 0
        center = self.s_GameScreen.getRelativeCenter()
        tile_h = self.s_GameScreen.tile_h
        half_tile = tile_h/2
        radius = int(tile_h*(area*3/5))
        print("GameScreen region: "+str(self.s_GameScreen.region))
        #print("tile_h "+str(tile_h)+ " radius " +str(radius) + " area "+str(area))
        image = img.screengrab_array(self.hwnd, self.s_GameScreen.region)
        
        #cv2.circle(image,center,radius,(255,0,0),2)
        
        
        for monster in self.monster_positions:
            dist = sqrt((monster[0]-center[0])**2+(monster[1]-center[1])**2)
            if dist <= radius and dist > half_tile:
                count += 1
                #cv2.circle(image,monster,5,(0,0,255),-1)
        #img.visualize_fast(image)
        return count
    def acceptPartyInvite(self):

        shield_color = (184,154,14)
        start = timeInMillis()
        check_color = shield_color
        region = self.s_GameScreen.getAreaAroundPlayer(9)
        game_screen_region = self.s_GameScreen.region
        image = img.screengrab_array(self.hwnd,region)
        shape = image.shape
        mask = np.full([shape[0],shape[1]],False)
        black_image = np.full_like(image, [0, 0, 0])
        red, green, blue = image[:,:,2], image[:,:,1], image[:,:,0]

        r1, g1, b1 = check_color # Original value
        mask = (red == r1) & (green == g1) & (blue == b1)
        black_image[mask] = [255,255,255]
        dilate = self.dilate(black_image,2)
        dilate = cv2.cvtColor(dilate,cv2.COLOR_BGR2GRAY)
        contours,_ = cv2.findContours(dilate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        img.visualize_fast(dilate)
        print(timeInMillis()-start)
        try:
            x = contours[0][0].item(0)
            y = contours[0][0].item(1)
            
            rclick(self.hwnd,int(game_screen_region[0]+x),int(game_screen_region[1]+y+self.s_GameScreen.tile_h/2))
            time.sleep(0.2)
            #40 x 210
        except Exception as e:
            print(e)
    def getPartyAroundContours(self,area,test = True):
        
        #check_color = [(232, 3, 11),(255, 4, 1),(27, 254, 21),(13, 255, 11),(190, 137, 26)] #(242, 9, 3), (255, 22, 7)
        check_colors = self.party_colors[self.party_colors_current].values()
        region = self.s_GameScreen.getAreaAroundPlayer(area)
        image = img.screengrab_array(self.hwnd,region)
        shape = image.shape
        mask = np.full([shape[0],shape[1]],False)
        black_image = np.full_like(image, [0, 0, 0])
        red, green, blue = image[:,:,2], image[:,:,1], image[:,:,0]
        start = timeInMillis()
        for color in check_colors:
            r1, g1, b1 = color # Original value
            mask = (red == r1) & (green == g1) & (blue == b1)
            black_image[mask] = [255,255,255]
        #print(timeInMillis()-start)    
        dilate = self.dilate(black_image,2)
        dilate = cv2.cvtColor(dilate,cv2.COLOR_BGR2GRAY)
        contours = cv2.findContours(dilate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        #img.visualize_fast(dilate)
        
        #ret = len(contours)
        #if ret > len(self.party)+1:
        #    print("error more than 4 party members found")
            #img.visualize_fast(dilate)
        return contours

    #@timeit
    def getMonstersAroundContours(self,area,test = False,test2 = False):
        #start = timeInMillis()
        #test = False
        self.s_GameScreen.visualize()
        region = self.s_GameScreen.getNamesArea(area)
        print("GameScreen region: "+str(self.s_GameScreen.region))
        print("region: "+str(region))
        image = img.screengrab_array(self.hwnd,region,test)
        ar = np.asarray(image) # get all pixels
        n = self.monster_around_scale_ratio
        image = ar[::n,::n] 
        shape = image.shape
        contour_count = 0
        contour_list = []
        red, green, blue = image[:,:,2], image[:,:,1], image[:,:,0]
        #black_image_ = np.full_like(image, [0, 0, 0])
        #black_image_ = cv2.cvtColor(black_image_,cv2.COLOR_BGR2GRAY)
        #mask_ = np.full([shape[0],shape[1]],False)  
        for color in self.hp_colors:
            #mask = mask_
            #black_image = black_image_
            black_image = np.full_like(image, [0, 0, 0])
            mask = np.full([shape[0],shape[1]],False)
            r1, g1, b1 = color # Original value
            mask = (red == r1) & (green == g1) & (blue == b1)
            
            black_image[mask] = [255,255,255]
            #black_image = self.dilate(black_image,1,3)
            black_image = cv2.cvtColor(black_image,cv2.COLOR_BGR2GRAY)
            #if test:
            #    img.visualize(black_image)
            #black_image = self.open(black_image,1)
            #if test:
            #    img.visualize(black_image)
                
            black_image = self.close(black_image,2)
            
            black_image = self.open(black_image,1)
            #if test:
            #    img.visualize(black_image)
            #times[2] = timeInMillis()
            black_image = self.dilate(black_image,1)
            #if test:
                
                #print("dilate")
            #    img.visualize(black_image)
            
            
   
            contours = cv2.findContours(black_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contour_list.append(contours)
            #print(contours[1])
            #print(contours)
            #try:
            #    contour_list = np.concatenate((contour_list,contours),axis=0)
            #except:
                #pass
            contour_count+= len(contours[0])


        #return (timeInMillis()-start,contours_count)
        return contour_list
    @timeit
    def getMonstersAroundContoursOld(self, area, test=False, test2=False):
        region = self.s_GameScreen.getNamesArea(area)
        image = img.screengrab_array(self.hwnd, region, test)
        ar = np.asarray(image)  # get all pixels
        n = self.monster_around_scale_ratio
        image = ar[::n, ::n]
        contour_count = 0
        contour_list = []
        red, green, blue = image[:, :, 2], image[:, :, 1], image[:, :, 0]
        # Use Numpy's broadcasting to create a mask for each color
    
        for color in self.hp_colors:
            mask = (red == color[0]) & (green == color[1]) & (blue == color[2])
            # Use Numpy's built-in functions for morphological operations
            mask = morphology.binary_closing(mask, np.ones((2, 2)))
            mask = morphology.binary_opening(mask, np.ones((2, 2)))
            mask = morphology.binary_dilation(mask, np.ones((8, 8)))
            black_image = np.full_like(image, [0, 0, 0])
            
            black_image[mask] = [255,255,255]
            #print(type(mask))
            black_image = cv2.cvtColor(black_image,cv2.COLOR_BGR2GRAY)
            # Find contours
            contours = cv2.findContours(black_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contour_list.append(contours)
            contour_count+= len(contours[0])
        #print("contours found: "+str(contour_count))
        #print("-------------")
        return contour_list
    def dilate(self,img,iter = 1,ker = 8):
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (ker,ker))
        dilate = cv2.dilate(img, kernel, iterations=iter)
        return dilate
    def open(self,img,iter= 1, ker = 2):
        
        kernel = np.ones((ker,ker),np.uint8)
        opening = cv2.morphologyEx(img,cv2.MORPH_OPEN,kernel, iterations = iter)
        return opening
    
    def close(self,img,iter= 1,ker = 2):
        
        kernel = np.ones((ker,ker),np.uint8)
        closing = cv2.morphologyEx(img,cv2.MORPH_CLOSE,kernel, iterations = iter)
        return closing
    
    def distance_transform(self,img,mod = 0.6):
        dist_transform = cv2.distanceTransform(img,cv2.DIST_L2,5)
        #print(dist_transform.max())
        ret, thresh = cv2.threshold(dist_transform,mod*dist_transform.max(),255,0)
        thresh = np.uint8(thresh)
        return thresh
    def getHealth(self):
        cant = 0
        region = self.s_Health.region
        y = region[1]+6
        bar_width = self.s_Health.getWidth()
        delta = 4
        #counts gray pixels in a line of hp region
        for x in range(region[0], region[2], delta):
            color = img.GetPixelRGBColor(self.hwnd,(x, y))
            dist = img.ColorDistance(color, (95, 95, 95))
            if (dist <= 15):
                cant += 1
        cant *= delta
        self.hppc = 100 * (bar_width-cant)/bar_width
        #return hppc
    def getMana(self):
        cant = 0
        region = self.s_Health.region
        region = self.s_Mana.region
        y = region[1]+6
        bar_width = self.s_Mana.getWidth()
        delta = 4
        cant = 0
        #counts gray pixels in a line of mp region
        for x in range(region[0], region[2], delta):
            color = img.GetPixelRGBColor(self.hwnd,(x, y))
            dist = img.ColorDistance(color, (95, 95, 95))
            if (dist <= 15):
                cant += 1
        cant *= delta
        self.mppc = 100 * (bar_width-cant)/bar_width
        #return mppc
    def getBurstDamage(self):
        current = self.hp_queue[0]
        val = []
        for i in range(0, 3):
            val.append(self.hp_queue[i]-current)
        return max(val)
    
    def manageMagicShield(self):
        if self.vocation == "druid" or self.vocation == "sorcerer":
            if self.hppc <= self.hp_thresh_low.get() or self.getBurstDamage() > 40:
                if self.slot_status[self.magic_shield_slot] and not self.magic_shield_enabled:
                    self.clickActionbarSlot(self.magic_shield_slot)
                    self.magic_shield_enabled = True
            else:
                if self.magic_shield_enabled and self.monsterCount() == 0:
                    self.clickActionbarSlot(self.cancel_magic_shield_slot)
                    self.magic_shield_enabled = False
    
    def manageHealth(self):
        self.getHealth()
        print("hppc: "+str(self.hppc))
        self.hp_queue.pop()
        self.hp_queue.appendleft(self.hppc)

        burst = self.getBurstDamage()
        
        if (self.hppc <= self.hp_thresh_low.get() or burst > 40):
            press(self.hwnd,self.heal_high_hotkey)
        elif self.hppc < self.hp_thresh_high.get():
            press(self.hwnd,self.heal_low_hotkey)
            
    def manageMana(self):
        self.getMana()
        
        if self.isAttacking():
            thresh = self.mp_thresh.get()
        else:
            thresh = self.safe_mp_thresh
        if (self.mppc <= thresh and self.hppc >= self.hp_thresh_low.get()):
            press(self.hwnd,self.mana_hotkey)
    def castExetaRes(self):
        if time.time() - self.exeta_res_time > self.exeta_res_cast_time and self.checkActionBarSlotCooldown(self.exeta_res_slot):
            self.exeta_res_time = time.time()
            self.clickActionbarSlot(self.exeta_res_slot)
    def castAmpRes(self):
        if time.time() - self.amp_res_time > self.amp_res_cast_time and self.checkActionBarSlotCooldown(self.amp_res_slot):
            
            self.amp_res_time = time.time()
            
            self.clickActionbarSlot(self.amp_res_slot)
    def haste(self):
        if self.slot_status[self.haste_slot]:
            if not self.buffs['haste'] and not self.buffs['pz']:
                #print("hasting")
                press(self.hwnd,self.haste_hotkey)
    def eat(self):
        if self.slot_status[self.food_slot]:
            if not self.buffs['pz'] and self.buffs['hungry']:
                
                self.clickActionbarSlot(self.food_slot)
    
    def shouldUtito(self,monster_count):
        b_x, b_y,_,b_y2 = self.s_BattleList.region
        #w, h = self.s_BattleList.getWidth(),self.s_BattleList.getHeight()
        # x 3 y 22
        #found = lookForColor([(255,0,0),(255,128,128)],(x,y,w-150,h))
        

        x = b_x+26  # constant
        first_pos = b_y+30  # about mid of first square
        d = 22  # dist between boxes, 19+3
        battlelist = img.screengrab_array(self.hwnd,self.s_BattleList.region)
        count = 1
        #3 monsters -> 3 0
        #4 monster -> 3 1
        #5 monsters -> 3 2
        #6 monsters -> 4 2
        #7 monsters -> 4 3
        #8 monsters -> 5 3
        for y in range(first_pos, b_y2, d):
            if count > monster_count:
                return True
            #cv2.circle(battlelist, (26,y-b_y),1, (0,0,255), 2) 
            #img.visualize(battlelist)
            color = img.GetPixelRGBColor(self.hwnd,(x, y))
            if (color not in self.low_hp_colors):
                #print(color)res
                return False
            count+=1
        return True
    def utito(self):
        
        if time.time() - self.utito_time >= 10:
            monster_count = self.monsterCount()
            if monster_count >= 3:
                if self.shouldUtito(monster_count):
                    self.clickActionbarSlot(self.utito_slot)
                    self.utito_time = time.time()
    def shouldRes(self):
        b_x, b_y,_,b_y2 = self.s_BattleList.region
        #w, h = self.s_BattleList.getWidth(),self.s_BattleList.getHeight()
        # x 3 y 22
        #found = lookForColor([(255,0,0),(255,128,128)],(x,y,w-150,h))
        

        x = b_x+26  # constant
        first_pos = b_y+30  # about mid of first square
        d = 22  # dist between boxes, 19+3
        #battlelist = img.screengrab_array(self.hwnd,self.s_BattleList.region)
        
        
        for y in range(first_pos, b_y2, d):
            #cv2.line(battlelist, (26,y), (26,y+5), (0,255,255), 1) 
            color = img.GetPixelRGBColor(self.hwnd,(x, y))
            if (color in self.low_hp_colors):
                return True
                
       
        #img.visualize(battlelist)
    def isAttacking(self):
        b_x, b_y,_,b_y2 = self.s_BattleList.region
        #w, h = self.s_BattleList.getWidth(),self.s_BattleList.getHeight()
        # x 3 y 22
        #found = lookForColor([(255,0,0),(255,128,128)],(x,y,w-150,h))
        
        colors = [(255, 0, 0), (255, 128, 128)]
        x = b_x+3  # constant
        first_pos = b_y+24  # about mid of first square
        d = 22  # dist between boxes, 19+3
        #battlelist = img.screengrab_array(self.hwnd,self.s_BattleList.region)
        if self.vocation == "knight":
            b_y2 = first_pos+d
        for y in range(first_pos, b_y2, d):
            #cv2.line(battlelist, (3,y-b_y), (3,y-b_y+5), (255,255,255), 1) 
            color = img.GetPixelRGBColor(self.hwnd,(x, y))
            if (color in colors):
                #if (vocation == "knight" and y != first_pos):
                #    return False
                return True
        #img.visualize(battlelist)
        return False
    def monsterCount(self):
        count = 0
        _x, _y, _x2,_y2 = self.s_BattleList.region
        # x 3 y 22
        x = _x+25#
        first_pos = _y+31
        d = 22  # dist between boxes, 19+3
        prev_y = first_pos
        for y in range(first_pos, _y2, d):
                color = img.GetPixelRGBColor(self.hwnd,(x, y))
                if (color == (0,0,0)):
                    count += 1
        return count
    def checkMonsterQueue(self):
        if not self.check_monster_queue:
            return False
        for t in self.monster_queue:
            if t >= self.min_monsters_around_spell.get():
                return True
        return False
    def getBuffs(self):
        lista = ['haste', 'pz', 'hungry', 'magicshield']
        area = self.s_Buffs.region
        os.chdir(self.base_directory)
        self.buffs = img.imageListExist(self.hwnd,lista, 'buffs', area, 0.95)
    
    def clickAttack(self):
        _x, _y, _x2,_y2 = self.s_BattleList.region
        # x 3 y 22
        #found = lookForColor([(255,0,0),(255,128,128)],(x,y,w-150,h))
        x = _x+25#x = _x+12  # constant
        first_pos = _y+30  # about mid of first square
        d = 22  # dist between boxes, 19+3
        if not self.isAttacking() and not self.buffs['pz']:
            for y in range(first_pos, _y2, d):
                    color = img.GetPixelRGBColor(self.hwnd,(x, y))
                    if (color == (0,0,0)):
                        click(self.hwnd,x, y)
                        #time.sleep(0.001)
                        return
    def stopAttacking(self):
        b_x, b_y,_,b_y2 = self.s_BattleList.region
        #w, h = self.s_BattleList.getWidth(),self.s_BattleList.getHeight()
        # x 3 y 22
        #found = lookForColor([(255,0,0),(255,128,128)],(x,y,w-150,h))
        
        colors = [(255, 0, 0), (255, 128, 128)]
        x = b_x+3  # constant
        first_pos = b_y+24  # about mid of first square
        d = 22  # dist between boxes, 19+3
        #battlelist = img.screengrab_array(self.hwnd,self.s_BattleList.region)
        for y in range(first_pos, b_y2, d):
            #cv2.line(battlelist, (3,y-b_y), (3,y-b_y+5), (255,255,255), 1) 
            color = img.GetPixelRGBColor(self.hwnd,(x, y))
            if (color in colors):
                #if (vocation == "knight" and y != first_pos):
                #    return False
                click(self.hwnd,x, y)
                    
    def updateLastAttackTime(self):
        self.last_attack_time = timeInMillis()
    def newNormalDelay(self):
        self.normal_delay = getNormalDelay() 
    def walkTowardsLeader(self):
        region = self.s_GameScreen.region
        relative_center = self.s_GameScreen.getRelativeCenter()
        #image = img.screengrab_array(self.hwnd,region)
        l_x,l_y = 0,0
        for p in self.party_positions:
            is_leader = p[1]
            if is_leader:
                #print("leader found")
                l_x,l_y = p[0]
                break
        if l_x == 0 and l_y == 0:
            print("leader not found")
            return
        distance = sqrt((l_x-relative_center[0])**2+(l_y-relative_center[1])**2)
        tile_h =self.s_GameScreen.tile_h
        
        d_t = tile_h*3
        if abs(distance - d_t) < 2*tile_h/3:
            return
        d_ratio = d_t/distance
        x = int((1-d_ratio)*l_x+relative_center[0]*d_ratio)
        y = int((1-d_ratio)*l_y+relative_center[1]*d_ratio)
        #cv2.circle(image, (l_x,l_y), int(d_t), (0,255,0), 2)
        #cv2.circle(image, (x,y), 5, (255,0,0), 2)
        #cv2.line(image, (l_x,l_y), (relative_center[0],relative_center[1]), (255,0,0), 2)
        #img.visualize_fast(image)
        click(self.hwnd,region[0]+x,region[1]+y)
    def updatePartyPositions(self):
        party_contours = self.getPartyAroundContours(9)
        party_cnts = imutils.grab_contours(party_contours)
        offset_y = int(self.s_GameScreen.tile_h/2)
        if len(party_cnts) == 0:
            
            if self.party_colors_current == "cross":
                self.party_colors_current = "check"
                print("party: check")
            else:
                self.party_colors_current = "cross"
                print("party: cross")
            return
        party_positions = []
        for cur in party_cnts:
            # compute the center of the contour
            #print(cv2.contourArea(cur))
            if cv2.contourArea(cur) > 75:
                is_leader = True
            else:
                is_leader = False
            M = cv2.moments(cur)
            curX = int(M["m10"] / M["m00"])
            curY = int(M["m01"] / M["m00"]) + offset_y
            party_positions.append(((curX,curY), is_leader))  
        self.party_positions = party_positions
    #@timeit
    def updateMonsterPositions(self,test = False):
        #self.monster_positions
        
        contour_list = self.getMonstersAroundContours(9,False,False)
        #contour_list2 = self.getMonstersAroundContoursOld(9,False,False)
        
        
        if test:
            opening = img.screengrab_array(self.hwnd,self.s_GameScreen.region, True)
        
        monster_positions = []
        offset_x = int(self.s_GameScreen.tile_h/4) #offset because names are offset from tile
        offset_y = 2*offset_x#int(self.s_GameScreen.tile_h/4)#2*offset_x
        ratio = self.monster_around_scale_ratio
        for contour in contour_list:
            cnts = imutils.grab_contours(contour)
            for cur in cnts:
                # compute the center of the contour
                M = cv2.moments(cur)
                
                curX = (int(M["m10"] / M["m00"])*ratio)+offset_x
                curY = (int(M["m01"] / M["m00"])*ratio)+offset_y
                is_party = False
                for player in self.party_positions:
                    cX,cY = player[0]
                    is_leader = player[1]
                    dist = sqrt((cX-curX)**2+(cY-curY)**2)
                    #print(dist)
                    if dist < 40:
                        is_party = True
                        #if test:
                        #    if is_leader:
                        #        cv2.circle(opening,(curX,curY), 5, (0,255,0), -1)
                        #    else:
                        #        cv2.circle(opening,(curX,curY), 5, (255,0,0), -1)
                
                        break
                if not is_party:
                    monster_positions.append((curX,curY))
                    if test:
                        cv2.circle(opening,(curX,curY), 5, (0,255,0), -1)
        
        self.monster_positions = monster_positions
        if test:
            img.visualize_fast(opening)
    #@timeit
    def updateMonsterPositionsNew(self, test=False):
        contour_list = self.getMonstersAroundContours(9, False, False)

        if test:
            opening = img.screengrab_array(self.hwnd, self.s_GameScreen.region)

        monster_positions = []
        offset_x = int(self.s_GameScreen.tile_h / 4)  # Offset because names are offset from tile
        offset_y = 2 * offset_x
        ratio = self.monster_around_scale_ratio
        
        for contours in contour_list:
            cnts = imutils.grab_contours(contours)
            for cur in cnts:
                # Calculate moments
                moments = cv2.moments(cur)
                # Ensure moments['m00'] is not zero to avoid division by zero
                if moments['m00'] != 0:
                    center_x = int(moments['m10'] / moments['m00'])
                    center_y = int(moments['m01'] / moments['m00'])
                    curX = (center_x * ratio) + offset_x
                    curY = (center_y * ratio) + offset_y
                    monster_positions.append((curX, curY))
                else:
                    # If area (m00) is zero, set center to (0, 0) or handle as needed
                    monster_positions.append((0, 0))  # Optional: handle differently

        return monster_positions
    
    def useAreaRune(self,test = False):
        if not test and (self.buffs['pz'] or self.monsterCount() <= 1):
            return
        start = timeInMillis()
        #contours,opening = self.getMonstersAroundContours(9)
        #opening = cv2.cvtColor(opening,cv2.COLOR_GRAY2BGR)
        #opening = img.screengrab_array(self.hwnd,self.s_GameScreen.region)
        region = self.s_GameScreen.region
        tile = self.s_GameScreen.tile_w
        tile_radius = 3
        min_cont = False
        min_neighbors_list = []
        
        for cur in self.monster_positions:
            neighbors_list = []
            # compute the center of the contour
            curX ,curY = cur
            neighbors_list.append((curX,curY))
            for c in self.monster_positions:
                if cur is c:
                    continue
                # compute the center of the contour
                cX,cY = c
                dist = sqrt((cX-curX)**2+(cY-curY)**2)
                if dist <= tile*tile_radius:
                    neighbors_list.append((cX,cY))
                    #total_dist += dist
                
            if len(neighbors_list) > len(min_neighbors_list):
                #min_dist = total_dist
                min_cont = (curX,curY)
                min_neighbors_list = neighbors_list
                if len(min_neighbors_list) > 4:
                    break
        
        if min_cont is not False:
            x = sum([x[0] for x in min_neighbors_list])/len(min_neighbors_list)
            y = sum([x[1] for x in min_neighbors_list])/len(min_neighbors_list)
            #print((x,y))
            x = int(x)
            y = int(y)
            #cv2.circle(opening,(x,y), int(tile*tile_radius), (0,0,255), 2)
            #img.visualize_fast(opening)
            if len(min_neighbors_list) > 2:
                #pass
                #offset = int(2*tile/3)
                self.clickActionbarSlot(self.area_rune_slot)
                #self.clickActionBar(self.hwnd,self.area_rune_hotkey)
                #press(self.hwnd,self.area_rune_hotkey)
                time.sleep(0.005)
                click(self.hwnd,region[0]+x,region[1]+y)
        #print(timeInMillis()-start)
    def walkAwayFromMonsters(self):
        region = self.s_GameScreen.region
        relative_center = self.s_GameScreen.getRelativeCenter()
        image = img.screengrab_array(self.hwnd,region)
        
        amount = len(self.monster_positions)
        if amount == 0:
            return
        avg_x,avg_y = 0,0
        for monster in self.monster_positions:
            x, y = monster
            avg_x += x
            avg_y += y
        avg_x /= amount
        avg_y /= amount
        avg_x = int(avg_x)
        avg_y = int(avg_y)
        distance = sqrt((avg_x-relative_center[0])**2+(avg_y-relative_center[1])**2)
        tile_h =self.s_GameScreen.tile_h
        
        d_t = tile_h*3
        #if abs(distance - d_t) < 2*tile_h/3:
        #    return
        d_ratio = -1*d_t/distance
        x = int((1-d_ratio)*relative_center[0]+avg_x*d_ratio)
        y = int((1-d_ratio)*relative_center[1]+avg_y*d_ratio)
        cv2.circle(image, (avg_x,avg_y), 5, (0,255,0), 2)
        #cv2.circle(image, (x,y), 5, (255,0,0), 2)
        cv2.line(image, (x,y), (relative_center[0],relative_center[1]), (255,0,0), 2)
        img.visualize_fast(image)
        #click(self.hwnd,region[0]+x,region[1]+y)
        
    
    def useAreaAmmo(self):
        if self.buffs['pz'] or self.isAttacking() or self.monsterCount() == 0:
            return
        contours_list = self.getMonstersAroundContours(9)
        
        # Process each contour tuple in the list
        all_cnts = []
        for contours in contours_list:
            try:
                cnts = imutils.grab_contours(contours)
                all_cnts.extend(cnts)  # Add these contours to our working set
            except Exception as e:
                continue  # Skip invalid contours
        
        # Now use all_cnts instead of cnts in the rest of your function
        region = self.s_GameScreen.region
        tile = self.s_GameScreen.tile_w
        tile_radius = 3
        min_cont = False
        min_neighbors_list = []
        
        # Rest of your function using all_cnts instead of cnts
        for cur in all_cnts:
            neighbors_list = []
            # compute the center of the contour
            M = cv2.moments(cur)
            curX = int(M["m10"] / M["m00"])
            curY = int(M["m01"] / M["m00"])
            
            neighbors_list.append((curX,curY))
            for c in cnts:
                if cur is c:
                    continue
                # compute the center of the contour
                M = cv2.moments(c)
                cX = int(M["m10"] / M["m00"])
                cY = int(M["m01"] / M["m00"])
                dist = sqrt((cX-curX)**2+(cY-curY)**2)
                if dist <= tile*tile_radius:
                    neighbors_list.append((cX,cY))
                    #total_dist += dist
                
            if len(neighbors_list) > len(min_neighbors_list):
                #min_dist = total_dist
                min_cont = (curX,curY)
                min_neighbors_list = neighbors_list
                
                if len(min_neighbors_list) > 5:
                    break
        
        if min_cont is not False:
            if len(min_neighbors_list) > 2:
                offset = int(2*tile/3)
                #cv2.circle(opening,min_cont, int(tile*tile_radius), (255,0,0), 2)
                #
                image = img.screengrab_array(self.hwnd,region)
                pos = (region[0]+min_cont[0],region[1]+min_cont[1]+offset)
                #cv2.circle(image,(min_cont[0],min_cont[1]),7,(0,255,0),-1)
                #img.visualize_fast(image)
                rclick(self.hwnd,pos[0],pos[1])
    
    
    def attackSpells(self):

        if self.buffs['pz'] or self.monsterCount() == 0:
            return
        #start = timeInMillis()
    
        cur_sleep = timeInMillis() - self.last_attack_time
        
        if (timeInMillis() - cur_sleep > (100+self.normal_delay)):
            
            self.monsters_around = self.getMonstersAround(self.areaspell_area,False,False)
            self.monster_count = self.monsterCount()
            #print(monsters_around)
            
            if time.time() - self.monster_queue_time >= 1:
                self.monster_queue.pop()
                self.monster_queue.appendleft(self.monsters_around)
                self.monster_queue_time = time.time()
            
            if self.monsters_around > 0:
                if self.res.get(): #and self.shouldRes()
                    self.castExetaRes()
                if self.amp_res.get():
                    #print("")
                    if self.monsters_around < self.monster_count:
                        
                        self.castAmpRes()
                times[4] = timeInMillis()
                if (self.kill and self.cavebot.get()) or self.monsters_around >= self.min_monsters_around_spell.get() :#or self.checkMonsterQueue():
                    for i in range(0,len(self.area_spells_hotkeys)):
                        if self.checkActionBarSlotCooldown(self.area_spells_slots[i]):
                            #print("casting area spell")
                            press(self.hwnd,self.area_spells_hotkeys[i])
                            
                        #press(self.hwnd,hotkey)
                    '''
                    if self.spell_alternate:
                        press(self.hwnd,self.areaspell1_hotkey)
                    else:
                        press(self.hwnd,self.areaspell2_hotkey)
                    #self.spell_alternate = not self.spell_alternate
                    '''
                    self.updateLastAttackTime()
                    self.newNormalDelay() 
                elif self.monsters_around >= 1:
                    #for hotkey in self.:
                     #   press(self.hwnd,hotkey)
                    for i in range(0,len(self.target_spells_hotkeys)):
                        if self.checkActionBarSlotCooldown(self.target_spells_slots[i]):
                            #print("casting area spell")
                            press(self.hwnd,self.target_spells_hotkeys[i])
                    self.updateLastAttackTime()
                    self.newNormalDelay()
    def manageEquipment(self):
        monster_count = self.monsterCount()
        if timeInMillis() - self.last_equip_time > 200:
            for slot in self.equipment_slots:
                if self.slot_status[slot]:
                    if self.isActionbarSlotEnabled(slot):
                        if monster_count == 0 :
                            print("disabling ring")
                            self.clickActionbarSlot(slot)
                            #press(self.hwnd,self.ring_hotkey)
                            time.sleep(0.05)
                    else:
                        if monster_count > 0:
                            print("enabling ring")
                            self.clickActionbarSlot(slot)
                            #self.last_equip_time = timeInMillis()
                            #press(self.hwnd,self.ring_hotkey)
                            time.sleep(0.05)
            self.last_equip_time = timeInMillis()
            
    def isFollowing(self):
        b_x, b_y, w, h = self.s_Party.region
        # x 3 y 22
        #screengrab_array((b_x, b_y, w, h),True)

        colors = [(0, 255, 0), (128, 255, 128)]
        first_pos = b_y+24  # about mid of first square
        d = 22  # dist between boxes, 19+3
        for y in range(first_pos, h, d):
            color = img.GetPixelRGBColor(self.hwnd,(b_x, y))
            if (color in colors):
                #print("following")
                return True
        #print("not following")
        return False
    
    def manageFollow(self):
        
        if self.follow_party.get():
            #bot.walkTowardsLeader()
            if not self.isFollowing():
                if not self.isAttacking() or not self.attack:
                    self.getPartyList()
                    self.followLeader()
        else:
            if self.isFollowing():
                print("clicking stop")
                self.clickStop()
    
    def followLeader(self):
        try:
            unavailable = (128, 128, 128)
            available = (192,192,192)
            #time.sleep(character_index*0.1)
            _,_, (x_i,y_i) = win32gui.GetCursorInfo()
            x,y,_,_ = self.party[self.party_leader.get()]
            for _x in range(x-7,x+50,2):
                color = img.GetPixelRGBColor(self.hwnd,(_x,y-5))
                if color == unavailable:
                    return False
                if color == available:
                    break
                    #img.screengrab_array(self.hwnd, (x-7,y-5,x+50,y+10),True)
            #if (img.GetPixelRGBColor(self.hwnd,(x+2,y+2)) == (112,112,112)):
                #print("leader far away")
                #return
            win32api.SetCursorPos((x,y))
            rclick(self.hwnd,x,y)
            time.sleep(0.05)
            click(self.hwnd,x+20,y+34)
            win32api.SetCursorPos((x_i,y_i))
        except:
            print("wrong party leader name")
    def getPartyList(self):
        x, y, x2,y2 = self.s_Party.region
        bar_h = 4
        h_m_space = 2
        p_dist = 26
        

        region = (x+20, y+12, x2-4, y2+1)
        hp_bar_y = y+28 #black border
        hp_bar_x = x+22 #black border
        #first black pix (2,16)
        player_count = 0
        for _y in range(hp_bar_y, y2, 26):
            if (img.GetPixelRGBColor(self.hwnd,(hp_bar_x,_y)) == (0,0,0)):
                player_count+=1
        for i in range(0,player_count):
            name_region = (hp_bar_x-2,hp_bar_y-13+(i*p_dist),x2-30,hp_bar_y-1+(i*p_dist))
            name_img = img.screengrab_array(self.hwnd,name_region)
            name = img.tesser_image(name_img, 124, 255, 1, config='--psm 7')
            #print(name)
            name_found = False
            for n in self.player_list.keys():  
                if (similarString(name, n)):
                    name = n
                    name_found = True
            if not name_found:
                print("name not found: "+name)
            else:
                hp_bar_region = (hp_bar_x, hp_bar_y+(i*p_dist), x2-4, hp_bar_y+(i*p_dist)+bar_h)
                self.party[name] = hp_bar_region
        #print(self.party)
    def getPartyLeaderVitals(self):
        try:
            hp_bar = self.party[self.party_leader.get()]
            hppc = 0
            cant = 0
            y = hp_bar[1]+2
            bar_width = hp_bar[2]-hp_bar[0]
            #img.screengrab_array(hp_bar)
            delta = 5
            for x in range(hp_bar[0], hp_bar[2], delta):
                color = img.GetPixelRGBColor(self.hwnd,(x, y))
                dist = img.ColorDistance(color, (75, 75, 75))
                if (dist <= 15):
                    cant += 1
            cant *= delta
            hppc = 100 * (bar_width-cant)/bar_width
            #y = mp_bar[1]+6
            cant = 0
            #print(hppc)
            return hppc
        except:
            return 100

    def healParty(self):
        if self.vocation == "druid":
                hppc = self.getPartyLeaderVitals()
                if hppc < 80:
                    self.clickActionbarSlot(self.sio_slot)
    def cavebottest(self):
        marks = self.getClosestMarks()
        monster_count = self.monsterCount()
        kill_time = time.time() - self.kill_start_time
        walk_delay = 85
        if self.kill:
            if monster_count <= self.kill_stop_amount.get() or kill_time > self.kill_stop_time or (kill_time > 20 and self.monsters_around == 0): 
                if self.manual_loot.get():
                    for i in range(0,2):
                        self.lootAround()
                    
                self.kill = False
            else:
                #hold follow
                pass
        else:
            if monster_count >= self.kill_amount.get():
                self.kill = True
                #print("enabling kill mode")
                self.kill_start_time = time.time()
            elif monster_count >= self.lure_amount and self.lure:
                walk_delay = 500
                if timeInMillis() - self.last_lure_click_time > 250:
                    print("luring")
                    self.clickStop()
                    self.last_lure_click_time = timeInMillis()
            if len(marks) == 0:
                #print("no "+self.current_mark+ " mark found, changing to the next one")
                self.nextMark()
            else:
                index = 0
                dist, pos, _ = marks[index]  # Unpack 3 values and ignore the third one
                #print(dist)
                if dist <= 3:
                    #print("reached current mark")
                    self.updatePreviousMarks()
                    self.nextMark()
                else:
                    if timeInMillis() - self.last_walk_time > walk_delay:
                        #print(str(walk_delay))
                        #print("clicking mark")
                        click(self.hwnd,pos[0],pos[1])
                        self.last_walk_time = timeInMillis()

    def cavebot_distance(self):
        marks = self.getClosestMarks()
        monster_count = self.monsterCount()
        monsters_inside_area = self.getMonstersAround(6)
        walk_delay = 200
        walk = False
        if monsters_inside_area >= 1:
            self.stopAttacking()
            self.attack.set(value = False)
            print("stopping attack")
            walk = True
        else:
            time_passed = timeInMillis() - self.last_walk_time
            if time_passed > 100 and time_passed < 500 and monster_count >= 2:
                print("clicking stop")
                self.clickStop()
                if not self.attack.get():
                    self.attack.set(value = True)
                
        if len(marks) == 0:
            #print("no "+self.current_mark+ " mark found, changing to the next one")
            self.nextMark()
            marks = self.getClosestMarks()
    
        index = 0
        dist, pos = marks[index]
        #print(dist)
        if dist <= 3:
            print("reached current mark")
            self.updatePreviousMarks()
            self.nextMark()
        else:
            if walk and timeInMillis() - self.last_walk_time > walk_delay:
                print("walking")
            #print(str(walk_delay))
            #print("clicking mark")
                click(self.hwnd,pos[0],pos[1])
                self.last_walk_time = timeInMillis()
    def clickStop(self):
        region = self.s_Stop.getCenter()
        click(self.hwnd,region[0],region[1])                     
    def getCenterMarkImage(self):
        map_center = self.s_Map.center
        region = (map_center[0]-5, map_center[1]-5, map_center[0]+5, map_center[1]+5)
        image = img.screengrab_array(self.hwnd,region)
        return image
    def updatePreviousMarks(self):
        self.previous_marks[self.current_mark] = self.getCenterMarkImage()
    def nextMark(self):
        if self.current_mark_index >= len(self.mark_list)-1:
            self.current_mark_index = 0
        else:
            self.current_mark_index+=1
        self.current_mark = self.mark_list[self.current_mark_index]
    
    
    def getClosestMarks(self):
        compare_to_previous = True
        map_center = self.s_Map.center
        map_region = self.s_Map.region
        map_relative_center = (map_center[0]-map_region[0], map_center[1]-map_region[1])
        result = []
        discarded = []
        
        # Get the screenshot and ensure it's in the right format for OpenCV
        map_image = img.screengrab_array(self.hwnd, map_region)
        
        # Make sure map_image is a proper numpy array for OpenCV
        if map_image is not None:
            # Convert to numpy array if it's not already
            map_image_np = np.array(map_image)
        else:
            # Create a blank image if screenshot failed
            map_image_np = np.zeros((300, 300, 3), dtype=np.uint8)
        
        positions = img.locateManyImage(self.hwnd, "map_marks/"+self.current_mark+".png", map_region, 0.97)
        if not isinstance(self.previous_marks[self.current_mark], bool):
            previous = img.locateImage(self.hwnd, self.previous_marks[self.current_mark], map_region, 0.99)
        else:
            previous = False
        
        if positions:
            if len(positions) > 0:
                for pos in positions:
                    x, y = pos[0]+int(pos[2])+4, pos[1]+int(pos[2])+3
                    if self.compareMarkToPrevious((x,y), previous):
                        dist = distance.euclidean(map_relative_center, (x,y))
                        result.append((dist, (map_region[0] + x, map_region[1] + y), (x, y)))
                    else:
                        dist = distance.euclidean(map_relative_center, (x,y))
                        discarded.append((dist, (map_region[0] + x, map_region[1] + y), (x, y)))
        
        if len(result) == 0:
            result = discarded
        result.sort(reverse=False)
        
        # Draw lines for visualization with color coding
        try:
            # Draw previous mark in red if it exists
            if not isinstance(previous, bool):
                prev_x, prev_y, w, h = previous
                prev_pos = (prev_x + w + 4, prev_y + h + 3)
                cv2.line(map_image_np, map_relative_center, prev_pos, (0, 0, 255), 1)  # Red for previous mark
            
            # Draw best option in green and secondary options in blue
            for i, (_, _, (x, y)) in enumerate(result):
                if i == 0:
                    cv2.line(map_image_np, map_relative_center, (x, y), (0, 255, 0), 2)  # Green for best option (thicker)
                else:
                    cv2.line(map_image_np, map_relative_center, (x, y), (255, 0, 0), 1)  # Blue for secondary options
        except Exception as e:
            print(f"Error drawing lines: {e}")

        # Store the image for the GUI
        try:
            self.current_map_image = map_image_np.copy()
        except Exception as e:
            print(f"Error copying map image: {e}")
            self.current_map_image = np.zeros((300, 300, 3), dtype=np.uint8)
        
        return result
    
    def compareMarkToPrevious(self,pos,previous):
        #for prev in previous:
        
        if not isinstance(previous,bool):
            #print(previous)
            p_x,p_y,w,h = previous
            #print(previous)
            dist = distance.euclidean(pos,(p_x+w+4,p_y+h+3))
            
            if dist < 20:
                #print("Found: "+str(dist))
                return False
            else:
                #print(""+str(dist))
                return True
        else:
            return True
            
    def saveWaypoint(self, folder):
        directory = os.getcwd() + "\\img\\wpts\\" + folder
        dirExists = os.path.exists(directory)
        filename = "1"
        map_region = self.s_Map.region
        map_width, map_height = self.s_Map.getWidth(), self.s_Map.getHeight()
        waypoint_radius = 35
        map_waypoint = (map_region[0]+int(map_width/2)-waypoint_radius, map_region[1]+int(map_height/2)-waypoint_radius,
                map_region[0]+int(map_width/2)+waypoint_radius, map_region[1]+int(map_height/2)+waypoint_radius)
        image = img.screengrab_array(self.hwnd,map_waypoint)
        if not dirExists:
            os.makedirs(directory)
            os.chdir(directory)
            cv2.imwrite(filename+".png", image)
        else:
            os.chdir(directory)
            max = 1
            for file in os.listdir(directory):
                fname = os.fsdecode(file)
                if fname.endswith(".png"):
                    fname = fname.replace(".png", "")
                    fname = int(fname)
                    if (fname > max):
                        max = fname
            print(len(os.listdir(directory)))
            print(os.listdir(directory))
            if (len(os.listdir(directory)) > 0):
                max += 1
            print(str(max)+".png")

            if not cv2.imwrite(str(max)+".png", image):
                raise Exception("Could not write image")
    def addWaypoint(self):
        self.saveWaypoint(self.waypoint_folder.get())
    def turn(self):
        setForegroundWindow(self.hwnd)
        wsh.SendKeys("^a") 
    def enableChase(self):
        self.s_Stop.region
    
    def getNPCTrade(self):
        region = (self.width-400, 0, self.width, self.height)
        print("region",region)
        trade_bar = img.locateImage(self.hwnd,'/hud/npc_trade.png', region, 0.96)
        if not(trade_bar):
            region = (0, 0, 200, self.height)
            trade_bar = img.locateImage(self.hwnd,'/hud/npc_trade.png', region, 0.96)

        if not(trade_bar):
            print("no trade bar found")
            return False
        else:
            print("trade bar found")
            x, y, box_w, box_h = trade_bar
            region = (region[0], region[1]+y, region[2], region[3])

            ok_button = img.locateImage(self.hwnd,'/hud/npc_trade_ok.png', region, 0.96)
            print("ok_button",ok_button)
            x_ok, y_ok, ok_w, ok_h = ok_button
            time.sleep(0.1)
            sell_x_off, sell_y_off = 149, 43
            click(self.hwnd,region[0]+sell_x_off,region[1]+sell_y_off)
            #buy_pressed = img.locateImage(self.hwnd,'/hud/npc_trade_buy_pressed.png', region, 0.97)
            #if buy_pressed:
            #    x_buy, y_buy, w_buy, h_buy = buy_pressed
            #    print("clicking sell button")
            #    click(self.hwnd,region[0]+x_buy + int(w_buy/2),
            #        region[1]+y_buy+int(3*h_buy/2))
            #else:
            #    buy_unpressed = img.locateImage(self.hwnd,'/hud/npc_trade_buy_unpressed.png', region, 0.83, True)
            #    x_buy, y_buy, w_buy, h_buy = buy_unpressed
            time.sleep(0.1)
            counter = 0
            while (True):
                click(self.hwnd,region[0]+100 , region[1]+75)
                time.sleep(0.05)
                current_item_region = region[0]+x+45, region[1]+64, region[0]+159, region[1]+90
                #img.screengrab_array(self.hwnd,current_item_region,True)
                # = locateImage('npc_trade_can_sell.png', region, 0.97)
                #image = img.screengrab_array(self.hwnd,current_item_region)
                #img.visualize_fast(image)
                # visualize current image region
                can_sell = img.lookForColor(self.hwnd, (192, 192, 192), current_item_region, 2, 2)
                print("can sell: "+str(can_sell))
                if (can_sell):
                    click(self.hwnd,region[0]+x_ok + int(ok_w/2), region[1]+y_ok+int(ok_h/2))
                    time.sleep(0.05)
                else:
                    #counter += 1
                    # if (counter > 2):
                    #winsound.Beep(int(frequency/2), int(duration*2))
                    print("finished selling")
                    return True
        return True
    
    def getChatStatus(self):
        print("chat_status_region",self.chat_status_region)
        enabled = img.locateImage(self.hwnd, 'hud/chat_on.png', self.chat_status_region, 0.96)
        if (enabled):
            return True
        else:
            return False


    def setChatStatus(self,status = "on"):
        cur_status = self.getChatStatus()
        if status == 'on':
            s = True
        else:
            s = False
        if (cur_status != s):
            click(self.hwnd,self.chat_status_region[0]+10, self.chat_status_region[1]+5)
    
    def sellAllNPC(self):    
        self.setChatStatus("on")
        time.sleep(0.6)
        press(self.hwnd, 'h','i')
        time.sleep(0.6)
        press(self.hwnd,'enter')
        time.sleep(0.6)
        press(self.hwnd, 't','r','a','d','e')
        time.sleep(0.6)
        press(self.hwnd,'enter')
        time.sleep(0.5)
        count = 0
        while not self.getNPCTrade():
            if (self.isAttacking()):
                return
            print("waiting for npc trade window")
            time.sleep(0.1)
            count += 1
            if (count > 10):
                time.sleep(0.08)
                press(self.hwnd,'b', 'y', 'e')
                time.sleep(0.08)
                press(self.hwnd,'enter')
                time.sleep(0.25)
                return
        self.setChatStatus('off')

        return
    def manageKeys(self):
        if self.key_pressed == keyboard.Key.page_up:
            bot.attack.set(value = not bot.attack.get())
        elif self.key_pressed == keyboard.Key.page_down:
            bot.follow_party.set(value = not bot.follow_party.get())
        elif self.key_pressed == keyboard.Key.end:
            bot.use_area_rune.set(value = not bot.use_area_rune.get())
        elif self.key_pressed == keyboard.Key.alt_gr:
            pass
            #self.sellAllNPC()
        self.key_pressed = False
    
    def test(self):
        print("test")
        offset, error, ss_color, win_color = img.sync_screenshot_with_pixel(self.hwnd, (100, 100, 300, 300), (10, 10))
        print("Best offset:", offset)
        print("Error:", error)
        print("Screenshot color:", ss_color)
        print("Window color:", win_color)
if __name__ == "__main__":
    
    bot = Bot()
    bot.test()
    bot.updateAllElements()
    bot.updateActionbarSlotStatus()
    bot.getPartyList()
    def on_press(key):
        #print('{0} pressed'.format(key))
        bot.key_pressed = key
    listener = keyboard.Listener(on_press=on_press)
    listener.setDaemon(True)
    listener.start()
    count = 0
    total_time = 0
    times = [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
    start_time = time.time()
    
    while(True): 
        #time.sleep(1)
        bot.GUI.loop()
        bot.updateWindowCoordinates()
        bot.checkAndDetectElements()
        bot.getBuffs()
        
        #bot.cavebottest()
        #bot.getMonstersAround(6,False,True)
        #print(bot.waypoint_folder.get())
        #bot.useAreaRune()
        #bot.acceptPartyInvite()
        #bot.getPartyAroundContours(9,False)
        #img.compareImages([r"\party\follower_check.png",r"\party\leader_check.png"])
        #break
        #img.listColors("\party\leader_check.png")
        #break
        #bot.walkAwayFromMonsters()
        #bot.updateMonsterPositions()
        # execute bot.monsterCount() 1000 times and check the average time using timeInMillis()
        
        start = timeInMillis()
        current_time = int(time.time() - start_time)
        times[0] = timeInMillis()
        
        #print(current_time % 10)
        if current_time % 10 == 0:
            bot.updateActionbarSlotStatus()
            #print("looting")
            if bot.loot_on_spot.get():
                bot.lootAround(True)
        times[1] = timeInMillis()
        if bot.monsterCount() > 0:
            bot.updateMonsterPositions()
            bot.updateMonsterPositionsNew()
        times[2] = timeInMillis()
        #bot.getMonstersAround(bot.areaspell_area,False,False)
        #if len(bot.party.keys()) > 0:
            #bot.updatePartyPositions()
        
        if bot.hp_heal.get():
            bot.manageHealth()
            bot.manageMagicShield()
        times[3] = timeInMillis()
        if bot.mp_heal.get():
            bot.manageMana()
        times[4] = timeInMillis()
        if bot.attack.get():
            bot.clickAttack()
        times[5] = timeInMillis()
        if bot.use_utito:
            if bot.vocation == "knight":
                bot.utito()
        if bot.attack_spells.get():
            bot.attackSpells()
        times[6] = timeInMillis()
        if bot.cavebot.get():
            if bot.vocation == "knight":
                bot.cavebottest()
            else:
                bot.cavebot_distance()
        times[7] = timeInMillis()
        if bot.use_haste:
            bot.haste()
        if bot.use_food:
            bot.eat()
        times[8] = timeInMillis()
        if bot.manage_equipment.get():
            bot.manageEquipment()
        #if bot.follow_party.get():
        times[9] = timeInMillis()
        if bot.character_name != bot.party_leader.get():
            bot.manageFollow()
            if count%300 == 0:
                #print("updating party list")
                bot.getPartyList()
        times[10] = timeInMillis()
        if bot.key_pressed is not False:
            bot.manageKeys()
        times[11] = timeInMillis()
        if bot.use_area_rune.get() and bot.vocation != "knight":
            #if bot.monsterCount() > 0:
            if bot.vocation == "paladin":
                bot.useAreaAmmo()
            else:
                bot.useAreaRune()
        times[12] = timeInMillis()
        if len(bot.party.keys()) > 0:
            bot.healParty()
        #manageEquipment
        '''
        if bot.use_ring:
            bot.manageRing()
        if bot.use_amulet:
            bot.manageAmulet()
        '''
        #listener.join()
        
        
        count+=1
        #for i in range(0,len(times)-1):
        #    print(str(i) + " " + str(times[i+1]-times[i]))
        end = timeInMillis()
        duration = (end-start)
        #total_time+=duration
        #print("loop time: "+ str(round(duration, 3))+"ms average time: " + str(round(total_time/count, 3)) +"ms total time: " + str(round(total_time,3)) + "ms")
        
        