# region Imports
import win32gui,win32api
from ctypes import windll
import time
import json
import datetime
import cv2
import imutils
import numpy as np

import PIL
import os
import keyboard as kb
from pynput import keyboard
from math import sqrt
# data
from collections import deque
#from natsort import natsorted
import win32com.client as comclt
from scipy.ndimage import morphology
from scipy.spatial import distance
wsh= comclt.Dispatch("WScript.Shell")

#LOCAL
import data
import image as img
import detect_monsters as dm
import config_manager as cm
from screen_elements import *
from window_interaction import *
from extras import *
from choose_client_gui import choose_capture_window
from main_GUI import *
from tkinter import BooleanVar,StringVar,IntVar,PhotoImage
from functools import partial
from bg_capture import BackgroundFrameGrabber

# endregion

class Bot:
    
    def __init__(self):
        self.base_directory = os.getcwd()
        self.hwnd = choose_capture_window()
        self.bg = BackgroundFrameGrabber(self.hwnd, max_fps=50)
        self.character_name = self.getCharacterName()
        if (self.character_name == None):
            print("You are not logged in.")
            exit()
            
        client_rect = win32gui.GetClientRect(self.hwnd)
        self.width = client_rect[2]
        self.height = client_rect[3]
        self.left, self.top, self.right, self.bottom = win32gui.GetWindowRect(self.hwnd)

        #self.height = abs(self.bottom - self.top)
        #self.width = abs(self.right - self.left)
        #green (0, 192, 0)
        #light green (96,192,96)
        #yellow (192,192,0)
        #light red (192, 0, 0)
        #red (192, 48, 48)f
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
        self.action_bar_anchor_pos = None # Will store the stable (x, y) of the action bar's start image.
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
        self.use_food = False
        
        self.manage_equipment = False
        self.use_ring = False
        self.use_amulet = False
        self.loot_on_spot = False
        self.single_spot_hunting = False
        self.waypoint_folder = "test"
        self.hppc = 100
        self.mppc = 100
        
        self.ElementsLists = [self.ScreenElements,self.BoundScreenElements,self.RelativeScreenElements,self.ScreenWindows,]
        self.action_bar_anchor_pos = None 

        # --- NEW CONFIGURATION SYSTEM ---
        # 1. Initialize Config Manager
        self.config = cm.ConfigManager()
        
        # 2. Identify Character & Load Data
        self.character_name = self.getCharacterName()
        if self.character_name is None:
            print("You are not logged in.")
            exit()

        char_data = self.config.get_character(self.character_name)
        self.vocation = char_data["vocation"]
        self.areaspell_area = char_data["spell_area"]
        self.party_leader = char_data.get("party_leader", "") # Default to empty if not set
        
        # 3. Load Vocation Preset
        self.preset = self.config.get_preset(self.vocation)
        
        # 4. LOAD SLOTS (The Action Bar mapping)
        self.slots = self.preset["slots"]
        
        # Load Spell Rotations (Lists of slots)
        self.area_spells_slots = self.preset["spells"]["area_slots"]
        self.target_spells_slots = self.preset["spells"]["target_slots"]
        
        # 5. LOAD SETTINGS (With defaults if missing)
        s = self.preset["settings"]
        
        # -- Thresholds --
        self.hp_thresh_high = int(s.get("hp_thresh_high", 90))
        self.hp_thresh_low = int(s.get("hp_thresh_low", 70))
        self.mp_thresh = int(s.get("mp_thresh", 30))
        
        # -- Combat Logic --
        self.min_monsters_around_spell = int(s.get("min_monsters_spell", 1))
        self.min_monsters_for_rune = int(s.get("min_monsters_rune", 1))
        self.attack_spells = s.get("attack_spells", True)
        self.res = s.get("res", False)
        self.amp_res = s.get("amp_res", False)
        self.use_utito = s.get("use_utito", False)
        self.use_area_rune = s.get("use_area_rune", False)
        
        # -- Toggles --
        self.hp_heal = True
        self.mp_heal = True
        self.loop = True
        self.attack = True
        self.cavebot = False
        self.follow_party = False
        self.manual_loot = False
        self.loot_on_spot = False
        self.manage_equipment = False
        self.show_area_rune_target = True
        
        # -- Internal Timers & Queues --
        self.party = {}
        self.party_positions = []
        self.monster_positions = []
        self.monsters_around = 0
        
        # HP History (Burst Calc)
        self.hp_queue = deque([], maxlen=3)
        for i in range(0, 3): self.hp_queue.append(100)
            
        # Monster History
        self.monster_queue_time = 0
        self.monster_queue = deque([], maxlen=10)
        for i in range(0, 10): self.monster_queue.append(0)
            
        self.buffs = {}
        self.last_attack_time = timeInMillis()
        
        # Delays
        self.normal_delay = getNormalDelay()
        self.delays = DelayManager(default_jitter_ms_fn=getNormalDelay)
        self.attack_click_delay_ms = 120
        self.delays.set_default("attack_click", self.attack_click_delay_ms)
        self.exeta_res_cast_time = 3
        self.amp_res_cast_time = 6
        self.delays.set_default("attack_click", 120)
        self.delays.set_default("area_rune", 1100)
        self.delays.set_default("equip_cycle", 200)
        self.delays.set_default("lure_stop", 250)
        self.delays.set_default("follow_retry", 2500)
        self.delays.set_default("exeta_res", 3000)
        self.delays.set_default("amp_res", 6000)
        self.delays.set_default("utito", 10000)
        
        # Trigger initial delays
        self.delays.trigger("equip_cycle")
        self.delays.trigger("lure_stop")
        self.delays.trigger("walk", base_ms=200)

        # Configs that didn't fit in preset or are global
        self.check_spell_cooldowns = True
        self.check_monster_queue = True
        self.area_rune_delay_ms = 1100
        self.area_rune_target_click_delay_s = 0.08
        self.safe_mp_thresh = self.mp_thresh + 15
        
        # Equipment Slot Definitions (Fixed by Game Client)
        self.weapon_slot = self.slots.get("weapon", 18)
        self.helmet_slot = self.slots.get("helmet", 17)
        self.armor_slot = self.slots.get("armor", 19)
        self.shield_slot = self.slots.get("shield", 22)
        self.amulet_slot = self.slots.get("amulet", 20)
        self.ring_slot = self.slots.get("ring", 21)
        self.equipment_slots = [self.weapon_slot, self.helmet_slot, self.armor_slot, self.amulet_slot, self.ring_slot, self.shield_slot]
        self.magic_shield_enabled = False
        self.slot_status = [False] * 30
        
        # Cavebot defaults
        self.kill_amount = 5
        self.kill_stop_amount = 1
        self.kill_stop_time = 120
        self.lure_amount = 2
        self.kill = False
        self.kill_start_time = time.time()
        self.lure = False
        self.waypoint_folder = "test"
        
        # Marks
        self.mark_list = ["skull", "lock", "cross"]
        self.current_mark_index = 0
        self.current_mark = self.mark_list[self.current_mark_index]
        self.previous_marks = {mark: False for mark in self.mark_list}
        
        self.chat_status_region = False
        self.current_map_image = None
        self.key_pressed = False

        # GUI Init
        self.GUI = ModernBotGUI(self, self.character_name, self.vocation)
        self.follow_retry_delay = 2.5

        # Centralized timers (seed throttles to avoid immediate spam on start)
        self.delays.set_default("area_rune", self.area_rune_delay_ms, jitter_ms_fn=getNormalDelay)
        self.delays.set_default("equip_cycle", 200)
        self.delays.set_default("lure_stop", 250)
        self.delays.set_default("follow_retry", int(self.follow_retry_delay * 1000))
        self.delays.set_default("exeta_res", int(self.exeta_res_cast_time * 1000))
        self.delays.set_default("amp_res", int(self.amp_res_cast_time * 1000))
        self.delays.set_default("utito", 10_000)

        self.delays.trigger("equip_cycle")
        self.delays.trigger("lure_stop")
        self.delays.trigger("walk", base_ms=200)
        self.delays.trigger("exeta_res")
        self.delays.trigger("amp_res")

    def _bool_value(self, v):
        try:
            return bool(v.get())
        except Exception:
            return bool(v)

    def _visualize_area_rune_target(self, rel_x, rel_y, neighbors_rel=None, radius_px=None):
        if not self._bool_value(self.show_area_rune_target):
            return
        region = self.s_GameScreen.region
        frame = img.screengrab_array(self.hwnd, region)
        if frame is None:
            return
        vis = np.ascontiguousarray(frame, dtype=np.uint8)

        x = int(rel_x)
        y = int(rel_y)
        cv2.drawMarker(vis, (x, y), (0, 0, 255), markerType=cv2.MARKER_CROSS, markerSize=20, thickness=2)
        if radius_px is not None:
            cv2.circle(vis, (x, y), int(radius_px), (255, 0, 0), 1)
        if neighbors_rel:
            for nx, ny in neighbors_rel:
                if nx == 0 and ny == 0:
                    continue
                cv2.circle(vis, (int(nx), int(ny)), 3, (0, 255, 0), -1)

        cv2.imshow("Area Rune Target", vis)
        cv2.waitKey(1)
        
    def updateFrame(self):
        ok = self.bg.update()
        if ok and self.bg.frame_bgr is not None:
            img.set_cached_frame(self.hwnd, self.bg.frame_bgr)

    def updateWindowCoordinates(self):
        maximizeWindow(self.hwnd)
        l, t, r, b = win32gui.GetWindowRect(self.hwnd)
        if (self.left, self.top, self.right, self.bottom) != (l, t, r, b):
            print("window rect changed")
            self.left, self.top, self.right, self.bottom = l, t, r, b
            self.height = abs(self.bottom - self.top)
            self.width = abs(self.right - self.left)
            self.bg._refresh_crop()
            self.updateAllElements()
            self.getPartyList()
        else:
            if self.s_GameScreen.has_been_resized():
                print("Game view has been resized. Updating bound elements...")
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
        # The original logic still needs to run for other parts of the bot.
        for elem in self.BoundScreenElements:
            elem.update()
    def checkActionbarMoved(self):
        """
        Performs a hyper-efficient and accurate check using a single, stable anchor point.
        This function performs NO image searching.
        """
        # If our stable anchor hasn't been set yet, we can't check.
        # This forces an update on the first run to establish the anchor.
        if self.action_bar_anchor_pos is None:
            print("Action bar anchor not established. Forcing update.")
            return True

        # These values are from our successful Anchored Calibration.
        stable_pixel_color = (40, 25, 12)
        dx = 6
        dy = 31

        # Use the STABLE anchor position, not the jittery s_ActionBar.region
        anchor_x, anchor_y = self.action_bar_anchor_pos
        
        check_x = anchor_x + dx
        check_y = anchor_y + dy

        # Perform the single, instantaneous pixel color check.
        current_pixel_color = img.GetPixelRGBColor(self.hwnd, (check_x, check_y))
        
        # If the color does not match, the bar has definitely moved.
        if current_pixel_color != stable_pixel_color:
            print(f'Action bar moved. At ({check_x},{check_y}) expected {stable_pixel_color}, got {current_pixel_color}. Triggering update.')
            return True # It moved!
                
        # The pixel is correct, the bar has not moved.
        return False
    def checkGameScreenMoved(self, color_min=(14,14,14), color_max=(28,28,28)):
        """
        Checks if the game screen has moved.
        Ignores pure black (0,0,0) which indicates a background/minimized capture failure.
        """
        # Get bottom-left corner pixel of the current gamescreen region
        x = self.s_GameScreen.region[0]      # left
        y = self.s_GameScreen.region[3] -1   # bottom (y2 is exclusive)
        
        pixel = img.GetPixelRGBColor(self.hwnd, (x, y))
        
        # --- FIX: Ignore Black Screen (Background/Minimized) ---
        if pixel == (0, 0, 0):
            # print("[DEBUG] Screen is black. Skipping resize check.")
            return False 

        # Check if pixel is in the expected color range
        in_range = all(color_min[i] <= pixel[i] <= color_max[i] for i in range(3))
        
        if not in_range:
            print(f"[RESIZE] Point ({x}, {y}) LOST border. Got {pixel}")
            return True # True = Moved/Resized
            
        return False # False = Stable

    def updateChatStatusButtonRegion(self):
        #region = (self.width-300, self.height-30, self.width-100, self.height)
        region = (self.width-500, self.height-300, self.width, self.height)
        button = img.locateImage(self.hwnd,'hud/chat_enabled_button.png', region, 0.96,False)
        if (button):
            x, y, b_w, b_h = button
            x = x+region[0]
            y = y+region[1]
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
        click_client(self.hwnd,x,y)
    
    def getActionbarSlotPosition(self,pos):
        box_width = 34
        
        y = self.s_ActionBar.region[1]
        x = self.s_ActionBar.region[0]+(box_width*(pos))+2*pos
        return (x,y)
    
    def clickActionbarSlot(self, pos, check_cooldown=True):
        # 1. Defensive Cooldown Check
        if check_cooldown:
            # We use the optimized NumPy check we just wrote
            if not self.checkActionBarSlotCooldown(pos):
                # print(f"[DEBUG] Slot {pos} is on cooldown. Skipping click.")
                return False

        # 2. Perform the click
        x, y = self.getActionbarSlotPosition(pos)
        click_client(self.hwnd, x, y)
        return True
    
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
    
    def checkActionBarSlotCooldown(self, pos):
        x, y = self.getActionbarSlotPosition(pos)
        x2, y2 = x + 34, y + 34
        
        # Center region where white text appears
        region = (x + 15, y + 18, x2 - 15, y2 - 12)
        
        image = img.screengrab_array(self.hwnd, region)
        if image is None: return False 

        # Check for (223, 223, 223) - Cooldown Text Color
        target = np.array([223, 223, 223])
        mask = np.all(image == target, axis=2)
        
        # If pixels found -> Cooldown detected -> Return False (Not Ready)
        return not np.any(mask)
    
    def debug_cooldown_check(self):
        """
        Standalone debug function to constantly monitor specific slots.
        """
        # List the slots you want to test (e.g., 5 is usually a strong strike)
        slots_to_test = [8,9] 
        
        for slot in slots_to_test:
            # We call the optimized check function
            is_ready = self.checkActionBarSlotCooldown(slot)
            
            status = "READY" if is_ready else "COOLDOWN"
            
            # Print distinct message
            print(f"[DEBUG MONITOR] Slot {slot} is {status}")
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
                            rclick_client(self.hwnd,positions[j][0],positions[j][1])
                        else:
                            click_client(self.hwnd,positions[j][0],positions[j][1])
                        #cv2.circle(image,(positions[j][0]-region[0],positions[j][1]-region[1]), 3, (255,0,0), -1)
                        time.sleep(0.03)
                #time.sleep(0.1)
                    
        #img.visualize_fast(image)
        #win32api.PostMessage(self.hwnd, win32con.WM_KEYUP, 0x10, 0)

    
    def getMonstersAround(self,area,test = True , test2 = False):
        #contours,_ = self.getMonstersAroundContours(area,test, test2)
        #print(len(contours[0])-1)
        #return len(contours[0])-1
        count = 0
        center = self.s_GameScreen.getRelativeCenter()
        tile_h = self.s_GameScreen.tile_h
        half_tile = tile_h/2
        radius = int(tile_h*(area*3/5))
        #print("tile_h "+str(tile_h)+ " radius " +str(radius) + " area "+str(area))
        #image = img.screengrab_array(self.hwnd, self.s_GameScreen.region)
        
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
            
            rclick_client(self.hwnd,int(game_screen_region[0]+x),int(game_screen_region[1]+y+self.s_GameScreen.tile_h/2))
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
        #self.s_GameScreen.visualize()
        region = self.s_GameScreen.getNamesArea(area)
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
        """
        Calculates Health % by analyzing a single row of pixels from a screenshot.
        Optimized for speed using NumPy.
        """
        image = img.screengrab_array(self.hwnd, self.s_Health.region)
        if image is None: 
            return

        # Scan line Y=6. This is the standard offset for the empty grey bar.
        scan_y = 6
        height, width, _ = image.shape
        
        if scan_y >= height:
            return

        # Extract the specific row. OpenCV images are BGR.
        # Target Grey (95, 95, 95) is the same in BGR.
        row_pixels = image[scan_y, :] 
        target_color = np.array([95, 95, 95])
        
        # Calculate Euclidean distance for the whole row at once
        distances = np.linalg.norm(row_pixels - target_color, axis=1)
        
        # Count pixels that are close to the "Empty Grey" color (dist <= 15)
        empty_pixels_count = np.sum(distances <= 15)
        
        # Calculate HP Percentage
        self.hppc = 100 * (width - empty_pixels_count) / width
    
    def getMana(self):
        """
        Calculates Mana % by analyzing a single row of pixels from a screenshot.
        Optimized for speed using NumPy.
        """
        image = img.screengrab_array(self.hwnd, self.s_Mana.region)
        if image is None: 
            return

        # Scan line Y=6. This is the standard offset for the empty grey bar.
        scan_y = 6
        height, width, _ = image.shape
        
        if scan_y >= height:
            return

        # Extract the specific row. OpenCV images are BGR.
        # Target Grey (95, 95, 95) is the same in BGR.
        row_pixels = image[scan_y, :] 
        target_color = np.array([95, 95, 95])
        
        # Calculate Euclidean distance for the whole row at once
        distances = np.linalg.norm(row_pixels - target_color, axis=1)
        
        # Count pixels that are close to the "Empty Grey" color (dist <= 15)
        empty_pixels_count = np.sum(distances <= 15)
        
        # Calculate MP Percentage
        self.mppc = 100 * (width - empty_pixels_count) / width
    def getBurstDamage(self):
        current = self.hp_queue[0]
        val = []
        for i in range(0, 3):
            val.append(self.hp_queue[i]-current)
        return max(val)
    
    def manageMagicShield(self):
        if self.vocation == "druid" or self.vocation == "sorcerer":
            if self.hppc <= self.hp_thresh_low.get() or self.getBurstDamage() > 40:
                if self.slot_status[self.slots.get("magic_shield")] and not self.magic_shield_enabled:
                    self.clickActionbarSlot(self.slots.get("magic_shield"))
                    self.magic_shield_enabled = True
            else:
                if self.magic_shield_enabled and self.monsterCount() == 0:
                    self.clickActionbarSlot(self.slots.get("cancel_magic_shield"))
                    self.magic_shield_enabled = False
    
    def manageHealth(self):
        self.getHealth()
        self.hp_queue.pop()
        self.hp_queue.appendleft(self.hppc)
        burst = self.getBurstDamage()
        # Use SLOTS instead of Key Press
        if (self.hppc <= self.hp_thresh_low.get() or burst > 40):
            # Check if slot exists in config
            if "heal_low" in self.slots: 
                self.clickActionbarSlot(self.slots["heal_low"])
                
        elif self.hppc < self.hp_thresh_high.get():
            if "heal_high" in self.slots:
                self.clickActionbarSlot(self.slots["heal_high"])
            
    def manageMana(self):
        self.getMana()
        if self.isAttacking():
            thresh = self.mp_thresh.get()
        else:
            thresh = self.safe_mp_thresh
            
        if (self.mppc <= thresh and self.hppc >= self.hp_thresh_low.get()):
            if "mana" in self.slots:
                self.clickActionbarSlot(self.slots["mana"])

    def castExetaRes(self):
        if not self.delays.due("exeta_res"):
            return
        slot = self.slots.get("exeta") 
        if slot is not None:
            if self.clickActionbarSlot(slot):
                self.delays.trigger("exeta_res")

    def castAmpRes(self):
        if not self.delays.due("amp_res"):
            return
        slot = self.slots.get("amp_res")
        if slot is not None:
            if self.clickActionbarSlot(slot):
                self.delays.trigger("amp_res")

    def haste(self):
        slot = self.slots.get("haste")
        if slot is not None and self.slot_status[slot]:
            if not self.buffs['haste'] and not self.buffs['pz']:
                self.clickActionbarSlot(slot)
                
    def eat(self):
        slot = self.slots.get("food")
        if slot is not None and self.slot_status[slot]:
            if not self.buffs['pz'] and self.buffs['hungry']:
                # Skip cooldown check for food
                self.clickActionbarSlot(slot, check_cooldown=False)
    
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
        if not self.delays.due("utito"):
            return
        monster_count = self.monsterCount()
        if monster_count >= 3:
            if self.shouldUtito(monster_count):
                # Only reset timer if the click actually happened
                if self.clickActionbarSlot(self.slots.get("utito")):
                    self.delays.trigger("utito")

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
    def isAttackingOld(self):
        b_x, b_y,b_x2,b_y2 = self.s_BattleList.region
        #w, h = self.s_BattleList.getWidth(),self.s_BattleList.getHeight()
        # x 3 y 22
        colors = [(255, 0, 0), (255, 128, 128)]
        x = b_x+3  # constant
        first_pos = b_y+24  # about mid of first square
        d = 22  # dist between boxes, 19+3
        #battlelist = img.screengrab_array(self.hwnd,self.s_BattleList.region)
        #img.visualize(battlelist)
        if self.vocation == "knight":
            b_y2 = first_pos+d

        for y in range(first_pos, b_y2, d):
            #cv2.line(battlelist, (3,y-b_y), (3,y-b_y+5), (255,255,255), 1) 
            color = img.GetPixelRGBColor(self.hwnd,(x, y))
            if (color in colors):
                #if (vocation == "knight" and y != first_pos):
                #    return False
                return True
        #
        return False
    def isAttacking(self):
        """
        Efficiently scans a narrow 5px strip on the left of the Battle List.
        Detects Red (0,0,255) or Highlight Red (128,128,255) pixels.
        """
        b_x, b_y, _, b_y2 = self.s_BattleList.region
        
        # Optimization: Scan only the first 5 pixels of width. 
        # The red attack border is usually at offset +2 or +3.
        scan_width = 5 
        
        scan_region = (b_x, b_y, b_x + scan_width, b_y2)
        image = img.screengrab_array(self.hwnd, scan_region)
        
        if image is None: 
            return False

        # Fast NumPy mask for Red or Highlight Red (BGR format)
        # Red: (0, 0, 255), Highlight: (128, 128, 255)
        # We check if Blue channel is 255 AND Green channel is either 0 or 128
        mask = (image[:, :, 2] == 255) & ((image[:, :, 1] == 0) | (image[:, :, 1] == 128))
        
        return np.any(mask)
    
    
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
        self.buffs = img.imageListExist(self.hwnd,lista, 'buffs', area, 0.90)

    def debug_clickAttack_scanlines(self):
        _x, _y, _x2, _y2 = self.s_BattleList.region
        x = _x + 25
        first_pos = _y + 30
        d = 22

        img_array = img.screengrab_array(self.hwnd, self.s_BattleList.region)

        # --- Ensure correct format ---
        img_array = np.array(img_array).copy()
        img_array = img_array.astype(np.uint8)
        if len(img_array.shape) == 2:
            img_array = cv2.cvtColor(img_array, cv2.COLOR_GRAY2BGR)
        elif img_array.shape[2] == 4:
            img_array = cv2.cvtColor(img_array, cv2.COLOR_BGRA2BGR)

        # --- Draw scan lines ---
        for y in range(first_pos, _y2, d):
            y_line = y - _y
            cv2.line(img_array, (0, y_line), (img_array.shape[1]-1, y_line), (0,0,255), 1)
            x_rel = x - _x
            cv2.circle(img_array, (x_rel, y_line), 3, (255,0,0), -1)

        cv2.imshow('BattleList Scanlines', img_array)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    def clickAttack(self):
        """
        Scans the Battle List for a valid target (Black Pixel check).
        Optimized to use a single screenshot + NumPy array lookup.
        """
        
        # 1. Checks: Don't attack if already attacking or in PZ
        if self.isAttacking() or self.buffs.get('pz', False):
            return
        if not self.delays.due("attack_click"):
            return

        # 2. Capture the Battle List region
        region = self.s_BattleList.region
        image = img.screengrab_array(self.hwnd, region)
        
        if image is None:
            return

        height, width, _ = image.shape

        # 3. Define Offsets (based on your original code)
        # Original: x = _x + 25, first_pos = _y + 30, d = 22
        rel_x = 25
        start_y = 30
        step_y = 22
        # 4. Iterate through the slots using the image array
        for rel_y in range(start_y, height, step_y):
            
            # Safety bound check
            if rel_y >= height or rel_x >= width:
                break

            # Get the pixel color from the array (Instant)
            # OpenCV images are BGR. Black is [0, 0, 0] in both.
            pixel = image[rel_y, rel_x]

            # Check if pixel is pure black [0, 0, 0]
            # We use np.array_equal or simple comparisons for speed
            if pixel[0] == 0 and pixel[1] == 0 and pixel[2] == 0:
                
                # Calculate Absolute Screen Coordinates for the click
                abs_x = region[0] + rel_x
                abs_y = region[1] + rel_y
                print("Clicking target at:", abs_x, abs_y)
                click_client(self.hwnd, abs_x, abs_y)
                self.delays.trigger("attack_click")
                
                # Stop after clicking the first valid target
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
                click_client(self.hwnd,x, y)
                    
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
        click_client(self.hwnd,region[0]+x,region[1]+y)
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
    def updateMonsterPositions(self, test=False):
        # 1. Capture the standard Game Screen region
        region = self.s_GameScreen.region
        image = img.screengrab_array(self.hwnd, region)
        
        if image is None:
            self.monster_positions = []
            return

        # 2. Run the detection (Returns feet coordinates)
        raw_positions = dm.detect_monsters(image)
        
        monster_positions = []
        
        # 3. Filter out Party Members
        # We assume Party Detection uses Sprite Center (Feet).
        # Our new detection ALSO targets Feet.
        # So we can use a tight distance check.
        for (mx, my) in raw_positions:
            is_party = False
            for player in self.party_positions:
                px, py = player[0] 
                
                # Simple distance check between feet
                dist = sqrt((px - mx)**2 + (py - my)**2)
                
                if dist < 45: 
                    is_party = True
                    if test:
                        # Draw BLUE for Party
                        cv2.circle(image, (mx, my), 5, (255, 0, 0), -1)
                    break
            
            if not is_party:
                monster_positions.append((mx, my))
                if test:
                    # Draw GREEN for Monsters
                    cv2.circle(image, (mx, my), 5, (0, 255, 0), -1)

        self.monster_positions = monster_positions
        
        if test:
            # Show the live debug window
            img.visualize_fast(image)

    def get_training_positions(self):
        """
        Calculates the center of the detected Name/Health bars relative to the 
        standard GameScreen region.
        """
        # 1. Get contours from the 'Names Area' (which is shifted up)
        contour_list = self.getMonstersAroundContours(9, False, False)
        
        training_positions = []
        
        # 2. Get the shift amount used in getNamesArea
        # We need to subtract this to align with the GameScreen image
        # In getNamesArea: r = (r[0], r[1]-offset_x, ...
        # So the detection area starts 'offset_x' pixels ABOVE the game screen.
        area_shift_y = int(self.s_GameScreen.tile_h / 4) # Matching the value used in your logic
        
        ratio = self.monster_around_scale_ratio
        
        for contours in contour_list:
            cnts = imutils.grab_contours(contours)
            for cur in cnts:
                M = cv2.moments(cur)
                if M["m00"] != 0:
                    # Raw centroid in the "Names Area" image
                    cX = int(M["m10"] / M["m00"])
                    cY = int(M["m01"] / M["m00"])
                    
                    # Scale back up (because detection uses downscaled image)
                    scaled_X = cX * ratio
                    scaled_Y = cY * ratio
                    
                    # 3. Adjust for the Area Shift
                    # If detection Y is 10, and area started -20 pixels (up), 
                    # then on the main screen (0), the Y is 10 - 20 = -10.
                    # However, we also have an offset_x and offset_y in the original code 
                    # that moved it to the feet. We WANT to stay on the name.
                    
                    # Assuming the contour is roughly the center of the nameplate:
                    # We just map it to the GameScreen coordinate system.
                    
                    # Note: You might need to tweak this specific subtraction 
                    # depending on exactly how getNamesArea is defined in your current version.
                    # Based on standard logic:
                    final_X = scaled_X + int(self.s_GameScreen.tile_h / 4) # Re-add the X offset if it aligns the column
                    final_Y = scaled_Y - area_shift_y 
                    
                    training_positions.append((final_X, final_Y))
                    
        return training_positions

    def capture_training_data(self):
        """
        Saves the current GameScreen image and the currently detected 
        monster NAME coordinates to a 'training_data' folder.
        """
        save_dir = os.path.join(self.base_directory, "training_data")
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        img_filename = f"{timestamp}.png"
        json_filename = f"{timestamp}.json"
        
        img_path = os.path.join(save_dir, img_filename)
        json_path = os.path.join(save_dir, json_filename)

        # 1. Capture the Image
        game_screen_img = img.screengrab_array(self.hwnd, self.s_GameScreen.region)
        if game_screen_img is None:
            print("Failed to capture training image.")
            return

        # 2. Get Name Coordinates (Not Feet!)
        name_positions = self.get_training_positions()

        # 3. Save Image
        cv2.imwrite(img_path, game_screen_img)

        # 4. Save Metadata
        data = {
            "timestamp": timestamp,
            "image_file": img_filename,
            "monster_count": len(name_positions),
            "coordinates": [ [int(x), int(y)] for x, y in name_positions ]
        }

        with open(json_path, 'w') as f:
            json.dump(data, f, indent=4)

        print(f"[DATA] Saved {img_filename} with {len(name_positions)} name labels.")
        
    def useAreaRunePrev(self, test=False):
        # 1. Get the SPECIFIC threshold for runes
        min_monsters = self.min_monsters_for_rune.get()

        # 2. Quick Fail Checks
        if not test:
            if self.buffs.get('pz', False):
                return
            if self.monsterCount() < min_monsters:
                return
            if not self.delays.due("area_rune"):
                return

        # 3. Get valid targets
        region = self.s_GameScreen.region
        tile = self.s_GameScreen.tile_w
        tile_radius = 3  # Radius of GFB/Avalanche (approx 3 tiles)
        
        valid_positions = [p for p in self.monster_positions if p != (0, 0)]
        
        # Optimization: If total tracked positions < requirement, don't bother clustering
        if len(valid_positions) < min_monsters:
            return

        # 4. Find Best Cluster (Brute Force Center Search)
        best_center = None
        best_neighbors = []

        for center_candidate in valid_positions:
            curX, curY = center_candidate
            
            # Find all neighbors within rune radius of this candidate
            neighbors = []
            for potential in valid_positions:
                pX, pY = potential
                dist = sqrt((pX - curX)**2 + (pY - curY)**2)
                
                # Check distance (Radius * Tile Size)
                if dist <= (tile * tile_radius):
                    neighbors.append((pX, pY))
            
            # If this cluster is better than what we found before, keep it
            if len(neighbors) > len(best_neighbors):
                best_neighbors = neighbors
                best_center = center_candidate
                
                # Optimization: If we found a huge cluster, stop searching early
                if len(best_neighbors) >= 5:
                    break
        
        # 5. Execute Attack
        if best_center is not None:
            # Check against the GUI setting
            if len(best_neighbors) >= min_monsters:
                
                # Calculate the centroid of the cluster for optimal coverage
                avg_x = sum([n[0] for n in best_neighbors]) / len(best_neighbors)
                avg_y = sum([n[1] for n in best_neighbors]) / len(best_neighbors)
                
                final_x = int(avg_x)
                final_y = int(avg_y)

                # Visualize (Debug / GUI toggle)
                self._visualize_area_rune_target(final_x, final_y, neighbors_rel=best_neighbors, radius_px=tile*tile_radius)

                if not test:
                    # 1. Click Rune Hotkey
                    if not self.clickActionbarSlot(self.slots.get("area_rune")):
                        return
                    
                    # 2. Click Game Screen (Global Coordinates)
                    # region[0], region[1] are the top-left of the game screen
                    click_client(self.hwnd, region[0] + final_x, region[1] + final_y)
                    
                    # 3. Set Cooldown
                    self.delays.trigger("area_rune")
                    print(f"[COMBAT] Fired Area Rune on {len(best_neighbors)} targets.")


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
        #click_client(self.hwnd,region[0]+x,region[1]+y)
        
    
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
                rclick_client(self.hwnd,pos[0],pos[1])
    
    
    def attackSpells(self):
        # 1. Safety Checks
        if self.buffs.get('pz', False) or self.monsterCount() == 0:
            return

        # 2. Global Cooldown / Delay Check
        cur_sleep = timeInMillis() - self.last_attack_time
        if (timeInMillis() - cur_sleep <= (100 + self.normal_delay)):
            return

        # 3. Update State
        # (Get accurate count for spells)
        self.monsters_around = self.getMonstersAround(self.areaspell_area, True, True)
        self.monster_count = self.monsterCount()

        # 4. Maintain Monster Queue (Preserved from your code)
        if time.time() - self.monster_queue_time >= 1:
            self.monster_queue.pop()
            self.monster_queue.appendleft(self.monsters_around)
            self.monster_queue_time = time.time()

        if self.monsters_around > 0:
            
            # --- SUPPORT SPELLS (Exeta / Amp Res) ---
            # Using new Slot system instead of hardcoded hotkeys
            
            # Exeta Res
            if self.res.get(): 
                # Check if we have a slot defined for 'exeta'
                if "exeta" in self.slots:
                    self.castExetaRes() # Ensure castExetaRes uses self.slots['exeta'] too

            # Amp Res
            if self.amp_res.get():
                monsters_in_melee = self.getMonstersAround(3, False, False)
                # Logic: If we see more monsters than are in melee range, cast Amp Res
                if monsters_in_melee < self.monster_count:
                    if "amp_res" in self.slots:
                        self.castAmpRes()

            # --- ATTACK SPELL ROTATION ---
            
            # Condition: Kill Mode OR Enough Monsters
            should_aoe = (self.kill and self.cavebot.get()) or \
                         (self.monsters_around >= self.min_monsters_around_spell.get())
            if should_aoe:
                # Iterate through the list of Area Spell Slots (F5, F6, etc.)
                for slot in self.area_spells_slots:
                    if self.check_spell_cooldowns:
                        # Only click if the slot is NOT on cooldown
                        if self.checkActionBarSlotCooldown(slot):
                            if self.clickActionbarSlot(slot):
                                self.updateLastAttackTime()
                                self.newNormalDelay()
                                return # STOP after one successful cast (Efficient)
                    else:
                        # No cooldown check, just spam (Original behavior support)
                        self.clickActionbarSlot(slot)
                        self.updateLastAttackTime()
                        self.newNormalDelay()
                        return

            # --- SINGLE TARGET ROTATION ---
            elif self.monsters_around >= 1:
                # Iterate through Single Target Slots (F8, F9, etc.)
                for slot in self.target_spells_slots:
                    if self.check_spell_cooldowns:
                        if self.checkActionBarSlotCooldown(slot):
                            if self.clickActionbarSlot(slot):
                                self.updateLastAttackTime()
                                self.newNormalDelay()
                                return
                    else:
                        self.clickActionbarSlot(slot)
                        self.updateLastAttackTime()
                        self.newNormalDelay()
                        return
    
    def attackAreaSpells(self):
        """
        Attempts to cast Area Spells (Waves, UE).
        Returns True if a spell was cast (triggered GCD).
        """
        # 1. Safety & Cooldown Checks
        if self.buffs.get('pz', False) or self.monsterCount() == 0:
            return False
            
        # Check explicit delay (Global Cooldown)
        cur_sleep = timeInMillis() - self.last_attack_time
        if (timeInMillis() - cur_sleep <= (100 + self.normal_delay)):
            return False

        # 2. Check Conditions
        # Use the configured area (e.g. 6 for Mages, 3 for Knights)
        self.monsters_around = self.getMonstersAround(self.areaspell_area, True, True)
        
        # Check threshold (e.g. 5+ for UE)
        if self.monsters_around < self.min_monsters_around_spell.get():
            return False

        # 3. Attempt Cast
        for slot in self.area_spells_slots:
            if self.check_spell_cooldowns:
                if self.checkActionBarSlotCooldown(slot):
                    if self.clickActionbarSlot(slot):
                        self.updateLastAttackTime()
                        self.newNormalDelay()
                        print(f"[COMBAT] Cast Area Spell (Slot {slot})")
                        return True
            else:
                self.clickActionbarSlot(slot)
                self.updateLastAttackTime()
                self.newNormalDelay()
                return True
                
        return False

    def useAreaRune(self, test=False):
        """
        Calculates clusters and throws runes (GFB/Ava).
        Returns True if a rune was thrown.
        """
        min_monsters = self.min_monsters_for_rune.get()

        if not test:
            if self.buffs.get('pz', False): return False
            if self.monsterCount() < min_monsters: return False
            # Check internal Rune Timer AND Global Cooldown (Runes share group CD)
            if not self.delays.due("area_rune"): return False
            
            # Don't rune if we just cast a spell (GCD protection)
            cur_sleep = timeInMillis() - self.last_attack_time
            if (timeInMillis() - cur_sleep <= (100 + self.normal_delay)):
                return False

        # --- Clustering Logic (Same as before) ---
        region = self.s_GameScreen.region
        tile = self.s_GameScreen.tile_w
        tile_radius = 3
        
        valid_positions = [p for p in self.monster_positions if p != (0, 0)]
        if len(valid_positions) < min_monsters: return False

        best_center = None
        best_neighbors = []

        for center_candidate in valid_positions:
            curX, curY = center_candidate
            neighbors = []
            for potential in valid_positions:
                pX, pY = potential
                dist = sqrt((pX - curX)**2 + (pY - curY)**2)
                if dist <= (tile * tile_radius):
                    neighbors.append((pX, pY))
            
            if len(neighbors) > len(best_neighbors):
                best_neighbors = neighbors
                best_center = center_candidate
                if len(best_neighbors) >= 5: break
        
        if best_center is not None:
            if len(best_neighbors) >= min_monsters:
                avg_x = sum([n[0] for n in best_neighbors]) / len(best_neighbors)
                avg_y = sum([n[1] for n in best_neighbors]) / len(best_neighbors)
                final_x = int(avg_x)
                final_y = int(avg_y)

                self._visualize_area_rune_target(final_x, final_y, neighbors_rel=best_neighbors, radius_px=tile*tile_radius)

                if not test:
                    if not self.clickActionbarSlot(self.slots.get("area_rune")):
                        return False
                    
                    click_client(self.hwnd, region[0] + final_x, region[1] + final_y)
                    self.delays.trigger("area_rune")
                    # Update attack time because Runes trigger a 2s Group CD
                    self.updateLastAttackTime() 
                    print(f"[COMBAT] Fired Area Rune on {len(best_neighbors)} targets.")
                    return True
        return False

    def attackTargetSpells(self):
        """
        Standard single target rotation (Exori Vis, etc).
        """
        if self.buffs.get('pz', False) or self.monsterCount() == 0: return

        cur_sleep = timeInMillis() - self.last_attack_time
        if (timeInMillis() - cur_sleep <= (100 + self.normal_delay)):
            return

        # Only cast if we have at least 1 monster
        if self.monsters_around >= 1:
            for slot in self.target_spells_slots:
                if self.check_spell_cooldowns:
                    if self.checkActionBarSlotCooldown(slot):
                        if self.clickActionbarSlot(slot):
                            self.updateLastAttackTime()
                            self.newNormalDelay()
                            return
                else:
                    self.clickActionbarSlot(slot)
                    self.updateLastAttackTime()
                    self.newNormalDelay()
                    return
                
    def get_slot_image(self, pos):
        """Helper for GUI to visualize slots"""
        x, y = self.getActionbarSlotPosition(pos)
        region = (x, y, x + 34, y + 34)
        return img.screengrab_array(self.hwnd, region)
    
    def manageEquipment(self):
        if not self.delays.allow("equip_cycle"):
            return
            
        monster_count = self.monsterCount()
        
        # Define the keys we care about
        equip_keys = ["weapon", "helmet", "armor", "amulet", "ring", "shield"]
        
        for key in equip_keys:
            slot_id = self.slots.get(key)
            if slot_id is None: continue
            
            # Use safe access to slot_status
            if slot_id < len(self.slot_status) and self.slot_status[slot_id]:
                if self.isActionbarSlotEnabled(slot_id):
                    # Item is equipped/active. Unequip if safe.
                    if monster_count == 0:
                        # print(f"Disabling {key}")
                        self.clickActionbarSlot(slot_id)
                        time.sleep(0.05)
                else:
                    # Item is unequipped. Equip if fighting.
                    if monster_count > 0:
                        # print(f"Enabling {key}")
                        self.clickActionbarSlot(slot_id)
                        time.sleep(0.05)
            
    def isFollowing(self):
        x1, y1, x2, y2 = self.s_Party.region
        image = img.screengrab_array(self.hwnd, (x1, y1, x2, y2))
        if image is None:
            return False

        mask_standard = np.all(image == [0, 255, 0], axis=2)
        mask_highlight = np.all(image == [128, 255, 128], axis=2)
        return np.any(mask_standard) or np.any(mask_highlight)

    
    def manageFollow(self):
        if not self.follow_party.get():
            return

        # 1. Check if we are already following (Success case)
        if self.isFollowing():
            return
        print("[DEBUG] Not currently following.")
        # 2. Check Cooldown (Prevents spamming)
        if not self.delays.due("follow_retry"):
            return

        # 3. Don't interrupt attack unless necessary
        # If we are attacking and the user wants to prioritize attack, skip follow logic
        if self.attack and self.isAttacking():
             return

        print("[DEBUG] Auto-Follow triggered...")
        
        # 4. Attempt to follow
        self.getPartyList() # Refresh positions
        
        ok = self.followLeader()
        self.delays.trigger("follow_retry")
        if ok:
            print(f"[DEBUG] Follow clicked. Waiting {self.follow_retry_delay}s to verify...")
        else:
            print("[DEBUG] Could not find leader to follow.")
    
    def followLeader(self):
        leader_name = self.party_leader.get()

        if leader_name not in self.party:
            return False

        try:
            name_rect = self.party[leader_name]["name_rect"]  # (x1,y1,x2,y2) CLIENT coords
            x1, y1, x2, y2 = name_rect

            # --- PRE-FLIGHT (leader not away) ---
            name_img = img.screengrab_array(self.hwnd, name_rect)
            if name_img is not None:
                target_color = np.array([192, 192, 192])  # BGR in your pipeline, but 192,192,192 is symmetric
                if not np.any(np.all(name_img == target_color, axis=2)):
                    print(f"[DEBUG] Skipping follow: Leader '{leader_name}' is AWAY.")
                    return False

            # Click center of the name row (CLIENT coords)
            click_x = (x1 + x2) // 2
            click_y = (y1 + y2) // 2

            # Context menu "Follow" offset (CLIENT coords)
            off_x = 35
            off_y = 35
            menu_x = click_x + off_x
            menu_y = click_y + off_y

            

            # Execute (CLIENT coords only)
            _, _, (x_i, y_i) = win32gui.GetCursorInfo()
            win32api.SetCursorPos((click_x, click_y))
            time.sleep(0.05) 
            rclick_client(self.hwnd, click_x, click_y)
            time.sleep(1)
            # Debug image: crop around the click point (CLIENT coords)
            debug_img = img.screengrab_array(self.hwnd, (click_x - 50, click_y - 50, click_x + 150, click_y + 150))
            if debug_img is not None:
                debug_img = np.ascontiguousarray(debug_img, dtype=np.uint8)
                cv2.drawMarker(debug_img, (50, 50), (255, 0, 0), markerType=cv2.MARKER_CROSS, markerSize=15, thickness=2)
                cv2.drawMarker(debug_img, (50 + off_x, 50 + off_y), (0, 0, 255), markerType=cv2.MARKER_CROSS, markerSize=15, thickness=2)
                cv2.imwrite("debug_follow_action.png", debug_img)
            win32api.SetCursorPos((menu_x, menu_y))
            click_client(self.hwnd, menu_x, menu_y)
            win32api.SetCursorPos((x_i, y_i))
            return True

        except Exception as e:
            print("error in followLeader: " + str(e))
            return False

          
    def getPartyList(self):
        x, y, x2, y2 = self.s_Party.region
        bar_h = 4
        p_dist = 26
        
        # We define a "Scan Column" to find the black separators
        hp_bar_y = y + 28 
        hp_bar_x = x + 22 
        
        # CAPTURE THE FULL PARTY REGION FOR DEBUGGING
        full_party_img = img.screengrab_array(self.hwnd, (x, y, x2, y2))
        if full_party_img is None: return

        # FIX: Make the array contiguous in memory so OpenCV can draw on it
        full_party_img = np.ascontiguousarray(full_party_img, dtype=np.uint8)

        player_count = 0
        
        # 1. Detect Player Count (Black Pixels)
        img_h, img_w, _ = full_party_img.shape
        
        for _y in range(hp_bar_y, y2, 26):
            # Convert absolute screen Y to relative image Y
            rel_y = _y - y
            rel_x = hp_bar_x - x
            
            # Safety check
            if rel_y >= img_h or rel_x >= img_w: break

            # Get pixel from the array (Fast)
            pixel = full_party_img[rel_y, rel_x]
            if np.array_equal(pixel, [0, 0, 0]):
                player_count += 1
                # DEBUG: Draw Blue Circle on found separators
                cv2.circle(full_party_img, (rel_x, rel_y), 2, (255, 0, 0), -1)

        print(f"[DEBUG] Found {player_count} party members.")

        # 2. Scan Names
        for i in range(0, player_count):
            abs_y1 = hp_bar_y - 13 + (i * p_dist)
            abs_y2 = hp_bar_y - 1 + (i * p_dist)
            abs_x1 = hp_bar_x - 2
            abs_x2 = x2 - 30
            
            name_region = (abs_x1, abs_y1, abs_x2, abs_y2)
            
            # Capture just the name for OCR
            name_img = img.screengrab_array(self.hwnd, name_region)
            
            if name_img is not None:
                # DEBUG: Save the exact crop we send to Tesseract
                debug_filename = f"debug_name_crop_{i}.png"
                cv2.imwrite(debug_filename, name_img)
                
                # Perform OCR
                raw_name = img.tesser_image(name_img, 124, 255, 1, config='--psm 7')
                print(f"[DEBUG OCR] Row {i} raw read: '{raw_name}'")

                # Match against known list
                name_found = False
                for n in self.player_list.keys():   
                    if (similarString(raw_name, n)):
                        name = n
                        name_found = True
                        break 
                
                if not name_found:
                    print(f"[DEBUG OCR FAIL] Could not match '{raw_name}' to any known player.")
                else:
                    hp_bar_region = (hp_bar_x, hp_bar_y+(i*p_dist), x2-4, hp_bar_y+(i*p_dist)+bar_h)
                    self.party[name] = {
                        "hp_bar": hp_bar_region,
                        "name_rect": name_region,   # <-- this is the clickable name area in CLIENT coords
                    }

                # DEBUG: Draw Red Box around name region on the main debug image
                rel_x1 = abs_x1 - x
                rel_y1 = abs_y1 - y
                rel_x2 = abs_x2 - x
                rel_y2 = abs_y2 - y
                cv2.rectangle(full_party_img, (rel_x1, rel_y1), (rel_x2, rel_y2), (0, 0, 255), 1)

        # Save the full diagnostic image
        cv2.imwrite("debug_party_scan.png", full_party_img)
        print("[DEBUG] Saved 'debug_party_scan.png' and name crops.")

    def getPartyLeaderVitals(self):
        try:
            hp_bar = self.party[self.party_leader.get()]["hp_bar"]
            y = hp_bar[1] + 2
            bar_width = hp_bar[2] - hp_bar[0]

            delta = 5
            cant = 0
            for x in range(hp_bar[0], hp_bar[2], delta):
                color = img.GetPixelRGBColor(self.hwnd, (x, y))
                dist = img.ColorDistance(color, (75, 75, 75))
                if dist <= 15:
                    cant += 1

            cant *= delta
            hppc = 100 * (bar_width - cant) / bar_width
            return hppc
        except:
            return 100


    def healParty(self):
        if self.vocation == "druid":
            hppc = self.getPartyLeaderVitals()
            if hppc < 80:
                self.clickActionbarSlot(self.slots.get("sio"))

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
                if self.delays.allow("lure_stop"):
                    print("luring")
                    self.clickStop()
            if len(marks) == 0:
                #print("no "+self.current_mark+ " mark found, changing to the next one")
                self.nextMark()
            else:
                index = 0
                dist, pos, _ = marks[index]  # Unpack 3 values and ignore the third one
                if dist <= 3:
                    #print("reached current mark")
                    self.updatePreviousMarks()
                    self.nextMark()
                else:
                    if self.delays.allow("walk", base_ms=walk_delay):
                        click_client(self.hwnd,pos[0],pos[1])
                        
    def reset_marks_history(self):
        """Manually clears the 'visited' status of map marks."""
        print("[CAVEBOT] Resetting mark history. All marks are now fresh.")
        for mark in self.mark_list:
            self.previous_marks[mark] = False
        # Optional: Reset index to start from the beginning of the list
        self.current_mark_index = 0
        self.current_mark = self.mark_list[0]

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
            time_passed = self.delays.elapsed_ms("walk")
            if time_passed > 100 and time_passed < 500 and monster_count >= 2:
                print("clicking stop")
                self.clickStop()
                if not self.attack.get():
                    self.attack.set(value = True)
                
        if len(marks) == 0:
            #print("no "+self.current_mark+ " mark found, changing to the next one")
            self.nextMark()
            marks = self.getClosestMarks()
        print("marks: "+str(marks))
        index = 0
        dist, pos, _ = marks[index]
        print("distance to mark: "+str(dist))
        #print(dist)
        if dist <= 3:
            print("reached current mark")
            self.updatePreviousMarks()
            self.nextMark()
        else:
            if walk and self.delays.allow("walk", base_ms=walk_delay):
                print("walking")
            #print(str(walk_delay))
            #print("clicking mark")
                click_client(self.hwnd,pos[0],pos[1])
                
    def clickStop(self):
        region = self.s_Stop.getCenter()
        click_client(self.hwnd,region[0],region[1])                     
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
        
        map_image = img.screengrab_array(self.hwnd, map_region)
        
        if map_image is not None:
            map_image_np = np.array(map_image)
        else:
            map_image_np = np.zeros((300, 300, 3), dtype=np.uint8)
        
        positions = img.locateManyImage(self.hwnd, "map_marks/"+self.current_mark+".png", map_region, 0.97)
        
        if not isinstance(self.previous_marks[self.current_mark], bool):
            previous = img.locateImage(self.hwnd, self.previous_marks[self.current_mark], map_region, 0.99)
        else:
            previous = False
        
        if positions:
            if len(positions) > 0:
                for pos in positions:
                    w = int(pos[2])
                    h = int(pos[3])
                    
                    # --- 1. VISUALIZATION / DISTANCE POINT (True Center) ---
                    # We use this for Distance calculation and Visualization lines.
                    vis_x = int(pos[0] + (w / 2))
                    vis_y = int(pos[1] + (h / 2))
                    
                    # --- 2. CLICK POINT (Action Anchor) ---
                    # FIX: Changed from (w + 3, h - 1) to Center to match visualization
                    # Old: click_x = int(pos[0] + w + 3)
                    # Old: click_y = int(pos[1] + h - 1)
                    
                    click_x = int(pos[0] + (w / 2))
                    click_y = int(pos[1] + (h / 2))
                    
                    # Absolute coords for clicking
                    click_abs = (map_region[0] + click_x, map_region[1] + click_y)
                    # Relative coords for drawing
                    vis_rel = (vis_x, vis_y)
                    
                    # FIX: Calculate DISTANCE to the VISUAL CENTER (vis_x, vis_y)
                    # NOT the click point. This ensures distance goes to ~0 when standing on it.
                    if self.compareMarkToPrevious((click_x, click_y), previous):
                        dist = distance.euclidean(map_relative_center, (vis_x, vis_y))
                        result.append((dist, click_abs, vis_rel))
                    else:
                        dist = distance.euclidean(map_relative_center, (vis_x, vis_y))
                        discarded.append((dist, click_abs, vis_rel))
        
        if len(result) == 0:
            result = discarded
        result.sort(reverse=False)
        
        try:
            if not isinstance(previous, bool):
                prev_x, prev_y, w, h = previous
                prev_center = (int(prev_x + w/2), int(prev_y + h/2))
                cv2.line(map_image_np, map_relative_center, prev_center, (0, 0, 255), 1) 
            
            for i, (_, _, vis_point) in enumerate(result):
                if i == 0:
                    cv2.line(map_image_np, map_relative_center, vis_point, (0, 255, 0), 2) 
                else:
                    cv2.line(map_image_np, map_relative_center, vis_point, (255, 0, 0), 1) 
        except Exception as e:
            print(f"Error drawing lines: {e}")

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
            click_client(self.hwnd,region[0]+sell_x_off,region[1]+sell_y_off)
            #buy_pressed = img.locateImage(self.hwnd,'/hud/npc_trade_buy_pressed.png', region, 0.97)
            #if buy_pressed:
            #    x_buy, y_buy, w_buy, h_buy = buy_pressed
            #    print("clicking sell button")
            #    click_client(self.hwnd,region[0]+x_buy + int(w_buy/2),
            #        region[1]+y_buy+int(3*h_buy/2))
            #else:
            #    buy_unpressed = img.locateImage(self.hwnd,'/hud/npc_trade_buy_unpressed.png', region, 0.83, True)
            #    x_buy, y_buy, w_buy, h_buy = buy_unpressed
            time.sleep(0.1)
            counter = 0
            while (True):
                click_client(self.hwnd,region[0]+100 , region[1]+75)
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
                    click_client(self.hwnd,region[0]+x_ok + int(ok_w/2), region[1]+y_ok+int(ok_h/2))
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
            click_client(self.hwnd,self.chat_status_region[0]+10, self.chat_status_region[1]+5)
    
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
        #offset, error, ss_color, win_color = img.sync_screenshot_with_pixel(self.hwnd, (100, 100, 300, 300), (10, 10))
        #print("Best offset:", offset)
        #print("Error:", error)
        #print("Screenshot color:", ss_color)
        #print("Window color:", win_color)
