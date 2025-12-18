# region Imports
import win32gui,win32api,win32con
from ctypes import windll
import time
import json
import datetime
import cv2
import imutils
import numpy as np
import keyboard as kb
import PIL
import os
from pynput import keyboard
from math import sqrt
# data
from collections import Counter, deque
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
from constants import BotConstants
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
        # 1. System & Character Setup
        self._setup_system()
        
        # 2. Config & Profile Loading
        self.config = cm.ConfigManager()
        char_info = self.config.get_character_info(self.character_name)
        self.vocation = char_info["vocation"]
        self.areaspell_area = char_info["spell_area"]
        self.profile = self.config.get_config(self.character_name, self.vocation)
        
        # --- DATA MUST BE READY BEFORE GUI BUILDS ---
        self.slots = self.profile["slots"]
        self.area_spells_slots = self.profile["spells"]["area_slots"]
        self.target_spells_slots = self.profile["spells"]["target_slots"]
        
        # 3. GUI Initialization (Creates the Root Window)
        self.GUI = ModernBotGUI(self, self.character_name, self.vocation)
        
        # 4. Initialize Bot Variables (Bridge logic)
        self._init_bot_vars(self.profile["settings"])

        # 5. Initialize Components (Screen elements, queues)
        self._init_screen_elements()
        self._init_queues_and_states()
        self._init_timers()

        # 6. FINALIZE GUI (This builds the tabs that need self.slots)
        # We call this LAST because now the bot has everything defined
        self.GUI.setup_vars_and_ui()

    def _setup_system(self):
        self.base_directory = os.getcwd()
        self.hwnd = choose_capture_window()
        self.bg = BackgroundFrameGrabber(self.hwnd, max_fps=50)
        self.character_name = self.getCharacterName()
        
        if self.character_name is None:
            print("You are not logged in.")
            exit()
            
        rect = win32gui.GetClientRect(self.hwnd)
        self.width, self.height = rect[2], rect[3]
        self.left, self.top, self.right, self.bottom = win32gui.GetWindowRect(self.hwnd)
        
        # Static Data
        self.hp_colors = BotConstants.HP_COLORS
        self.low_hp_colors = BotConstants.LOW_HP_COLORS
        self.party_colors = BotConstants.PARTY_COLORS
        self.party_colors_current = "cross"

    def _init_screen_elements(self):
        # Base Elements
        self.s_Stop = ScreenElement("Stop", self.hwnd, 'stop.png', 
                                    lambda w, h: (w - 200, 0, w, int(h / 2)))
        
        # Bound Elements
        self.s_ActionBar = BoundScreenElement("ActionBar", self.hwnd, 'action_bar_start.png', 'action_bar_end.png', 
                                              lambda w, h: (0, h//4, w//3, h), 
                                              lambda w, h: (2*w//3, h//4, w, h), (2, 0))
        
        self.s_GameScreen = GameScreenElement("GameScreen", self.hwnd, 'hp_start.png', 'action_bar_end.png', 
                                              lambda w, h: (150, 0, 300, 150), 
                                              lambda w, h: (2*w//3, h//4, w, h), (2, 0))

        # Window Elements
        self.s_BattleList = ScreenWindow("BattleList", self.hwnd, 'battle_list.png', 2)
        self.s_Skills = ScreenWindow("Skills", self.hwnd, 'skills.png', 1)
        self.s_Party = ScreenWindow("Party", self.hwnd, 'party_list.png', 10)
        
        # Relative Elements (using constants for offsets)
        off = BotConstants.OFFSETS
        self.s_Map = RelativeScreenElement("Map", self.hwnd, self.s_Stop, off["Map"])
        self.s_Bless = RelativeScreenElement("Bless", self.hwnd, self.s_Stop, off["Bless"])
        self.s_Buffs = RelativeScreenElement("Buffs", self.hwnd, self.s_Stop, off["Buffs"])
        self.s_Health = RelativeScreenElement("Health", self.hwnd, self.s_Stop, off["Health"])
        self.s_Mana = RelativeScreenElement("Mana", self.hwnd, self.s_Stop, off["Mana"])
        self.s_Capacity = RelativeScreenElement("Capacity", self.hwnd, self.s_Stop, off["Capacity"])
        self.s_WindowButtons = RelativeScreenElement("WindowButtons", self.hwnd, self.s_Stop, off["WindowButtons"])

        # Grouping
        self.ScreenElements = [self.s_Stop]
        self.BoundScreenElements = [self.s_GameScreen, self.s_ActionBar]
        self.ScreenWindows = [self.s_BattleList, self.s_Skills, self.s_Party]
        self.RelativeScreenElements = [self.s_Map, self.s_Bless, self.s_Buffs, self.s_Health, self.s_Mana, self.s_Capacity, self.s_WindowButtons]
        self.ElementsLists = [self.ScreenElements, self.BoundScreenElements, self.RelativeScreenElements, self.ScreenWindows]
        self.action_bar_anchor_pos = None

    def _init_queues_and_states(self):
        self.resize_confirmation_count = 0
        self.resize_threshold = 5  # Only redetect if border is gone for 5 consecutive frames

        self.hppc, self.mppc = 100, 100
        self.hp_queue = deque([100, 100, 100], maxlen=3)
        self.monster_queue = deque([0]*10, maxlen=10)
        self.monster_queue_time = 0
        self.monster_count = 0
        self.party, self.party_positions = {}, []
        self.monster_positions = []
        self.monsters_around = 0
        self.buffs = {}
        self.last_attack_time = timeInMillis()
        self.slot_status = [False] * 32
        self.magic_shield_enabled = False
        self.key_pressed = False
        
        # --- MISSING LOGIC FLAGS ---
        self.check_spell_cooldowns = True  # FIX: Define the missing attribute
        self.check_monster_queue = True
        self.area_rune_target_click_delay_s = 0.08
        # ---------------------------

        self.kill, self.lure = False, False
        self.kill_start_time = time.time()
        self.kill_stop_time = 120
        self.lure_amount = 2
        self.visited_fingerprints = []
        self.discovery_mode = True # True until we finish the first complete lap
        self.loop_count = 0
        self.circuit_marks_found = 0
        self.mark_list = ["skull", "lock", "cross", "star"]
        self.current_mark_index = 0
        self.current_mark = self.mark_list[0]
        # NEW: Separate index for the manual mark-placer
        self.add_mark_index = 0 
        self.add_mark_type = self.mark_list[0]
        self.last_mark_rel_pos = None # Stores the map-relative (x,y) of the last reached mark
        self.previous_marks = {mark: False for mark in self.mark_list}
        self.visited_history = deque(maxlen=4)
        # Lógica de Lure
        self.lure_stutter_active = False
        self.last_lure_action_time = time.time()
        self.lure_phase = "walking" # "walking" o "stopping"
        
        # Tiempos configurables (ms)
        self.lure_walk_duration = 0.6  # Segundos caminando
        self.lure_stop_duration = 0.4  # Segundos parado

        self.last_map_center_img = None
        self.kiting_stuck_count = 0
        self.kite_rotation_offset = 0
        self.kiting_mode = StringVar(value="forward")
        self.last_reached_mark_rel = None
        self.collision_grid = None
        self.map_scale = 2  # Baseline
        self.last_scale_check = 0
        # Pick 10 random offsets within a 20px radius of map center for tracking
        self.stuck_check_coords = [(np.random.randint(-20, 20), np.random.randint(-20, 20)) for _ in range(10)]
        self.last_stuck_colors = []
        self.stuck_counter = 0
        self.best_rune_tile = None
    def _init_timers(self):
        self.normal_delay = getNormalDelay()
        self.delays = DelayManager(default_jitter_ms_fn=getNormalDelay)
        
        # Internal Values
        self.safe_mp_thresh = self.mp_thresh.get() + 15
        self.follow_retry_delay = 2.5
        
        # Defaults
        self.delays.set_default("attack_click", 120)
        self.delays.set_default("area_rune", 1100, jitter_ms_fn=getNormalDelay)
        self.delays.set_default("equip_cycle", 200)
        self.delays.set_default("lure_stop", 250)
        self.delays.set_default("follow_retry", int(self.follow_retry_delay * 1000))
        self.delays.set_default("exeta_res", 3000)
        self.delays.set_default("amp_res", 6000)
        self.delays.set_default("utito", 10000)
        self.delays.set_default("centering", 250) # Only recenter every 1.5s
        self.delays.set_default("kiting", 600) # El mago reacciona más rápido (0.8s) que el caballero

        # Immediate Triggers
        for timer in ["equip_cycle", "lure_stop", "exeta_res", "amp_res"]:
            self.delays.trigger(timer)
        self.delays.trigger("walk", base_ms=200)

    def _init_bot_vars(self, s):
        """Helper to create Tkinter variables after root window exists"""
        self.attack           = BooleanVar(value=s.get("attack", True))
        self.loop             = BooleanVar(value=s.get("loop", True))
        self.attack_spells    = BooleanVar(value=s.get("attack_spells", True))
        self.hp_heal          = BooleanVar(value=s.get("hp_heal", True))
        self.mp_heal          = BooleanVar(value=s.get("mp_heal", True))
        self.cavebot          = BooleanVar(value=s.get("cavebot", False))
        self.use_lure_walk = BooleanVar(value=s.get("use_lure_walk", False))
        self.lure_walk_ms  = IntVar(value=int(s.get("lure_walk_ms", 600)))
        self.lure_stop_ms  = IntVar(value=int(s.get("lure_stop_ms", 400)))
        self.use_recenter = BooleanVar(value=s.get("use_recenter", False))
        self.use_kiting   = BooleanVar(value=s.get("use_kiting", False))
        self.follow_party     = BooleanVar(value=s.get("follow_party", False))
        self.manual_loot      = BooleanVar(value=s.get("manual_loot", False))
        self.loot_on_spot     = BooleanVar(value=s.get("loot_on_spot", False))
        self.manage_equipment = BooleanVar(value=s.get("manage_equipment", False))
        self.use_area_rune    = BooleanVar(value=s.get("use_area_rune", False))
        self.show_area_rune_target = BooleanVar(value=s.get("show_area_rune_target", True))
        self.use_utito        = BooleanVar(value=s.get("use_utito", False))
        self.res              = BooleanVar(value=s.get("res", False))
        self.amp_res          = BooleanVar(value=s.get("amp_res", False))
        self.use_haste        = BooleanVar(value=s.get("use_haste", True))
        self.use_food         = BooleanVar(value=s.get("use_food", True))

        self.hp_thresh_high        = IntVar(value=int(s.get("hp_thresh_high", 90)))
        self.hp_thresh_low         = IntVar(value=int(s.get("hp_thresh_low", 70)))
        self.mp_thresh             = IntVar(value=int(s.get("mp_thresh", 30)))
        self.min_monsters_around_spell = IntVar(value=int(s.get("min_monsters_spell", 1)))
        self.min_monsters_for_rune = IntVar(value=int(s.get("min_monsters_rune", 1)))
        self.kill_amount           = IntVar(value=int(s.get("kill_amount", 5)))
        self.kill_stop_amount      = IntVar(value=int(s.get("kill_stop_amount", 1)))

        self.party_leader    = StringVar(value=str(s.get("party_leader", "")))
        self.waypoint_folder = StringVar(value=str(s.get("waypoint_folder", "test")))

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
        
        # 1. Physical Window Resize (Always trigger)
        if (self.left, self.top, self.right, self.bottom) != (l, t, r, b):
            print("Window physical rect changed. Force updating elements.")
            self.left, self.top, self.right, self.bottom = l, t, r, b
            self.height = abs(self.bottom - self.top)
            self.width = abs(self.right - self.left)
            self.bg._refresh_crop()
            self.updateAllElements()
            self.getPartyList()
        else:
            # 2. Internal Game View Resize (Use our new debounced check)
            if self.checkGameScreenMoved():
                print("Game view internal resize confirmed. Updating bound elements...")
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
        Checks if the game screen has moved with flicker protection.
        """
        # Get bottom-left corner pixel of the current gamescreen region
        x = self.s_GameScreen.region[0]
        y = self.s_GameScreen.region[3] - 1
        
        pixel = img.GetPixelRGBColor(self.hwnd, (x, y))
        
        # --- FLICKER PROTECTION: Ignore Pure Black ---
        # If the capture is black, it's a flicker or minimized window. 
        # We don't want to redetect; we want to wait for a valid frame.
        if pixel == (0, 0, 0):
            return False 

        # Check if pixel is in the expected dark-grey border range
        in_range = all(color_min[i] <= pixel[i] <= color_max[i] for i in range(3))
        
        if not in_range:
            self.resize_confirmation_count += 1
            if self.resize_confirmation_count >= self.resize_threshold:
                print(f"[RESIZE] Point ({x}, {y}) LOST border for {self.resize_confirmation_count} frames. Confirmed. Got {pixel}")
                self.resize_confirmation_count = 0 # Reset for next time
                return True 
        else:
            # If we get even ONE good frame, reset the counter
            self.resize_confirmation_count = 0
            
        return False

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

    def get_filtered_monsters(self):
        """
        Returns monster positions excluding the player's center tile.
        Uses the 15x11 grid system for perfectly accurate filtering.
        """
        if not self.monster_positions:
            return []

        tile_w = self.s_GameScreen.tile_w
        tile_h = self.s_GameScreen.tile_h
        p_row, p_col = 5, 7  # Shared player grid constants

        filtered = []
        for mx, my in self.monster_positions:
            # Map pixel coordinate to grid tile
            m_col = int(mx // tile_w)
            m_row = int(my // tile_h)

            # IGNORE if it's the player's tile (5, 7)
            if m_row == p_row and m_col == p_col:
                continue
            
            filtered.append((mx, my))
            
        return filtered
    
    def getMonstersAround(self, area, test=True, test2=False):
        count = 0
        center = self.s_GameScreen.getRelativeCenter()
        tile_h = self.s_GameScreen.tile_h
        half_tile = tile_h / 2
        radius = int(tile_h * (area * 3 / 5))
        
        valid_monsters = self.get_filtered_monsters()
        
        for monster in valid_monsters:
            dist = sqrt((monster[0] - center[0])**2 + (monster[1] - center[1])**2)
            # We still keep the 'dist > half_tile' as a secondary safety
            if dist <= radius and dist > half_tile:
                count += 1
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
        if self.vocation in ["druid", "sorcerer"]:
            ms_slot = self.slots.get("magic_shield")
            cancel_slot = self.slots.get("cancel_magic_shield")
            
            if ms_slot is None or cancel_slot is None: return

            if self.hppc <= self.hp_thresh_low.get() or self.getBurstDamage() > 40:
                if self.slot_status[ms_slot] and not self.magic_shield_enabled:
                    self.clickActionbarSlot(ms_slot)
                    self.magic_shield_enabled = True
            else:
                if self.magic_shield_enabled and self.monsterCount() == 0:
                    self.clickActionbarSlot(cancel_slot)
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

    def clickAttack(self, force=False):
        """
        Scans the Battle List for a valid target.
        force: If True, bypasses the delay check (used for stutter-walk recovery).
        """
        # 1. Checks: Don't attack if in PZ
        if self.buffs.get('pz', False):
            return
            
        # Only check delay if we are NOT forcing the attack
        if not force:
            if self.isAttacking() or not self.delays.due("attack_click"):
                return

        # 2. Capture and Scan (Rest of your existing logic...)
        region = self.s_BattleList.region
        image = img.screengrab_array(self.hwnd, region)
        if image is None: return

        height, width, _ = image.shape
        rel_x, start_y, step_y = 25, 30, 22

        for rel_y in range(start_y, height, step_y):
            if rel_y >= height or rel_x >= width: break
            pixel = image[rel_y, rel_x]

            if pixel[0] == 0 and pixel[1] == 0 and pixel[2] == 0:
                abs_x, abs_y = region[0] + rel_x, region[1] + rel_y
                click_client(self.hwnd, abs_x, abs_y)
                self.delays.trigger("attack_click")
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
        
    def useAreaRune(self):
        """Precision Rune placement using a geometric bitmask."""
        if not self.delays.due("area_rune") or not self.monster_positions:
            return False

        # 2. Build a binary Monster Grid (11x15)
        m_grid = np.zeros((11, 15), dtype=int)
        tile_w = self.s_GameScreen.tile_w
        tile_h = self.s_GameScreen.tile_h

        for mx, my in self.monster_positions:
            col = int(mx // tile_w)
            row = int(my // tile_h)
            if 0 <= row < 11 and 0 <= col < 15:
                m_grid[row, col] = 1

        # 3. Slide Mask over the Grid to find the best impact tile
        best_hits = 0
        best_tile = None
        
        # We iterate over internal tiles to keep the 7x7 mask on-screen
        for r in range(3, 8): 
            for c in range(3, 12):
                # Extract the 7x7 neighborhood
                neighborhood = m_grid[r-3:r+4, c-3:c+4]
                # Matrix multiplication count
                current_hits = np.sum(neighborhood * BotConstants.RUNE_MASK)
                
                if current_hits > best_hits:
                    best_hits = current_hits
                    best_tile = (r, c)

        # 4. Fire if threshold is met
        if best_tile and best_hits >= self.min_monsters_for_rune.get():
            tr, tc = best_tile
            self.best_rune_tile = best_tile # Store for visualization
            
            gs = self.s_GameScreen.region
            # Click center of tile + small random jitter
            target_px_x = int(gs[0] + (tc + 0.5) * tile_w) + np.random.randint(-4, 4)
            target_px_y = int(gs[1] + (tr + 0.5) * tile_h) + np.random.randint(-4, 4)

            if self.clickActionbarSlot(self.slots.get("area_rune")):
                click_client(self.hwnd, target_px_x, target_px_y)
                self.delays.trigger("area_rune")
                self.updateLastAttackTime()
                print(f"[COMBAT] Precision Rune: Hit {best_hits} monsters.")
                return True
        return False

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
    
    def manageKnightSupport(self):
        if self.vocation != "knight":
            return

        # Buff de Daño (Utito Tempo)
        if self._bool_value(self.use_utito):
            self.utito() # Este método ya tiene su propio delay interno de 10s

        # Actualizar monstruos alrededor (usando el área de hechizos configurada)
        self.monsters_around = self.getMonstersAround(self.areaspell_area, True, True)
        self.monster_count = self.monsterCount()

        if self.monsters_around > 0:
            # --- Exeta Res ---
            if self._bool_value(self.res): # Usamos _bool_value para estar seguros
                if "exeta" in self.slots:
                    self.castExetaRes()

            # --- Amp Res ---
            if self._bool_value(self.amp_res):
                monsters_in_melee = self.getMonstersAround(3, False, False)
                # Si hay más monstruos en pantalla que en cuerpo a cuerpo, traerlos
                if monsters_in_melee < self.monster_count:
                    if "amp_res" in self.slots:
                        self.castAmpRes()

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
        if self._bool_value(self.attack) and self.isAttacking():
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
            # 1. Get coordinates from your OCR/Scan logic
            name_rect = self.party[leader_name]["name_rect"] # (x1, y1, x2, y2)
            
            # 2. Calculate center in Client Coords
            click_x_client = (name_rect[0] + name_rect[2]) // 2
            click_y_client = (name_rect[1] + name_rect[3]) // 2

            # 3. Convert to Screen Coords (to fix the 'Title Bar' offset)
            screen_pt = win32gui.ClientToScreen(self.hwnd, (click_x_client, click_y_client))
            screen_x, screen_y = screen_pt[0], screen_pt[1]

            # 4. Store mouse and move
            _, _, (orig_x, orig_y) = win32gui.GetCursorInfo()
            
            # 5. Right Click using Physical Click
            physical_click(self.hwnd,screen_x, screen_y, right=True)
            time.sleep(0.2)
            
            # 6. Click the 'Follow' option (Blind offset)
            # Standard Tibia context menu 'Follow' is usually ~35px right, ~35px down
            # Note: If this misses, we can use the 37px boundary logic here too
            physical_click(self.hwnd,screen_x + 35, screen_y + 35, right=False)
            
            # 7. Return mouse
            win32api.SetCursorPos((orig_x, orig_y))
            return True

        except Exception as e:
            print(f"Error in followLeader: {e}")
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
                
                # Perform OCR
                raw_name = img.tesser_image(name_img, 124, 255, 1, config='--psm 7')
                print(f"[DEBUG OCR] Row {i} raw read: '{raw_name}'")

                # Match against known list
                name_found = False
                # FIX: use self.config.data["characters"]
                for n in self.config.data.get("characters", {}).keys():   
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
        # 1. Update basic state for this frame
        marks = self.getClosestMarks()
        self.monster_count = self.monsterCount() # Ensure this is fresh
        kill_time = time.time() - self.kill_start_time
        
        # --- 2. STATE MACHINE (Toggle Kill Mode) ---
        if not self.kill:
            if self.monster_count >= self.kill_amount.get():
                print(f"[CAVEBOT] Switching to KITING. Monsters: {self.monster_count}")
                self.kill = True
                self.kill_start_time = time.time()
                self.clickStop()
        else:
            if self.monster_count <= self.kill_stop_amount.get() or kill_time > self.kill_stop_time:
                print(f"[CAVEBOT] Switching to LURING/WALKING.")
                if self.manual_loot.get() and self.monster_count == 0:
                    for i in range(0, 2): self.lootAround()
                self.kill = False

        # --- 3. THE PROGRESSION ENGINE (No Lock) ---
        # This part runs every frame to see if we reached our waypoint landmark.
        if marks:
            dist, abs_pos, rel_pos = marks[0]
            
            # Arrival Threshold: 6px for walking, 18px "Soft Arrival" for forward kiting
            arrival_threshold = 6
            if self.kill and self.kiting_mode.get().lower() == "forward":
                arrival_threshold = 18

            if dist <= arrival_threshold:
                # --- MEMORY & DISCOVERY ---
                # Update memory so Backward kiting knows where we just were
                self.last_reached_mark_rel = rel_pos
                
                # Check fingerprint to prevent loop-stuck
                is_seen, score, idx = self.is_visited_detailed(rel_pos)
                total_nodes = len(self.visited_fingerprints)
                mem_limit = max(1, int(total_nodes * 0.5))

                if idx != -1 and score > 0.88:
                    if idx not in self.visited_history:
                        self.visited_history.append(idx)
                        while len(self.visited_history) > mem_limit:
                            self.visited_history.popleft()
                elif self.discovery_mode:
                    # Save new landmark during the first lap
                    fp = self.get_mark_fingerprint(rel_pos)
                    new_idx = len(self.visited_fingerprints)
                    self.visited_fingerprints.append({"pixels": fp, "type": self.current_mark})
                    self.visited_history.append(new_idx)
                    print(f"[MEMORY] Saved new node {new_idx} for {self.current_mark}")

                # --- ADVANCE TO NEXT MARK ---
                print(f"[CAVEBOT] Node {self.current_mark} reached ({int(dist)}px). Advancing.")
                self.clickStop()
                self.nextMark()
                
                # REFRESH: Get the NEW mark data immediately so kiting/walking 
                # uses the new destination in this same frame.
                marks = self.getClosestMarks()

        # --- 4. NAVIGATION RESET (Fallback if no marks visible) ---
        if not marks:
            if self.current_mark == self.mark_list[-1]: 
                self.loop_count += 1
                self.discovery_mode = False
                print(f"[CAVEBOT] Loop #{self.loop_count} Reset.")
                self.current_mark_index = 0
                self.current_mark = self.mark_list[0]
                marks = self.getClosestMarks() 
                if not marks: return 
            else:
                self.nextMark()
                return

        # --- 5. EXECUTION (Final Movement Step) ---
        # Unpack the (potentially refreshed) mark data
        dist, abs_pos, rel_pos = marks[0]

        if self.kill:
            # ACTIVE COMBAT MOVEMENT
            if self.monster_count >= 1:
                if self.use_recenter.get():
                    self.recenter_on_pack()
                elif self.use_kiting.get():
                    # Will kite toward rel_pos (either the current mark or the new one if we just advanced)
                    self.kite_from_pack(next_mark_rel=rel_pos)
            return # Block passive navigation while kiting

        # PASSIVE NAVIGATION MOVEMENT (Luring/Walking)
        if self.use_lure_walk.get() and self.monster_count > 0:
            self.executeLureWalk(abs_pos)
        elif self.delays.allow("walk", base_ms=250):
            click_client(self.hwnd, abs_pos[0], abs_pos[1])
    
    
    def executeLureWalk(self, mark_pos):
        # If the setting is off or no monsters, walk normally
        if not self.use_lure_walk.get() or self.monster_count == 0:
            if self.delays.allow("walk", base_ms=200):
                click_client(self.hwnd, mark_pos[0], mark_pos[1])
            return

        now = time.time()
        elapsed_ms = (now - self.last_lure_action_time) * 1000

        if self.lure_phase == "walking":
            if elapsed_ms >= self.lure_walk_ms.get():
                # --- THE FIX ---
                # 1. See if we were attacking before we hit Stop
                was_attacking = self.isAttacking()
                
                # 2. Stop movement (and unfortunately, attack)
                self.clickStop()
                
                # 3. If we were attacking, resume IMMEDIATELY
                if was_attacking:
                    self.clickAttack(force=True)
                # ---------------

                self.lure_phase = "stopping"
                self.last_lure_action_time = now
            else:
                # Maintain direction while walking
                if self.delays.allow("walk", base_ms=250):
                    click_client(self.hwnd, mark_pos[0], mark_pos[1])

        elif self.lure_phase == "stopping":
            if elapsed_ms >= self.lure_stop_ms.get():
                self.lure_phase = "walking"
                self.last_lure_action_time = now
                click_client(self.hwnd, mark_pos[0], mark_pos[1])

    def recenter_on_pack(self):
        """Aggressive recentering to maximize AoE spell coverage."""
        if not self.delays.due("centering") or not self.monster_positions:
            return

        p_center = self.s_GameScreen.getRelativeCenter()
        tile_size = self.s_GameScreen.tile_h

        # 1. Calculate Vector to Centroid
        avg_mx = sum([m[0] for m in self.monster_positions]) / len(self.monster_positions)
        avg_my = sum([m[1] for m in self.monster_positions]) / len(self.monster_positions)
        
        dx = avg_mx - p_center[0]
        dy = avg_my - p_center[1]
        dist = sqrt(dx**2 + dy**2)

        # --- AGGRESSION TWEAKS ---
        # Lowered minimum distance from 1.5 tiles to 0.6 tiles.
        # If the pack center is even slightly off, we step toward it.
        if dist < (tile_size * 0.6) or dist > (tile_size * 7):
            return

        # 2. Determine Discrete Direction
        # Lowered threshold from 0.4 to 0.2 to make it much more sensitive to diagonal packs
        dir_x = 0
        if dx > (tile_size * 0.2): dir_x = 1
        elif dx < -(tile_size * 0.2): dir_x = -1

        dir_y = 0
        if dy > (tile_size * 0.2): dir_y = 1
        elif dy < -(tile_size * 0.2): dir_y = -1

        # 3. Target Tile Coordinates
        target_rel_x = p_center[0] + (dir_x * tile_size)
        target_rel_y = p_center[1] + (dir_y * tile_size)

        # 4. Obstacle Check (Stay strict here to avoid walking INTO a monster)
        for mx, my in self.monster_positions:
            m_dist = sqrt((mx - target_rel_x)**2 + (my - target_rel_y)**2)
            if m_dist < (tile_size * 0.4):
                return

        # 5. Execute Step using the new Physical Click logic for reliability
        gs_region = self.s_GameScreen.region
        abs_cx = int(gs_region[0] + target_rel_x)
        abs_cy = int(gs_region[1] + target_rel_y)
        # Use physical_click to ensure the movement is registered during high-action combat
        click_client(self.hwnd, abs_cx, abs_cy)
        
        # Immediate Attack Resume
        self.GUI.root.after(30, lambda: self.clickAttack(force=True))
        self.delays.trigger("centering")

    def is_actually_moving(self, map_img):
        """
        Ultra-fast movement check using sparse pixel sampling.
        """
        mw, mh = map_img.shape[1], map_img.shape[0]
        cx, cy = mw // 2, mh // 2
        
        current_colors = []
        for dx, dy in self.stuck_check_coords:
            current_colors.append(tuple(map_img[cy + dy, cx + dx]))
        
        if not self.last_stuck_colors:
            self.last_stuck_colors = current_colors
            return True

        # Check if all sampled pixels are identical to last check
        if current_colors == self.last_stuck_colors:
            self.stuck_counter += 1
        else:
            self.stuck_counter = 0
            self.last_stuck_colors = current_colors

        # If we haven't changed a single pixel in 5 checks (~500ms), we are stuck
        return self.stuck_counter < 5
    
    def kite_from_pack(self, next_mark_rel=None):
        # 1. Traversal Governor: If we just clicked recently, don't interrupt
        if not self.delays.due("kiting") or not self.monster_positions:
            return

        if self.collision_grid is None:
            return

        # 2. Movement Check (Stuck detection)
        map_img = img.screengrab_array(self.hwnd, self.s_Map.region)
        stuck_boost = 0
        if map_img is not None and not self.is_actually_moving(map_img):
            stuck_boost = 250 # Increased panic for being stuck
        else:
            # If we are already moving smoothly, we can actually afford to wait longer
            # to let the animation finish.
            self.stuck_counter = 0

        p_center = self.s_GameScreen.getRelativeCenter()
        tile_size = self.s_GameScreen.tile_h
        p_row, p_col = 5, 7 

        # 3. Mode Configuration & Weights
        mode = self.kiting_mode.get().lower() 
        attract_vec = (0, 0)
        
        # Slightly softer weights to prevent erratic "twitching"
        w_monster_repulsion = 1.1 
        w_mark_attraction = 90.0  
        w_wall_penalty = 120.0   
        w_center_bonus = 25.0    

        if mode == "forward" and next_mark_rel:
            m_dx = next_mark_rel[0] - (self.s_Map.center[0] - self.s_Map.region[0])
            m_dy = next_mark_rel[1] - (self.s_Map.center[1] - self.s_Map.region[1])
            mag = sqrt(m_dx**2 + m_dy**2) + 0.01
            attract_vec = (m_dx/mag, m_dy/mag)
            
        elif mode == "backward" and hasattr(self, 'last_reached_mark_rel') and self.last_reached_mark_rel:
            m_dx = self.last_reached_mark_rel[0] - (self.s_Map.center[0] - self.s_Map.region[0])
            m_dy = self.last_reached_mark_rel[1] - (self.s_Map.center[1] - self.s_Map.region[1])
            mag = sqrt(m_dx**2 + m_dy**2) + 0.01
            attract_vec = (m_dx/mag, m_dy/mag)
            w_monster_repulsion = 4.0
            w_mark_attraction = 20.0

        avg_mx = sum([m[0] for m in self.monster_positions]) / len(self.monster_positions)
        avg_my = sum([m[1] for m in self.monster_positions]) / len(self.monster_positions)

        # 4. Scoring Engine
        directions = [(-1,0), (1,0), (0,-1), (0,1), (-1,-1), (-1,1), (1,-1), (1,1)]
        best_score = -999999
        best_move = (0, 0, 1)

        for dy, dx in directions:
            tr, tc = p_row + dy, p_col + dx
            if self.collision_grid[tr, tc] == 1: continue 
            
            if dx != 0 and dy != 0:
                if self.collision_grid[p_row + dy, p_col] == 1 or self.collision_grid[p_row, p_col + dx] == 1:
                    continue

            # DYNAMIC PROBING (1-3 tiles)
            max_probe = 1
            for d in [2, 3]:
                pr, pc = p_row + (dy * d), p_col + (dx * d)
                if 0 <= pr < 11 and 0 <= pc < 15:
                    if self.collision_grid[pr, pc] == 0:
                        max_probe = d
                    else:
                        break
            
            # Use a slightly more conservative probe to avoid "over-running"
            actual_probe = np.random.choice(range(1, max_probe + 1))

            tx_px = p_center[0] + (dx * tile_size)
            ty_px = p_center[1] + (dy * tile_size)
            score = 0

            # --- SCORE CALCULATION ---
            dist_to_pack = sqrt((tx_px - avg_mx)**2 + (ty_px - avg_my)**2)
            score += dist_to_pack * w_monster_repulsion

            if stuck_boost > 0:
                score += np.random.randint(0, stuck_boost)
            elif mode != "random":
                move_dot_attract = (dx * attract_vec[0]) + (dy * attract_vec[1])
                score += move_dot_attract * w_mark_attraction

            # Multi-scale wall avoidance
            wall_count_near = np.sum(self.collision_grid[tr-1:tr+2, tc-1:tc+2])
            wall_count_far = np.sum(self.collision_grid[max(0, tr-2):tr+3, max(0, tc-2):tc+3])
            score -= (wall_count_near * w_wall_penalty)
            score -= (wall_count_far * 15)
            if wall_count_near == 0: score += w_center_bonus

            # Strict melee penalty
            melee_dist = 0.9 if mode == "forward" else 1.2
            for mx, my in self.monster_positions:
                m_dist = sqrt((mx - tx_px)**2 + (my - ty_px)**2)
                if m_dist < (tile_size * melee_dist):
                    score -= 2000 

            if score > best_score:
                best_score = score
                best_move = (dx, dy, actual_probe)

        # 5. EXECUTION WITH VARIABLE DELAY
        if best_move != (0, 0, 0):
            dx, dy, d_dist = best_move
            gs = self.s_GameScreen.region
            
            target_x = int(gs[0] + p_center[0] + (dx * tile_size * d_dist) + np.random.randint(-4, 4))
            target_y = int(gs[1] + p_center[1] + (dy * tile_size * d_dist) + np.random.randint(-4, 4))
            
            click_client(self.hwnd, target_x, target_y)
            
            # --- THE DYNAMIC GOVERNOR ---
            # If we clicked 3 tiles away, we need to wait longer for the character to get there.
            # Base delay (450ms) + 150ms per extra tile.
            dynamic_delay = 600 + (d_dist - 1) * 150
            self.delays.trigger("kiting", base_ms=dynamic_delay)
            
            self.GUI.root.after(30, lambda: self.clickAttack(force=True))

    def reset_marks_history(self):
        """Manually clears the 'visited' status of map marks."""
        print("[CAVEBOT] Resetting mark history. All marks are now fresh.")
        for mark in self.mark_list:
            self.previous_marks[mark] = False
        # Optional: Reset index to start from the beginning of the list
        self.current_mark_index = 0
        self.current_mark = self.mark_list[0]
           
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
        self.current_mark_index += 1
        if self.current_mark_index >= len(self.mark_list):
            self.current_mark_index = 0
            
        self.current_mark = self.mark_list[self.current_mark_index]
        print(f"[CAVEBOT] Next target mark: {self.current_mark}")
        
        # Debounce to prevent skipping multiple marks in one frame
        self.delays.trigger("walk", base_ms=500)
    
    def nextAddMark(self):
        """Advances the sequence for the manual painting tool only."""
        self.add_mark_index += 1
        if self.add_mark_index >= len(self.mark_list):
            self.add_mark_index = 0
        self.add_mark_type = self.mark_list[self.add_mark_index]
        print(f"[PAINTER] Ready for next mark: {self.add_mark_type}")
        
    def get_mark_fingerprint(self, rel_pos):
        """Captures a 20x20 visual patch around a mark's relative coordinates."""
        rx, ry = rel_pos
        map_reg = self.s_Map.region
        # Absolute region for the fingerprint
        fp_reg = (map_reg[0] + rx - 10, map_reg[1] + ry - 10, 
                  map_reg[0] + rx + 10, map_reg[1] + ry + 10)
        return img.screengrab_array(self.hwnd, fp_reg)

    def getClosestMarks(self):
        scale = 3 
        map_region = self.s_Map.region
        mw, mh = map_region[2] - map_region[0], map_region[3] - map_region[1]
        map_rel_center = (self.s_Map.center[0] - map_region[0], self.s_Map.center[1] - map_region[1])
        
        map_img = img.screengrab_array(self.hwnd, map_region)
        if map_img is None: return []
        map_hd = cv2.resize(map_img, (mw * scale, mh * scale), interpolation=cv2.INTER_CUBIC)
        
        positions = img.locateManyImage(self.hwnd, f"map_marks/{self.current_mark}.png", map_region, 0.90)
        
        result = []
        if positions:
            for pos in positions:
                rel_x, rel_y = int(pos[0] + pos[2]/2), int(pos[1] + pos[3]/2)
                vis_lap, score, seq_idx = self.is_visited_detailed((rel_x, rel_y))
                
                hd_x, hd_y = rel_x * scale, rel_y * scale
                box_rad = 3 * scale 

                # Color logic for the GUI
                if vis_lap:
                    color, thick = (0, 0, 200), 1 # Red (Already Walked)
                else:
                    color, thick = (0, 255, 0), 2 # Green (Valid Target)

                # Draw to GUI buffer
                cv2.rectangle(map_hd, (hd_x - box_rad, hd_y - box_rad), (hd_x + box_rad, hd_y + box_rad), color, thick)
                cv2.putText(map_hd, f"{int(score*100)}%", (hd_x + 5, hd_y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255,255,255), 1)

                # ONLY add to navigation result if NOT visited this lap
                if not vis_lap:
                    dist = distance.euclidean(map_rel_center, (rel_x, rel_y))
                    result.append((dist, (map_region[0] + rel_x, map_region[1] + rel_y), (rel_x, rel_y)))

        result.sort(key=lambda x: x[0])
        self.current_map_image = map_hd
        return result

    def is_visited_detailed(self, rel_pos):
        """Returns (bool: visited_this_lap, float: highest_score, int: sequence_index)"""
        map_region = self.s_Map.region
        mw, mh = map_region[2] - map_region[0], map_region[3] - map_region[1]
        rx, ry = rel_pos
        rad = 10  # This defines our 20x20 search area (radius 10)
        
        # 1. Determine the actual screen coordinates to capture (clamped to minimap)
        fp_x1, fp_y1 = max(0, rx - rad), max(0, ry - rad)
        fp_x2, fp_y2 = min(mw, rx + rad), min(mh, ry + rad)
        
        # 2. Calculate the 'Local Trim' within the 20x20 saved patch
        # This aligns the saved pixels with the current screen capture
        t_x1 = fp_x1 - (rx - rad)
        t_y1 = fp_y1 - (ry - rad)
        t_x2 = t_x1 + (fp_x2 - fp_x1)
        t_y2 = t_y1 + (fp_y2 - fp_y1)
        
        current_fp = img.screengrab_array(self.hwnd, (map_region[0] + fp_x1, map_region[1] + fp_y1, 
                                                     map_region[0] + fp_x2, map_region[1] + fp_y2))
        
        if current_fp is None or not self.visited_fingerprints: 
            return False, 0.0, -1

        highest_score = 0.0
        best_index = -1
        visited_this_lap = False

        for idx, data in enumerate(self.visited_fingerprints):
            saved_pixels = data["pixels"]
            
            # Crop the saved 20x20 fingerprint to match the currently visible window
            comparable_saved = saved_pixels[t_y1:t_y2, t_x1:t_x2]
            
            if current_fp.shape != comparable_saved.shape:
                continue
                
            res = cv2.matchTemplate(current_fp, comparable_saved, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            
            if max_val > highest_score:
                highest_score = max_val
                best_index = idx
                visited_this_lap = data.get("visited_this_lap", False)
            
            if max_val > 0.96: break # Exit early on near-perfect match
                
        # threshold for logical 'visited' state
        is_visited_recently = (highest_score > 0.88) and (best_index in self.visited_history)
        
        return is_visited_recently, highest_score, best_index
    
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



    def _place_mark_at_screen_coords(self, client_x, client_y):
        """
        Now uses Client Coordinates because physical_click handles the Screen translation.
        """
        # 1. Store original screen mouse position
        _, _, (orig_x, orig_y) = win32gui.GetCursorInfo()
        
        try:
            map_reg = self.s_Map.region
            # rel_x helps determine if menu opens left or right
            rel_x = client_x - map_reg[0]
            
            # 2. Open Context Menu
            physical_click(self.hwnd,client_x, client_y, right=True)
            time.sleep(0.08) 

            # 3. Calculate Menu Option Position (Client-relative)
            if rel_x < 37:
                menu_x, menu_y = client_x + 45, client_y + 10
            else:
                menu_x, menu_y = client_x - 45, client_y + 10

            # 4. Click 'Create Mark'
            physical_click(self.hwnd,menu_x, menu_y, right=False)
            time.sleep(0.1)
            
            # 5. Wait for the 'Edit Mark' dialog and force a frame refresh
            print(f"[PAINTER] Waiting for dialog to search for {self.add_mark_type}...")
            
            icon_pos = None
            search_reg = (self.width//4, self.height//4, 3*self.width//4, 3*self.height//4)
            icon_path = f"map_marks/{self.add_mark_type}.png"

            # Retry Loop: This is crucial because BackgroundFrameGrabber 
            # might need a few cycles to catch the new window.
            for attempt in range(6):
                time.sleep(0.05)
                self.updateFrame() # FORCE the grabber to pull a new frame from the GPU
                
                icon_pos = img.locateImage(self.hwnd, icon_path, search_reg, 0.90)
                if icon_pos:
                    break
            
            if icon_pos:
                ix, iy, iw, ih = icon_pos
                target_ix = search_reg[0] + ix + (iw//2)
                target_iy = search_reg[1] + iy + (ih//2)
                
                # 6. Click Icon and Save
                physical_click(self.hwnd,target_ix, target_iy, right=False)
                time.sleep(0.05)
                win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
                time.sleep(0.05)
                win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
                
                print(f"[PAINTER] Success: Placed {self.add_mark_type}.")
                self.nextAddMark()
            else:
                win32api.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
                time.sleep(0.05)
                win32api.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
                print(f"[PAINTER] Could not find {self.add_mark_type} icon in the capture buffer.")

        finally:
            # 7. Snap mouse back
            win32api.SetCursorPos((orig_x, orig_y))

    def mark_at_mouse(self):
        if not self.delays.allow("manual_mark", base_ms=1200): return
        _, _, (sx, sy) = win32gui.GetCursorInfo()
        
        # Convert Screen -> Client so it plays nice with our new physical_click
        point = win32gui.ScreenToClient(self.hwnd, (sx, sy))
        self._place_mark_at_screen_coords(point[0], point[1])

    def mark_at_player(self):
        if not self.delays.allow("manual_mark", base_ms=1200): return
        # Minimap center is already in Client coords
        map_reg = self.s_Map.region
        cx = (map_reg[0] + map_reg[2]) // 2
        cy = (map_reg[1] + map_reg[3]) // 2
        self._place_mark_at_screen_coords(cx, cy)

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

    def sell_item_at_mouse(self):
        """
        Contextual macro: Clicks an item and confirms the trade via the 'OK' button.
        """
        client_origin = win32gui.ClientToScreen(self.hwnd, (0, 0))
        # 1. Store original position and click the item
        _, _, (orig_x, orig_y) = win32gui.GetCursorInfo()
        
        # We use a slight delay between actions for client stability
        physical_click(self.hwnd, orig_x - client_origin[0], orig_y - client_origin[1], right=False)
        time.sleep(0.1)

        # 2. Define search region for the 'OK' button
        # The button is usually 100-300 pixels below the item list
        # Search Box: [MouseX - 100, MouseY, MouseX + 200, MouseY + 400]
        # We convert screen coords to client coords for the search function
        
        client_pt = win32gui.ScreenToClient(self.hwnd, (orig_x, orig_y))
        print(f"client_pt: {client_pt}, client_origin: {client_origin}")
        search_region = (
            max(0, client_pt[0] - 150), 
            client_pt[1], 
            min(self.width, client_pt[0] + 150), 
            min(self.height, client_pt[1] + 450)
        )

        # 3. Locate the 'OK' Button
        # We call updateFrame to ensure we see the result of our first click
        self.updateFrame()
        ok_btn = img.locateImage(self.hwnd, 'hud/npc_trade_ok.png', search_region, 0.90)

        if ok_btn:
            ix, iy, iw, ih = ok_btn
            # Calculate absolute click target
            target_x = search_region[0] + ix + (iw // 2)
            target_y = search_region[1] + iy + (ih // 2)

            # 4. Click 'OK' and return mouse
            physical_click(self.hwnd, target_x, target_y, right=False)
            time.sleep(0.05)
            win32api.SetCursorPos((orig_x, orig_y))
            print("[TRADE] Item sold and confirmed.")
        else:
            print("[TRADE] Could not find OK button near mouse.")
            # Return mouse anyway in case of failure
            win32api.SetCursorPos((orig_x, orig_y))

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
    
    def cycle_map_scale(self):
        """Cycles the map scale: 1 -> 2 -> 4 -> 1"""
        if self.map_scale == 1: self.map_scale = 2
        elif self.map_scale == 2: self.map_scale = 4
        else: self.map_scale = 1
        print(f"[MAP] Manual Scale set to: {self.map_scale} px/tile")

    def manageKeys(self):
        if not self.key_pressed:
            return

        # 'keyboard' library uses string names
        key = self.key_pressed.lower()

        # --- GLOBAL KEYS ---
        if key == 'page up':
            self.attack.set(not self.attack.get())
        elif key == 'page down':
            self.follow_party.set(not self.follow_party.get())
        elif key == 'end':
            self.use_area_rune.set(not self.use_area_rune.get())
        if self.key_pressed == keyboard.Key.insert: # Or any key you prefer
            self.cycle_map_scale()
        # --- FOREGROUND-ONLY KEYS ---
        if isTopWindow(self.hwnd):
            if key == 'f11':
                self.mark_at_mouse()
            elif key == 'f12':
                self.mark_at_player()

        self.key_pressed = False
    
    def manageKeysSync(self):
        """
        Checks for key presses synchronously to avoid background thread crashes.
        """
        # --- GLOBAL KEYS ---
        if kb.is_pressed('page up'):
            if not self.key_debounce: # Simple flag to prevent rapid toggling
                self.attack.set(not self.attack.get())
                self.key_debounce = True
        elif kb.is_pressed('page down'):
            if not self.key_debounce:
                self.follow_party.set(not self.follow_party.get())
                self.key_debounce = True
        elif kb.is_pressed('insert'): # Or any key you prefer
            if not self.key_debounce:
                self.cycle_map_scale()
                self.key_debounce = True
        else:
            self.key_debounce = False # Reset debounce when key is released

        # --- FOREGROUND KEYS ---
        if isTopWindow(self.hwnd):
            if kb.is_pressed('f11'):
                self.mark_at_mouse()
            elif kb.is_pressed('f12'):
                self.mark_at_player()
            elif kb.is_pressed('f10'): # New Sell Hotkey
                if not self.delays.allow("manual_mark", base_ms=500): return
                self.sell_item_at_mouse()


    def detect_minimap_scale(self, map_img):
        try:
            # Get dimensions and constants
            mh, mw = map_img.shape[:2]
            cx, cy = mw // 2, mh // 2
            TERRAIN = np.array(BotConstants.OBSTACLES + BotConstants.WALKABLE, dtype=np.uint8)

            # Define scan strips (Wider range to get more data points in one go)
            x_start, x_end = max(0, cx - 90), min(mw, cx + 90)
            y_start, y_end = max(0, cy - 60), min(mh, cy + 60)

            strips = [
                map_img[np.clip(cy - 40, 0, mh-1), x_start:x_end], 
                map_img[np.clip(cy + 40, 0, mh-1), x_start:x_end], 
                map_img[y_start:y_end, np.clip(cx + 45, 0, mw-1)].reshape(-1, 3),
                map_img[y_start:y_end, np.clip(cx - 45, 0, mw-1)].reshape(-1, 3)
            ]

            distances = []
            for strip in strips:
                if strip.size == 0: continue
                # Mask pixels that are known terrain
                is_terrain = np.any(np.all(strip[:, None] == TERRAIN, axis=-1), axis=-1)
                
                last_idx = -1
                for i in range(1, len(strip)):
                    if is_terrain[i] and is_terrain[i-1]:
                        if not np.array_equal(strip[i], strip[i-1]):
                            if last_idx != -1:
                                d = i - last_idx
                                if 1 <= d <= 16: distances.append(d)
                            last_idx = i

            # --- INSTANT DECISION LOGIC ---
            # If we don't find enough edges, we don't have enough data to change our mind.
            if len(distances) < 3:
                return self.map_scale

            counts = Counter(distances)
            
            # 1. Evidence for Scale 1 (The most common zoom)
            # If we see 1s or 3s, it's Scale 1.
            if counts[1] > 0 or counts[3] > 0:
                new_scale = 1
            # 2. Evidence for Scale 2
            # If no 1s, but we see 2s or 6s, it's Scale 2.
            elif counts[2] > 0 or counts[6] > 0:
                new_scale = 2
            # 3. Scale 4
            # If everything found is 4, 8, 12...
            elif counts[4] > 0:
                new_scale = 4
            else:
                # No change if results are ambiguous
                return self.map_scale

            if new_scale != self.map_scale:
                print(f"[AUTO-SCALE] Instant switch detected: {new_scale}px/tile")
                self.map_scale = new_scale

            return self.map_scale

        except Exception as e:
            return self.map_scale

    def get_local_collision_map(self):
        map_img = img.screengrab_array(self.hwnd, self.s_Map.region)
        if map_img is None: 
            return None, self.map_scale

        S = self.map_scale 
        mh, mw = map_img.shape[0], map_img.shape[1]
        cx, cy = mw // 2, mh // 2
        
        # 1. Prepare Obstacle Data (The Blacklist)
        OBS = np.array(BotConstants.OBSTACLES, dtype=np.uint8)
        
        # 2. Vectorized Color Sampling
        local_data = np.zeros((11, 15, 3), dtype=np.uint8)
        for r in range(11):
            for c in range(15):
                px, py = cx + (c - 7) * S, cy + (r - 5) * S
                if 0 <= px < mw and 0 <= py < mh:
                    local_data[r, c] = map_img[py, px]
                else:
                    # Boundaries/Outside map treated as walls
                    local_data[r, c] = [0, 0, 0] 

        # 3. Terrain Check: "Blacklist" approach
        # Marks are NOT in the obstacle list, so they will stay False (Walkable)
        is_obstacle = np.zeros((11, 15), dtype=bool)
        for r in range(11):
            for c in range(15):
                color = local_data[r, c]
                # If the sampled pixel matches ANY known obstacle color exactly
                if np.any(np.all(color == OBS, axis=-1)):
                    is_obstacle[r, c] = True
                else:
                    # EVERYTHING ELSE (Marks, UI, Grass, Water, New terrain) is Walkable
                    is_obstacle[r, c] = False

        # 4. Initialize Grid
        grid = np.zeros((11, 15), dtype=int)
        grid[is_obstacle] = 1
        grid[5, 7] = 3 # Player tile constant

        # 5. Apply 3-Point Connectivity interpolation (Preserved)
        # We KEEP this because it connects detected obstacles to form solid walls
        if S == 1:
            grid[5:7, 5:11] = 0; grid[3:9, 7:9] = 0; grid[5, 7] = 3
            for c in [5, 6]: # WEST
                if grid[4, c] == 1 and grid[7, c] == 1 and is_obstacle[5:7, c-1].all():
                    grid[5:7, c] = 1
            for c in [9, 10]: # EAST
                if grid[4, c] == 1 and grid[7, c] == 1 and is_obstacle[5:7, c+1].all():
                    grid[5:7, c] = 1
            for r in [3, 4]: # NORTH
                if grid[r, 6] == 1 and grid[r, 9] == 1 and is_obstacle[r-1, 7:9].all():
                    grid[r, 7:9] = 1
            for r in [7, 8]: # SOUTH
                if grid[r, 6] == 1 and grid[r, 9] == 1 and is_obstacle[r+1, 7:9].all():
                    grid[r, 7:9] = 1
        else:
            # Scale 2 and 4 interpolation
            grid[4, 7] = 0; grid[6, 7] = 0; grid[5, 6] = 0; grid[5, 8] = 0
            if is_obstacle[3, 7] and grid[4, 6] == 1 and grid[4, 8] == 1: grid[4, 7] = 1
            if is_obstacle[7, 7] and grid[6, 6] == 1 and grid[6, 8] == 1: grid[6, 7] = 1
            if is_obstacle[5, 5] and grid[4, 6] == 1 and grid[6, 6] == 1: grid[5, 6] = 1
            if is_obstacle[5, 9] and grid[4, 8] == 1 and grid[6, 8] == 1: grid[5, 8] = 1

        return grid, S
    def get_player_grid_pos(self):  
        """Standardized center of the 15x11 grid."""
        return (5, 7) # (row, col)
    
    def visualize_monster_grid(self, collision_grid, current_s):
        try:
            # Skip if calculation failed
            if collision_grid is None: return
            
            region = self.s_GameScreen.region
            frame = img.screengrab_array(self.hwnd, region)
            if frame is None: return
            
            vis = np.ascontiguousarray(frame, dtype=np.uint8)
            overlay = vis.copy()
            
            # FLOAT MATH for perfect sync
            gr_w, gr_h = self.s_GameScreen.getWidth(), self.s_GameScreen.getHeight()
            tile_w_float = gr_w / 15.0
            tile_h_float = gr_h / 11.0
            
            p_row, p_col = 5, 7

            # --- DRAW UI ---

            # --- DRAW GRID ---
            for row in range(11):
                for col in range(15):
                    tx = int(col * tile_w_float)
                    ty = int(row * tile_h_float)
                    tx2 = int((col + 1) * tile_w_float)
                    ty2 = int((row + 1) * tile_h_float)
                    
                    if row == p_row and col == p_col:
                        cv2.rectangle(overlay, (tx, ty), (tx2, ty2), (0, 255, 0), 2)
                    elif collision_grid is not None and collision_grid[row, col] == 1:
                        cv2.rectangle(overlay, (tx, ty), (tx2, ty2), (180, 50, 0), -1)
                    
                    cv2.rectangle(vis, (tx, ty), (tx2, ty2), (45, 45, 45), 1)

            # --- DRAW MONSTERS ---
            if hasattr(self, 'monster_positions') and self.monster_positions:
                for mx, my in self.monster_positions:
                    m_col = int(mx / tile_w_float)
                    m_row = int(my / tile_h_float)
                    
                    tx = int(m_col * tile_w_float)
                    ty = int(m_row * tile_h_float)
                    tx2 = int((m_col + 1) * tile_w_float)
                    ty2 = int((m_row + 1) * tile_h_float)
                    
                    # IGNORE PLAYER (Safety Check)
                    if m_col == p_col and m_row == p_row:
                        continue
                        
                    cv2.rectangle(overlay, (tx, ty), (tx2, ty2), (0, 0, 150), -1)
                    cv2.circle(vis, (int(mx), int(my)), 2, (0, 255, 0), -1)
            # DRAW RUNE TARGETING (If any monsters detected)
            if hasattr(self, 'best_rune_tile') and self.best_rune_tile:
                tr, tc = self.best_rune_tile
                # Draw the 7x7 mask area in faint Purple
                for mr in range(-3, 4):
                    for mc in range(-3, 4):
                        if BotConstants.RUNE_MASK[mr+3, mc+3] == 1:
                            rx = int((tc + mc) * tile_w_float)
                            ry = int((tr + mr) * tile_h_float)
                            rx2 = int((tc + mc + 1) * tile_w_float)
                            ry2 = int((tr + mr + 1) * tile_h_float)
                            # Draw a transparent-ish box
                            cv2.rectangle(overlay, (rx, ry), (rx2, ry2), (255, 0, 255), -1)
                
                # Draw a target cross on the center
                cx = int((tc + 0.5) * tile_w_float)
                cy = int((tr + 0.5) * tile_h_float)
                cv2.drawMarker(vis, (cx, cy), (255, 255, 255), cv2.MARKER_CROSS, 20, 2)
            # DEBUG TEXT
            cv2.putText(vis, f"ZOOM: {self.map_scale}x", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            cv2.addWeighted(overlay, 0.4, vis, 0.6, 0, vis)
            cv2.imshow("AI Spatial Vision", vis)
            cv2.waitKey(1)
        except Exception as e:
            print("Visualization error:", e)
            pass

if __name__ == "__main__":
    
    bot = Bot()
    bot.updateFrame()
    bot.updateAllElements()
    bot.updateActionbarSlotStatus()
    bot.getPartyList()
    def on_key_event(e):
        bot.key_pressed = e.name # Stores strings like 'f11', 'page up'

    kb.on_press(on_key_event)
    count = 0
    total_time = 0
    times = [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
    start_time = time.time()
    while(True): 
        # Check if GUI signaled exit
        if not bot.loop.get():
            break
            
        bot.GUI.loop()
        bot.updateFrame()
        bot.updateWindowCoordinates()
        bot.manageKeysSync()
        bot.checkAndDetectElements()
        bot.getBuffs()

        
        start = timeInMillis()
        start_loop = time.perf_counter()
        current_time = int(time.time() - start_time)



        #print(current_time % 10)
        if current_time % 10 == 0:
            bot.updateActionbarSlotStatus()
            #print("looting")
            if bot.loot_on_spot.get():
                bot.lootAround(True)


        # 1. Periodic Scale Detection (Every ~2 seconds)
        if count % 50 == 0:
            map_img = img.screengrab_array(bot.hwnd, bot.s_Map.region)
            bot.map_scale = bot.detect_minimap_scale(map_img)

        # 2. Update Basic States (Monsters, Buffs, etc)
        bot.monster_count = bot.monsterCount() 
        if bot.monster_count > 0:
            bot.updateMonsterPositions()
            bot.monster_positions = bot.get_filtered_monsters()

        # 3. GENERATE COLLISION GRID (Calculated once per frame)
        # This grid is now stored in bot.collision_grid and shared with all methods
        bot.collision_grid, _ = bot.get_local_collision_map()

        # 4. Logic methods can now simply read bot.collision_grid
        if bot.attack.get():
            bot.clickAttack()

        if bot.cavebot.get():
            # Method internal logic: Use self.collision_grid for A* or Kiting
            bot.cavebottest()



        if bot.hp_heal.get():
            bot.manageHealth()
            bot.manageMagicShield()
        if bot.mp_heal.get():
            bot.manageMana()

        bot.manageKnightSupport()

       # Combat chain
        if bot.attack_spells.get():
            did_aoe = bot.attackAreaSpells()
            did_rune = False
            if not did_aoe and bot.use_area_rune.get():
                did_rune = bot.useAreaRune()
            if not did_aoe and not did_rune:
                bot.attackTargetSpells()


        if bot._bool_value(bot.use_haste):
            bot.haste()
        if bot._bool_value(bot.use_food):
            bot.eat()
        if bot.manage_equipment.get():
            bot.manageEquipment()
        #if bot.follow_party.get():
        if bot.character_name != bot.party_leader.get():
            bot.manageFollow()
            if count%300 == 0:
                #print("updating party list")
                bot.getPartyList()

        if bot.use_area_rune.get() and bot.vocation != "knight":
            #if bot.monsterCount() > 0:
            if bot.vocation == "paladin":
                bot.useAreaAmmo()
            else:
                bot.useAreaRune()
        if len(bot.party.keys()) > 0:
            bot.healParty()

        # 5. Visualization (Throttled for performance)
        if count % 3 == 0:
            bot.visualize_monster_grid(bot.collision_grid, bot.map_scale)

        
        count+=1