if __name__ == "__main__":
    
    bot = Bot()
    bot.updateFrame()
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
    calibrate = False
    while(True): 
        # Check if GUI signaled exit
        if not bot.loop.get():
            break
            
        bot.GUI.loop()
        bot.updateFrame()
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
        if calibrate:
            bot.calibrate_actionbar_pixel()
            print("Calibration finished. Please update your code and restart the bot.")
            exit() # Exit the script after calibration is done


        #print(current_time % 10)
        if current_time % 10 == 0:
            bot.updateActionbarSlotStatus()
            #print("looting")
            if bot.loot_on_spot.get():
                bot.lootAround(True)
        times[1] = timeInMillis()
        if bot.monsterCount() > 0:
            #print("monster count: "+str(bot.monsterCount()))
            bot.updateMonsterPositions()
        times[2] = timeInMillis()
        #bot.getMonstersAround(bot.areaspell_area,False,False)
        #if len(bot.party.keys()) > 0:w
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
        #if bot.use_utito:
        #    if bot.vocation == "knight":
        #        bot.utito()
        times[6] = timeInMillis()
        
        # --- COMBAT LOGIC CHAIN ---
        if bot.attack_spells.get():
            # 1. Try Big Area Spells (e.g. UE/Wave) if density is high
            did_aoe_spell = bot.attackAreaSpells()
            
            # 2. If no Big Spell, try Area Rune (GFB)
            did_rune = False
            if not did_aoe_spell and bot.use_area_rune.get():
                did_rune = bot.useAreaRune()
            
            # 3. If no AoE occurred, use Single Target Spell (Filler)
            if not did_aoe_spell and not did_rune:
                bot.attackTargetSpells()
        if bot.cavebot.get():
            bot.cavebottest()
            #if bot.vocation == "knight":
            #    bot.cavebottest()
            #else:
            #    bot.cavebot_distance()
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
        
        
