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

# LOCAL
from src.config import data
from src.vision import image as img
from src.vision import detect_monsters as dm
from src.config import config_manager as cm
from src.config.constants import BotConstants
from src.vision.screen_elements import *
from src.actions.window_interaction import *
from src.utils.extras import *
from src.ui.choose_client_gui import choose_capture_window
from src.ui.main_GUI import *
from tkinter import BooleanVar,StringVar,IntVar,PhotoImage
from functools import partial
from src.vision.bg_capture import BackgroundFrameGrabber

# endregion

class Bot:
    
    def __init__(self):
        # 1. System & Character Setup
        self._setup_system()
        
        # 2. Config & Profile Loading
        self.config = cm.ConfigManager()
        char_info = self.config.get_character_info(self.character_name)
        self.areaspell_area = char_info["spell_area"]
        if (self.vocation or "").lower() == "knight" and self.areaspell_area != 3:
            print(f"[CONFIG] Knight spell_area override: {self.areaspell_area} -> 3")
            self.areaspell_area = 3
        self.profile = self.config.get_config(self.server_id, self.character_name, self.vocation)
        
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
        # boss room
        self.hallway_images = []      # List of (image, coordinate)
        self.is_auto_walking = False  # Toggle state
        self.last_tp_pos = None       # To avoid clicking the same one twice
        self.active_sequence = None   # Puede ser "enter" o "exit"
        self.sequence_complete = False

    def _setup_system(self):
        self.base_directory = os.getcwd()
        self.hwnd, self.server_id, self.character_name, self.vocation = choose_capture_window()
        # PrintWindow is expensive; cap capture rate to reduce frame-stall pressure.
        self.bg = BackgroundFrameGrabber(self.hwnd, max_fps=25)
        self.bg.start()
        self._lock_window_resizing()
        
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

    def _lock_window_resizing(self):
        """Disable manual resizing while allowing window movement."""
        try:
            style = win32gui.GetWindowLong(self.hwnd, win32con.GWL_STYLE)
            new_style = style & ~win32con.WS_THICKFRAME & ~win32con.WS_MAXIMIZEBOX
            if new_style != style:
                win32gui.SetWindowLong(self.hwnd, win32con.GWL_STYLE, new_style)
                win32gui.SetWindowPos(
                    self.hwnd,
                    0,
                    0,
                    0,
                    0,
                    0,
                    win32con.SWP_NOMOVE
                    | win32con.SWP_NOSIZE
                    | win32con.SWP_NOZORDER
                    | win32con.SWP_NOACTIVATE
                    | win32con.SWP_FRAMECHANGED,
                )
                print("[WINDOW] Resize handles disabled (move allowed).")
        except Exception as e:
            print(f"[WINDOW] Could not lock resize: {e}")

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
        self.monster_count_battlelist = 0
        self.monster_count_screen = 0
        self.monster_count_reachable = 0
        self.monster_count_unreachable = 0
        self.monster_count_effective = 0
        self.party, self.party_positions = {}, []
        self.monster_positions = []
        self.monster_positions_reachable = []
        self.monster_positions_unreachable = []
        self.last_monster_detection_debug_image = None
        self.monsters_around = 0
        self.buffs = {}
        self.last_attack_time = timeInMillis()
        self.last_attack_click_ms = 0
        self.attack_recheck_delay_ms = 100
        self.attack_acquire_grace_until_ms = 0
        self.last_force_attack_request_ms = 0
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
        # Default cavebot cycle (shared by F11/F12 painter + cave navigation).
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
        self.lure_trip_active = False # Indica si el EK está en el recorrido de lure

        # Tiempos configurables (ms)
        self.lure_walk_duration = 0.6  # Segundos caminando
        self.lure_stop_duration = 0.4  # Segundos parado

        self.last_map_center_img = None
        self.kiting_stuck_count = 0
        self.kite_rotation_offset = 0
        self.kiting_mode = StringVar(value="forward")
        self.last_reached_mark_rel = None
        self.collision_grid = None
        self.raw_collision_grid = None
        self.map_scale = 2  # Baseline
        self.last_scale_check = 0
        # Pick 10 random offsets within a 20px radius of map center for tracking
        self.stuck_check_coords = [(np.random.randint(-20, 20), np.random.randint(-20, 20)) for _ in range(10)]
        self.last_stuck_colors = []
        self.stuck_counter = 0
        self.best_rune_tile = None
        self.key_debounce = False
        self.enable_boss_sequences = False
        self.last_walk_click_pos = None
        self.last_walk_click_ms = 0
        self.last_auto_sell_stone_ms = 0
        self.equip_state_initialized = False
        self.equip_combat_state = False
        self.equip_state_since_ms = 0
        self.equip_last_click_by_slot = {}
        self.next_mark_eligible_ms = 0
        self.only_visited_last_mark = None
        self.only_visited_streak = 0
        self.only_visited_confirm_scans = 3
        # Cavebot progression tuning (from offline replay harness).
        self.cavebot_arrival_threshold_px = 4.0
        self.cavebot_arrival_confirm_frames = 2
        self.cavebot_immediate_advance_px = 1.0
        self.cavebot_arrival_streak = 0
        self.cavebot_arrival_last_mark = None
        self.last_cavebot_reset_ms = 0
        self.last_mark_scan_log_ms = 0
        self.last_mark_scan_info = {}
        self.cavebot_recording = False
        self.cavebot_record_session_dir = None
        self.cavebot_record_trace_fp = None
        self.cavebot_record_frame_idx = 0
        self.cavebot_record_last_ms = 0
        self.cavebot_record_interval_default_ms = 120
        self.cavebot_record_zoom_label_default = 0
        self.cavebot_record_pending_mark = None
        self.cavebot_record_pending_rows = []
        self.cavebot_record_last_map_small = None
        self.minimap_zoom_recording = False
        self.minimap_zoom_session_dir = None
        self.minimap_zoom_target_scales = [1, 2, 4]
        self.minimap_zoom_captured = {}
        self.minimap_zoom_captured_order = []
        self.minimap_zoom_last_capture_ms = 0
        self.minimap_zoom_stable_scale = None
        self.minimap_zoom_stable_frames = 0
        self.minimap_zoom_required_stable_frames = 3
        self.minimap_zoom_true_tiles = {"unwalkable": [], "tp": []}
        self.minimap_zoom_sync_group = None
        self.minimap_tile_memory = np.full((11, 15), -1, dtype=np.int8)  # -1 unknown, 0 walkable, 1 blocked
        self.minimap_yellow_memory = np.full((11, 15), -1, dtype=np.int8)  # -1 unknown, 0 not yellow, 1 yellow
        self.minimap_memory_prev_map = None
        self.minimap_memory_prev_scale = 0
        self.minimap_memory_last_ms = 0.0
        self.minimap_memory_occluded_count = 0
        self.minimap_memory_recovered_count = 0
        self.minimap_memory_recovered_yellow_count = 0
        self.minimap_memory_shift_rc = (0, 0)
        self.last_minimap_memory_log_ms = 0
        self.visualize_pause_until_ms = 0
        self.visualize_window_alive = False
        self.last_battlelist_log_ms = 0
        self.battlelist_visualize_window_alive = False
        self.battlelist_debug_last_scan = {}
        self.amp_res_stagnation_start_ms = 0
        self.amp_res_prev_far_avg_dist = None
        self.amp_res_prev_update_ms = 0
        self.amp_res_last_far_count = 0
        self.amp_res_rearmed = True
        self.amp_res_far_anchor = None
        self.amp_res_far_anchor_start_ms = 0
        self.amp_res_debug = {}
        self._sync_mark_cycle(force_reset=True)
    def _init_timers(self):
        self.normal_delay = getNormalDelay()
        self.delays = DelayManager(default_jitter_ms_fn=getNormalDelay)
        
        # Internal Values
        self.safe_mp_thresh = self.mp_thresh.get() + 15
        self.follow_retry_delay = 2.5
        
        # Defaults
        self.delays.set_default("attack_click", 120)
        self.delays.set_default("area_rune", 1100, jitter_ms_fn=getNormalDelay)
        self.delays.set_default("equip_cycle", 180)
        self.delays.set_default("lure_stop", 250)
        self.delays.set_default("follow_retry", int(self.follow_retry_delay * 1000))
        self.delays.set_default("exeta_res", 3000)
        self.delays.set_default("amp_res", 6000)
        self.delays.set_default("utito", 10000)
        self.delays.set_default("haste_try", 900)
        self.delays.set_default("heal_low_try", 350)
        self.delays.set_default("heal_high_try", 450)
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
        self.use_static_lure = BooleanVar(value=s.get("use_static_lure", False))
        self.use_auto_sell_stone = BooleanVar(value=s.get("use_auto_sell_stone", False))
        self.auto_sell_stone_interval_s = IntVar(value=int(s.get("auto_sell_stone_interval_s", 60)))
        self.use_recenter = BooleanVar(value=s.get("use_recenter", False))
        self.use_kiting   = BooleanVar(value=s.get("use_kiting", False))
        self.log_cavebot      = BooleanVar(value=s.get("log_cavebot", False))
        self.log_battlelist   = BooleanVar(value=s.get("log_battlelist", False))
        self.visualize_battlelist = BooleanVar(value=s.get("visualize_battlelist", False))
        self.cavebot_record_interval_ms = IntVar(value=int(s.get("cavebot_record_interval_ms", 120)))
        self.cavebot_record_zoom_label = IntVar(value=int(s.get("cavebot_record_zoom_label", 0)))
        self.auto_zoom_capture_unwalkable = BooleanVar(value=s.get("auto_zoom_capture_unwalkable", True))
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
        self.use_magic_shield = BooleanVar(value=s.get("use_magic_shield", False))
        self.log_enabled      = BooleanVar(value=s.get("log_enabled", True))
        self.log_actions      = BooleanVar(value=s.get("log_actions", False))
        self.log_perf         = BooleanVar(value=s.get("log_perf", False))
        self.unwalkable_sync_gold = BooleanVar(value=s.get("unwalkable_sync_gold", False))

        self.hp_thresh_high        = IntVar(value=int(s.get("hp_thresh_high", 90)))
        self.hp_thresh_low         = IntVar(value=int(s.get("hp_thresh_low", 70)))
        self.mp_thresh             = IntVar(value=int(s.get("mp_thresh", 30)))
        self.min_monsters_around_spell = IntVar(value=int(s.get("min_monsters_spell", 1)))
        self.min_monsters_for_rune = IntVar(value=int(s.get("min_monsters_rune", 1)))
        self.kill_amount           = IntVar(value=int(s.get("kill_amount", 5)))
        self.kill_stop_amount      = IntVar(value=int(s.get("kill_stop_amount", 1)))

        self.party_leader    = StringVar(value=str(s.get("party_leader", "")))
        self.waypoint_folder = StringVar(value=str(s.get("waypoint_folder", "test")))
        self._sync_action_log_config()
        for v in (self.log_enabled, self.log_actions):
            try:
                v.trace_add("write", lambda *a: self._sync_action_log_config())
            except Exception:
                pass

    def _bool_value(self, v):
        try:
            return bool(v.get())
        except Exception:
            return bool(v)

    def _is_log_enabled(self, section=None):
        if not self._bool_value(getattr(self, "log_enabled", True)):
            return False
        if section == "action":
            return self._bool_value(getattr(self, "log_actions", False))
        if section == "perf":
            return self._bool_value(getattr(self, "log_perf", False))
        if section == "cavebot":
            return self._bool_value(getattr(self, "log_cavebot", False))
        if section == "battlelist":
            return self._bool_value(getattr(self, "log_battlelist", False))
        return True

    def _sync_action_log_config(self):
        enabled = self._is_log_enabled("action")
        configure_action_logging(enabled=enabled, include_caller=True)

    def _desired_mark_cycle(self):
        return ["skull", "lock", "cross", "star"]

    def _sync_mark_cycle(self, force_reset=False):
        desired = self._desired_mark_cycle()
        if force_reset or self.mark_list != desired:
            prev_mark = getattr(self, "current_mark", desired[0])
            self.mark_list = desired
            if force_reset or prev_mark not in self.mark_list:
                self.current_mark_index = 0
                self.current_mark = self.mark_list[0]
            else:
                self.current_mark_index = self.mark_list.index(prev_mark)
                self.current_mark = prev_mark

    def _cavebot_log(self, msg, throttle_ms=0):
        if not self._is_log_enabled("cavebot"):
            return
        if throttle_ms > 0:
            now_ms = timeInMillis()
            if (now_ms - self.last_mark_scan_log_ms) < throttle_ms:
                return
            self.last_mark_scan_log_ms = now_ms
        print(f"[CAVEBOT DEBUG] {msg}")

    def _battlelist_log(self, msg, throttle_ms=0):
        if not self._is_log_enabled("battlelist"):
            return
        if throttle_ms > 0:
            now_ms = timeInMillis()
            if (now_ms - self.last_battlelist_log_ms) < throttle_ms:
                return
            self.last_battlelist_log_ms = now_ms
        print(f"[BATTLELIST DEBUG] {msg}")

    def _ensure_cavebot_recording_dir(self, session_name=None):
        if not session_name:
            session_name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.join(self.base_directory, "training_data", "cavebot_sessions", session_name)
        frames = os.path.join(base, "frames")
        os.makedirs(frames, exist_ok=True)
        return base, frames

    def start_cavebot_recording(self, session_name=None):
        if self.cavebot_recording:
            return
        base, _ = self._ensure_cavebot_recording_dir(session_name=session_name)
        trace_path = os.path.join(base, "trace.jsonl")
        self.cavebot_record_trace_fp = open(trace_path, "a", encoding="utf-8")
        self.cavebot_record_session_dir = base
        self.cavebot_record_frame_idx = 0
        self.cavebot_record_last_ms = 0
        self.cavebot_record_pending_mark = None
        self.cavebot_record_pending_rows = []
        self.cavebot_record_last_map_small = None
        self.cavebot_recording = True
        zoom_lbl = int(self.cavebot_record_zoom_label.get()) if hasattr(self.cavebot_record_zoom_label, "get") else 0
        print(f"[CAVEBOT REC] recording started: {base} (zoom_label={zoom_lbl or 'auto'})")

    def stop_cavebot_recording(self):
        if not self.cavebot_recording:
            return
        self._flush_cavebot_record_segment(reason="stop")
        self.cavebot_recording = False
        if self.cavebot_record_trace_fp:
            try:
                self.cavebot_record_trace_fp.flush()
                self.cavebot_record_trace_fp.close()
            except Exception:
                pass
        self.cavebot_record_trace_fp = None
        print("[CAVEBOT REC] recording stopped")

    def toggle_cavebot_recording(self):
        if self.cavebot_recording:
            self.stop_cavebot_recording()
        else:
            self.start_cavebot_recording()

    def _record_cavebot_step(self, marks, event="tick", force=False):
        if not self.cavebot_recording:
            return
        now_ms = timeInMillis()
        interval_ms = int(self.cavebot_record_interval_ms.get()) if hasattr(self.cavebot_record_interval_ms, "get") else 120
        if not force and (now_ms - self.cavebot_record_last_ms) < max(40, interval_ms):
            return

        if not self.cavebot_record_session_dir:
            return
        frames_dir = os.path.join(self.cavebot_record_session_dir, "frames")
        map_img = img.screengrab_array(self.hwnd, self.s_Map.region)
        if map_img is None:
            return

        # Save only when minimap changed (unless forced snapshot/start marker).
        small = cv2.resize(map_img, (48, 48), interpolation=cv2.INTER_AREA)
        map_delta = None
        move_dx = 0.0
        move_dy = 0.0
        moved_px = 0.0
        move_confidence = 0.0
        move_method = "none"
        if self.cavebot_record_last_map_small is not None:
            map_delta = float(np.mean(cv2.absdiff(small, self.cavebot_record_last_map_small)))
            if not force and map_delta < 0.8:
                return
            try:
                move_dx, move_dy, move_confidence, move_method, motion_valid, motion_reason = self._estimate_minimap_motion(
                    self.cavebot_record_last_map_small,
                    small,
                    map_delta=map_delta,
                )
                moved_px = float((move_dx * move_dx + move_dy * move_dy) ** 0.5)
            except Exception:
                motion_valid = False
                motion_reason = "error"
        else:
            motion_valid = False
            motion_reason = "first_frame"

        self.cavebot_record_frame_idx += 1
        self.cavebot_record_last_ms = now_ms
        self.cavebot_record_last_map_small = small
        fname = f"frame_{self.cavebot_record_frame_idx:06d}.png"
        fpath = os.path.join(frames_dir, fname)
        try:
            cv2.imwrite(fpath, map_img)
        except Exception:
            return

        nearest_dist = None
        nearest_rel = None
        if marks:
            nearest_dist = float(marks[0][0])
            nearest_rel = [int(marks[0][2][0]), int(marks[0][2][1])]

        zoom_label = 0
        if hasattr(self.cavebot_record_zoom_label, "get"):
            try:
                zoom_label = int(self.cavebot_record_zoom_label.get())
            except Exception:
                zoom_label = 0
        if zoom_label in (1, 2, 4):
            zoom_label_source = "manual"
            zoom_label_value = zoom_label
        else:
            zoom_label_source = "auto"
            zoom_label_value = int(getattr(self, "map_scale", 2))

        rec = {
            "ts_ms": int(now_ms),
            "event": event,
            "frame": fname,
            "current_mark": self.current_mark,
            "current_mark_index": int(self.current_mark_index),
            "mark_list": list(self.mark_list),
            "monster_count": int(getattr(self, "monster_count", 0)),
            "kill_mode": bool(self.kill),
            "scan": dict(getattr(self, "last_mark_scan_info", {})),
            "nearest_dist": nearest_dist,
            "nearest_rel": nearest_rel,
            "map_scale": int(getattr(self, "map_scale", 2)),
            "zoom_label": int(zoom_label_value),
            "zoom_label_source": zoom_label_source,
            "map_delta": map_delta,
            "move_dx": move_dx,
            "move_dy": move_dy,
            "moved_px": moved_px,
            "move_confidence": move_confidence,
            "move_method": move_method,
            "motion_valid": bool(motion_valid),
            "motion_reason": motion_reason,
        }
        if self.cavebot_record_pending_mark is None:
            self.cavebot_record_pending_mark = self.current_mark
        if self.current_mark != self.cavebot_record_pending_mark:
            self._flush_cavebot_record_segment(reason="mark_change", next_mark=self.current_mark)
            self.cavebot_record_pending_mark = self.current_mark
        self.cavebot_record_pending_rows.append(rec)

    def _estimate_minimap_motion(self, prev_bgr, curr_bgr, max_shift=8, map_delta=None):
        """
        Estimate minimap movement between frames.
        Primary: center template matching (very accurate in offline benchmarks).
        Fallback: phase correlation if template confidence is weak/out-of-range.
        Returns (dx, dy, confidence, method, valid, reason).
        """
        # Light discontinuity guard for floor-jump/teleport-style minimap changes.
        likely_discontinuity = bool(map_delta is not None and float(map_delta) >= 30.0)
        try:
            prev_g = cv2.cvtColor(prev_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
            curr_g = cv2.cvtColor(curr_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
            h, w = prev_g.shape[:2]
            m = int(max(2, min(max_shift, h // 4, w // 4)))
            templ = prev_g[m : h - m, m : w - m]
            if templ.size > 0:
                res = cv2.matchTemplate(curr_g, templ, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                dx = float(max_loc[0] - m)
                dy = float(max_loc[1] - m)
                # Keep template result only when it is plausible and confident.
                if abs(dx) <= (max_shift + 1) and abs(dy) <= (max_shift + 1):
                    conf = float(max_val)
                    # Keep pure template as default; only invalidate obvious jump frames.
                    if likely_discontinuity and conf < 0.65:
                        return 0.0, 0.0, conf, "template_center", False, "discontinuity_low_template_conf"
                    if conf >= 0.55:
                        return dx, dy, conf, "template_center", True, "template_ok"
        except Exception:
            pass

        # Fallback path (rare): only if template fails outside discontinuity handling.
        try:
            prev_g = cv2.cvtColor(prev_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
            curr_g = cv2.cvtColor(curr_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
            shift, response = cv2.phaseCorrelate(prev_g, curr_g)
            dx = float(shift[0])
            dy = float(shift[1])
            conf = float(response)
            if likely_discontinuity:
                return 0.0, 0.0, conf, "phase_gray", False, "discontinuity_template_failed"
            if abs(dx) > (max_shift * 1.8) or abs(dy) > (max_shift * 1.8):
                return 0.0, 0.0, conf, "phase_gray", False, "shift_out_of_range"
            return dx, dy, conf, "phase_gray", True, "phase_ok"
        except Exception:
            return 0.0, 0.0, 0.0, "none", False, "estimate_failed"

    def _flush_cavebot_record_segment(self, reason="flush", next_mark=None):
        if not self.cavebot_record_trace_fp or not self.cavebot_record_pending_rows:
            self.cavebot_record_pending_rows = []
            self.cavebot_record_pending_mark = None
            return

        rows = self.cavebot_record_pending_rows
        goal_mark = self.cavebot_record_pending_mark
        rels = [r["nearest_rel"] for r in rows if r.get("nearest_rel") is not None]
        goal_rel = None
        if rels:
            xs = sorted([int(v[0]) for v in rels])
            ys = sorted([int(v[1]) for v in rels])
            goal_rel = [xs[len(xs)//2], ys[len(ys)//2]]

        seg_size = len(rows)
        for idx, r in enumerate(rows):
            out = dict(r)
            out["goal_mark"] = goal_mark
            out["goal_rel"] = goal_rel
            out["segment_size"] = seg_size
            out["segment_idx"] = idx
            out["segment_end_reason"] = reason
            out["next_mark_after_segment"] = next_mark
            self.cavebot_record_trace_fp.write(json.dumps(out, ensure_ascii=True) + "\n")
        self.cavebot_record_trace_fp.flush()
        self.cavebot_record_pending_rows = []
        self.cavebot_record_pending_mark = None

    def set_debug_goal_mark(self, mark):
        mark = str(mark).lower().strip()
        if mark not in self.mark_list:
            print(f"[CAVEBOT REC] invalid goal mark: {mark}")
            return
        self.current_mark = mark
        self.current_mark_index = self.mark_list.index(mark)
        print(f"[CAVEBOT REC] goal mark set to: {self.current_mark}")

    def record_cavebot_snapshot_now(self):
        marks = self.getClosestMarks()
        if not self.cavebot_recording:
            # one-shot session
            self.start_cavebot_recording()
            self._record_cavebot_step(marks, event="snapshot", force=True)
            self.stop_cavebot_recording()
        else:
            self._record_cavebot_step(marks, event="snapshot", force=True)

    def record_cavebot_tick(self):
        if not self.cavebot_recording:
            return
        marks = self.getClosestMarks()
        self._record_cavebot_step(marks, event="tick", force=False)

    def is_cavebot_recording(self):
        return bool(self.cavebot_recording)

    def _ensure_minimap_zoom_recording_dir(self, session_name=None):
        if not session_name:
            session_name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.join(self.base_directory, "training_data", "minimap_zoom_sets", session_name)
        os.makedirs(base, exist_ok=True)
        return base

    def _ensure_minimap_zoom_samples_dir(self):
        base = os.path.join(self.base_directory, "training_data", "minimap_zoom_samples")
        os.makedirs(base, exist_ok=True)
        return base

    def start_minimap_zoom_recording(self, session_name=None):
        if self.minimap_zoom_recording:
            return
        if not session_name:
            session_name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = self._ensure_minimap_zoom_recording_dir(session_name=session_name)
        self.minimap_zoom_session_dir = base
        self.minimap_zoom_captured = {}
        self.minimap_zoom_captured_order = []
        self.minimap_zoom_last_capture_ms = 0
        self.minimap_zoom_stable_scale = None
        self.minimap_zoom_stable_frames = 0
        self.minimap_zoom_true_tiles = {"unwalkable": [], "tp": []}
        self.minimap_zoom_sync_group = str(session_name)
        self.minimap_zoom_recording = True
        targets = ",".join(str(v) for v in self.minimap_zoom_target_scales)
        auto_unw = bool(self._bool_value(getattr(self, "auto_zoom_capture_unwalkable", True)))
        print(f"[ZOOM CAPTURE] started: {base} (targets={targets}, save_unw={auto_unw})")

    def stop_minimap_zoom_recording(self, reason="manual_stop"):
        if not self.minimap_zoom_recording:
            return
        self.minimap_zoom_recording = False
        base = self.minimap_zoom_session_dir
        if base:
            scales_out = {}
            for s, info in sorted(self.minimap_zoom_captured.items()):
                scales_out[str(int(s))] = {
                    "frame": info.get("frame"),
                    "ts_ms": int(info.get("ts_ms", 0)),
                    "anchor_dx": int(info.get("anchor_dx", 0)),
                    "anchor_dy": int(info.get("anchor_dy", 0)),
                    "unwalkable": info.get("unwalkable", []),
                    "tp": info.get("tp", []),
                }
            meta = {
                "session_type": "minimap_zoom_set",
                "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "reason": str(reason),
                "target_scales": list(self.minimap_zoom_target_scales),
                "captured_order": [int(v) for v in self.minimap_zoom_captured_order],
                "x4_truth": dict(self.minimap_zoom_true_tiles),
                "save_unwalkable_samples": bool(self._bool_value(getattr(self, "auto_zoom_capture_unwalkable", True))),
                "sync_group": self.minimap_zoom_sync_group,
                "scales": scales_out,
            }
            try:
                meta_path = os.path.join(base, "metadata.json")
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=True, indent=2)
            except Exception as e:
                print(f"[ZOOM CAPTURE] metadata write failed: {e}")
        captured = sorted(self.minimap_zoom_captured.keys())
        print(f"[ZOOM CAPTURE] stopped: reason={reason} captured={captured}")
        self.minimap_zoom_sync_group = None

    def toggle_minimap_zoom_recording(self):
        if self.minimap_zoom_recording:
            self.stop_minimap_zoom_recording(reason="manual_stop")
        else:
            self.start_minimap_zoom_recording()

    def is_minimap_zoom_recording(self):
        return bool(self.minimap_zoom_recording)

    def capture_minimap_zoom_sample(self, manual_zoom=None, note=""):
        """
        Save one minimap frame + manual zoom label for zoom-detector evaluation.
        Output:
          training_data/minimap_zoom_samples/<timestamp>_minimap.png
          training_data/minimap_zoom_samples/<timestamp>.json
        """
        map_img = img.screengrab_array(self.hwnd, self.s_Map.region)
        if map_img is None:
            print("[ZOOM SAMPLE] Failed to capture minimap image.")
            return

        out_dir = self._ensure_minimap_zoom_samples_dir()
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        img_name = f"{ts}_minimap.png"
        json_name = f"{ts}.json"
        img_path = os.path.join(out_dir, img_name)
        json_path = os.path.join(out_dir, json_name)

        if manual_zoom is None:
            try:
                manual_zoom = int(self.cavebot_record_zoom_label.get())
            except Exception:
                manual_zoom = 0
        manual_zoom = int(manual_zoom)
        if manual_zoom not in (0, 1, 2, 4):
            manual_zoom = 0

        try:
            detected_zoom = int(self.detect_minimap_scale(map_img))
            detect_source = "detect_minimap_scale"
        except Exception:
            detected_zoom = int(max(1, getattr(self, "map_scale", 2)))
            detect_source = "runtime_fallback"
        detected_zoom = int(max(1, detected_zoom))

        # Diagnostics for known failure mode: mostly-black minimap.
        px = map_img.astype(np.uint8)
        black_mask = np.all(px <= np.array([8, 8, 8], dtype=np.uint8), axis=-1)
        black_ratio = float(np.mean(black_mask)) if black_mask.size else 0.0

        if not hasattr(self, "_terrain_codes_u32"):
            terrain = np.array(BotConstants.OBSTACLES + BotConstants.WALKABLE, dtype=np.uint8)
            self._terrain_codes_u32 = (
                (terrain[:, 0].astype(np.uint32) << 16)
                | (terrain[:, 1].astype(np.uint32) << 8)
                | terrain[:, 2].astype(np.uint32)
            )
        codes = (
            (px[:, :, 0].astype(np.uint32) << 16)
            | (px[:, :, 1].astype(np.uint32) << 8)
            | px[:, :, 2].astype(np.uint32)
        )
        terrain_ratio = float(np.mean(np.isin(codes, self._terrain_codes_u32, assume_unique=False))) if codes.size else 0.0

        ok = (manual_zoom == 0) or (manual_zoom == detected_zoom)
        cv2.imwrite(img_path, map_img)

        meta = {
            "session_type": "minimap_zoom_sample",
            "timestamp": ts,
            "image_file": img_name,
            "manual_zoom_level": int(manual_zoom),
            "detected_zoom_level": int(detected_zoom),
            "detector_source": detect_source,
            "detected_matches_manual": bool(ok),
            "black_ratio": float(black_ratio),
            "terrain_ratio": float(terrain_ratio),
            "map_region": [int(v) for v in self.s_Map.region],
            "map_scale_runtime": int(max(1, getattr(self, "map_scale", detected_zoom))),
            "note": str(note or ""),
            "sync_gold": bool(self._bool_value(getattr(self, "unwalkable_sync_gold", False))),
            "quality_tag": "sync_gold" if bool(self._bool_value(getattr(self, "unwalkable_sync_gold", False))) else "regular",
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=True)

        status = "OK" if ok else "MISMATCH"
        print(
            f"[ZOOM SAMPLE] Saved {json_name} "
            f"(manual={manual_zoom} detected={detected_zoom} {status} "
            f"black={black_ratio:.3f} terrain={terrain_ratio:.3f})"
        )

    def record_minimap_zoom_tick(self):
        if not self.minimap_zoom_recording:
            return
        now_ms = timeInMillis()
        scale = int(max(1, getattr(self, "map_scale", 2)))
        if scale == int(self.minimap_zoom_stable_scale or -1):
            self.minimap_zoom_stable_frames += 1
        else:
            self.minimap_zoom_stable_scale = scale
            self.minimap_zoom_stable_frames = 1

        if scale not in self.minimap_zoom_target_scales:
            return
        if scale in self.minimap_zoom_captured:
            if all(s in self.minimap_zoom_captured for s in self.minimap_zoom_target_scales):
                self.stop_minimap_zoom_recording(reason="all_scales_captured")
            return
        if self.minimap_zoom_stable_frames < int(max(1, self.minimap_zoom_required_stable_frames)):
            return
        if (now_ms - self.minimap_zoom_last_capture_ms) < 220:
            return

        map_img = img.screengrab_array(self.hwnd, self.s_Map.region)
        if map_img is None:
            return
        game_img = img.screengrab_array(self.hwnd, self.s_GameScreen.region)
        if game_img is None:
            return
        if not self.minimap_zoom_session_dir:
            return

        frame_name = f"zoom_x{scale}.png"
        frame_path = os.path.join(self.minimap_zoom_session_dir, frame_name)
        try:
            cv2.imwrite(frame_path, map_img)
        except Exception:
            return

        tile_info = self._extract_tile_sets_from_map(map_img, scale)
        tile_info["frame"] = frame_name
        tile_info["ts_ms"] = int(now_ms)
        self.minimap_zoom_captured[int(scale)] = tile_info
        self.minimap_zoom_captured_order.append(int(scale))
        self.minimap_zoom_last_capture_ms = now_ms

        if int(scale) == 4:
            self.minimap_zoom_true_tiles = {
                "unwalkable": list(tile_info.get("unwalkable", [])),
                "tp": list(tile_info.get("tp", [])),
            }

        print(
            f"[ZOOM CAPTURE] saved x{scale} ({frame_name}) "
            f"stable_frames={self.minimap_zoom_stable_frames} "
            f"tiles: unwalkable={len(tile_info.get('unwalkable', []))} tp={len(tile_info.get('tp', []))}"
        )

        if bool(self._bool_value(getattr(self, "auto_zoom_capture_unwalkable", True))):
            self._save_unwalkable_sample_from_frames(
                game_img=game_img,
                map_img=map_img,
                scale=scale,
                scale_source="runtime_map_scale",
                capture_source="auto_zoom_capture",
                tile_info=tile_info,
                collision_unwalkable=[],
                collision_scale=scale,
                extra_meta={
                    "sync_group": self.minimap_zoom_sync_group,
                    "zoom_capture_session": os.path.basename(self.minimap_zoom_session_dir or ""),
                    "zoom_capture_order": int(len(self.minimap_zoom_captured_order)),
                },
            )

        if all(s in self.minimap_zoom_captured for s in self.minimap_zoom_target_scales):
            self.stop_minimap_zoom_recording(reason="all_scales_captured")

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
        # Non-blocking: consume latest frame produced by background capture thread.
        if self.bg.frame_bgr is not None:
            img.set_cached_frame(self.hwnd, self.bg.frame_bgr)
        else:
            # Startup fallback (first frame) in case thread has not produced one yet.
            ok = self.bg.update(force=True)
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
            # HighGUI can become unstable while dragging/resizing; pause debug draw briefly.
            self.visualize_pause_until_ms = timeInMillis() + 900
            if self.visualize_window_alive:
                try:
                    cv2.destroyWindow("AI Spatial Vision")
                except Exception:
                    pass
                self.visualize_window_alive = False
            if self.battlelist_visualize_window_alive:
                try:
                    cv2.destroyWindow("Battle List Debug")
                except Exception:
                    pass
                self.battlelist_visualize_window_alive = False
            self.bg._refresh_crop()
            self.updateAllElements()
            self.getPartyList()
        else:
            # 2. Internal Game View Resize (Use our new debounced check)
            if self.checkGameScreenMoved():
                print("Game view internal resize confirmed. Updating bound elements...")
                self.visualize_pause_until_ms = timeInMillis() + 900
                if self.visualize_window_alive:
                    try:
                        cv2.destroyWindow("AI Spatial Vision")
                    except Exception:
                        pass
                    self.visualize_window_alive = False
                if self.battlelist_visualize_window_alive:
                    try:
                        cv2.destroyWindow("Battle List Debug")
                    except Exception:
                        pass
                    self.battlelist_visualize_window_alive = False
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

    def clickActionbarSlot(self, pos, check_cooldown=True, source="", key="", equip_action=""):
        if pos is None:
            return False
        # 1. Defensive Cooldown Check
        if check_cooldown:
            # We use the optimized NumPy check we just wrote
            if not self.checkActionBarSlotCooldown(pos):
                return False

        # 2. Perform the click
        x, y = self.getActionbarSlotPosition(pos)
        # Click the center of the slot, not the top-left sample pixel.
        click_x = x + 17
        click_y = y + 17
        ctx_parts = [f"source={source or 'unknown'}", f"slot={pos}"]
        if key:
            ctx_parts.append(f"key={key}")
        if equip_action:
            ctx_parts.append(f"equip_action={equip_action}")
        click_client(self.hwnd, click_x, click_y, log_action=False, log_context=" ".join(ctx_parts))
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

    def _compute_walkable_reachability(self, grid):
        """
        BFS over local 15x11 grid from player tile.
        Uses 8-way movement with anti-corner-cutting on diagonals.
        """
        if grid is None:
            return None
        if grid.shape[0] != 11 or grid.shape[1] != 15:
            return None

        reachable = np.zeros((11, 15), dtype=bool)
        p_row, p_col = 5, 7

        def is_walkable(r, c):
            return 0 <= r < 11 and 0 <= c < 15 and int(grid[r, c]) != 1

        if not is_walkable(p_row, p_col):
            return reachable

        queue = deque([(p_row, p_col)])
        reachable[p_row, p_col] = True
        dirs = [
            (-1, 0), (1, 0), (0, -1), (0, 1),
            (-1, -1), (-1, 1), (1, -1), (1, 1),
        ]

        while queue:
            r, c = queue.popleft()
            for dr, dc in dirs:
                nr, nc = r + dr, c + dc
                if not is_walkable(nr, nc) or reachable[nr, nc]:
                    continue
                if dr != 0 and dc != 0:
                    # Prevent diagonal leak through corner walls.
                    if not (is_walkable(r + dr, c) and is_walkable(r, c + dc)):
                        continue
                reachable[nr, nc] = True
                queue.append((nr, nc))
        return reachable

    def update_monster_reachability(self):
        """
        Classifies on-screen monsters as reachable/unreachable using local collision map.
        """
        positions = list(getattr(self, "monster_positions", []) or [])
        if not positions:
            self.monster_positions_reachable = []
            self.monster_positions_unreachable = []
            self.monster_count_screen = 0
            self.monster_count_reachable = 0
            self.monster_count_unreachable = 0
            return

        tile_w = max(1, int(self.s_GameScreen.tile_w))
        tile_h = max(1, int(self.s_GameScreen.tile_h))
        base_grid = self.collision_grid if self.collision_grid is not None else self.raw_collision_grid
        reachable_mask = self._compute_walkable_reachability(base_grid)

        reachable_positions = []
        unreachable_positions = []
        for mx, my in positions:
            m_col = int(mx // tile_w)
            m_row = int(my // tile_h)
            if not (0 <= m_row < 11 and 0 <= m_col < 15):
                reachable_positions.append((mx, my))
                continue

            if reachable_mask is None:
                reachable_positions.append((mx, my))
                continue

            if reachable_mask[m_row, m_col]:
                reachable_positions.append((mx, my))
                continue

            # Grace path for noisy cells: if monster landed on a blocked sample,
            # still treat as reachable when any adjacent walkable tile is reachable.
            adj_reachable = False
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    rr = m_row + dr
                    cc = m_col + dc
                    if 0 <= rr < 11 and 0 <= cc < 15 and reachable_mask[rr, cc]:
                        adj_reachable = True
                        break
                if adj_reachable:
                    break

            if adj_reachable:
                reachable_positions.append((mx, my))
            else:
                unreachable_positions.append((mx, my))

        self.monster_positions_reachable = reachable_positions
        self.monster_positions_unreachable = unreachable_positions
        self.monster_count_screen = int(len(positions))
        self.monster_count_reachable = int(len(reachable_positions))
        self.monster_count_unreachable = int(len(unreachable_positions))

    def get_effective_monster_count_for_cavebot(self):
        """
        Cavebot count policy:
        - If we see monsters on screen, trust only reachable on-screen count.
        - If screen has none, fallback to battle list count.
        """
        screen_total = int(getattr(self, "monster_count_screen", len(getattr(self, "monster_positions", []) or [])))
        reachable = int(getattr(self, "monster_count_reachable", screen_total))
        battle = int(getattr(self, "monster_count_battlelist", 0))
        if screen_total > 0:
            return max(0, reachable)
        return max(0, battle, reachable)
    
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
        """
        Mantiene el Magic Shield activo si el mana es saludable (>50%)
        y no tenemos el buff actualmente.
        """
        # 1. Solo para Magos (y si está habilitado en la GUI)
        if self.vocation not in ["druid", "sorcerer"] or not self.use_magic_shield.get():
            return

        ms_slot = self.slots.get("magic_shield")
        if ms_slot is None:
            return

        # 2. Verificar estado actual (vía self.buffs poblado por getBuffs)
        has_magic_shield = self.buffs.get('magicshield', False)

        # 3. Lógica: Si NO tengo el escudo Y el mana es > 50%
        if not has_magic_shield and self.mppc > 50:
            # Intentar castear (incluye check de cooldown interno)
            if self.checkActionBarSlotCooldown(ms_slot):
                if self.clickActionbarSlot(ms_slot):
                    print("[BUFF] Magic Shield reactivado (Mana > 50%)")
    
    def manageHealth(self):
        self.getHealth()
        self.hp_queue.pop()
        self.hp_queue.appendleft(self.hppc)
        burst = self.getBurstDamage()
        # Use SLOTS instead of Key Press
        if (self.hppc <= self.hp_thresh_low.get() or burst > 40):
            # Check if slot exists in config
            if "heal_low" in self.slots: 
                # Aggressive retry cadence for emergency heals.
                # We intentionally bypass slot-text cooldown detection here.
                if self.delays.allow("heal_low_try"):
                    self.clickActionbarSlot(self.slots["heal_low"], check_cooldown=False)
                
        elif self.hppc < self.hp_thresh_high.get():
            if "heal_high" in self.slots:
                # Slightly slower than low-heal, still faster/more responsive.
                if self.delays.allow("heal_high_try"):
                    self.clickActionbarSlot(self.slots["heal_high"], check_cooldown=False)
            
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

    def castAmpRes(self, allow_rearm=False):
        if not self.delays.due("amp_res"):
            if not allow_rearm:
                return
            last_amp_ms = self.delays.last_ms("amp_res", default=0) or 0
            # Early recast path only when explicitly allowed by smarter logic.
            if (timeInMillis() - last_amp_ms) < 2500:
                return
        slot = self.slots.get("amp_res")
        if slot is not None:
            if self.clickActionbarSlot(slot):
                self.delays.trigger("amp_res")
                self.amp_res_rearmed = False

    def _count_free_melee_tiles(self):
        """
        Counts immediately adjacent walkable tiles around player on 15x11 local grid.
        """
        base_grid = self.raw_collision_grid if self.raw_collision_grid is not None else self.collision_grid
        if base_grid is None:
            return 0
        p_row, p_col = 5, 7

        # Mark tiles currently occupied by detected monsters.
        occupied = set()
        tile_w = self.s_GameScreen.tile_w
        tile_h = self.s_GameScreen.tile_h
        for mx, my in self.monster_positions:
            m_col = int(mx // tile_w)
            m_row = int(my // tile_h)
            if 0 <= m_row < 11 and 0 <= m_col < 15:
                occupied.add((m_row, m_col))

        free = 0
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                r = p_row + dy
                c = p_col + dx
                if (
                    0 <= r < 11
                    and 0 <= c < 15
                    and base_grid[r, c] == 0
                    and (r, c) not in occupied
                ):
                    free += 1
        return free

    def _should_cast_amp_res(self):
        """
        Smart Amp Res decision:
        - Need at least one distant monster (>=2 tiles).
        - Need at least one free adjacent tile around player.
        - A distant monster must stay roughly in the same place for ~1s.
        - Respect cooldown, with optional rearm path after far mobs clear/reappear.
        """
        now_ms = timeInMillis()

        if not self.monster_positions:
            self.amp_res_stagnation_start_ms = 0
            self.amp_res_prev_far_avg_dist = None
            self.amp_res_prev_update_ms = 0
            self.amp_res_last_far_count = 0
            self.amp_res_rearmed = True
            self.amp_res_far_anchor = None
            self.amp_res_far_anchor_start_ms = 0
            self.amp_res_debug = {"reason": "no_monsters"}
            return False

        tile = self.s_GameScreen.tile_h
        center = self.s_GameScreen.getRelativeCenter()

        # Ranged/away monsters: outside >=2.0 tiles from player center
        far_dist_threshold = tile * 2.0
        far_positions = []
        far_distances = []
        for mx, my in self.monster_positions:
            d = sqrt((mx - center[0]) ** 2 + (my - center[1]) ** 2)
            if d > far_dist_threshold:
                far_positions.append((mx, my))
                far_distances.append(d)

        far_count = len(far_distances)
        free_melee_tiles = self._count_free_melee_tiles()

        # If far monsters disappear, rearm early recast path.
        if far_count == 0:
            self.amp_res_rearmed = True
            self.amp_res_stagnation_start_ms = 0
            self.amp_res_prev_far_avg_dist = None
            self.amp_res_prev_update_ms = now_ms
            self.amp_res_last_far_count = 0
            self.amp_res_far_anchor = None
            self.amp_res_far_anchor_start_ms = 0
            self.amp_res_debug = {
                "reason": "no_far_monsters",
                "free_melee_tiles": free_melee_tiles,
            }
            return False

        # Need room around player so pulled monsters can stack in melee ring.
        if free_melee_tiles < 1:
            self.amp_res_stagnation_start_ms = 0
            self.amp_res_prev_far_avg_dist = float(np.mean(far_distances))
            self.amp_res_prev_update_ms = now_ms
            self.amp_res_last_far_count = far_count
            self.amp_res_far_anchor = None
            self.amp_res_far_anchor_start_ms = 0
            self.amp_res_debug = {
                "reason": "no_free_melee_tiles",
                "far_count": far_count,
                "free_melee_tiles": free_melee_tiles,
            }
            return False

        # Track one "anchor" far monster without identities:
        # If nearest far monster to previous anchor stays near same spot, accumulate stable time.
        anchor_match_radius = tile * 0.55
        anchor_stability_radius = tile * 0.28

        if self.amp_res_far_anchor is None:
            self.amp_res_far_anchor = far_positions[0]
            self.amp_res_far_anchor_start_ms = now_ms
        else:
            ax, ay = self.amp_res_far_anchor
            nearest = min(
                far_positions,
                key=lambda p: (p[0] - ax) ** 2 + (p[1] - ay) ** 2
            )
            nearest_dist = sqrt((nearest[0] - ax) ** 2 + (nearest[1] - ay) ** 2)

            if nearest_dist <= anchor_match_radius:
                # Same likely target still around. Update anchor gently.
                # If it drifted a lot, reset stability timer.
                if nearest_dist > anchor_stability_radius:
                    self.amp_res_far_anchor_start_ms = now_ms
                self.amp_res_far_anchor = nearest
            else:
                # Previous far target likely gone/replaced -> restart stability timer.
                self.amp_res_far_anchor = nearest
                self.amp_res_far_anchor_start_ms = now_ms

        stable_ms = max(0, now_ms - self.amp_res_far_anchor_start_ms)

        # Standard cooldown OR early-rearm path (only after far pack cleared once)
        last_amp_ms = self.delays.last_ms("amp_res", default=0) or 0
        since_last_amp_ms = now_ms - last_amp_ms if last_amp_ms else 10**9
        due_regular = self.delays.due("amp_res")
        due_rearm = self.amp_res_rearmed and since_last_amp_ms >= 2500

        should_cast = stable_ms >= 1000 and (due_regular or due_rearm)

        far_avg = float(np.mean(far_distances))
        self.amp_res_prev_far_avg_dist = far_avg
        self.amp_res_prev_update_ms = now_ms
        self.amp_res_last_far_count = far_count
        self.amp_res_debug = {
            "reason": "ready" if should_cast else "tracking",
            "far_count": far_count,
            "far_avg": int(far_avg),
            "free_melee_tiles": free_melee_tiles,
            "stagnant_ms": int(stable_ms),
            "due_regular": due_regular,
            "due_rearm": due_rearm,
        }

        return should_cast

    def haste(self):
        slot = self.slots.get("haste")
        if slot is not None and self.slot_status[slot]:
            if not self.buffs['haste'] and not self.buffs['pz']:
                if self.delays.due("haste_try"):
                    self.clickActionbarSlot(slot, source="haste")
                    self.delays.trigger("haste_try")
                
    def eat(self):
        slot = self.slots.get("food")
        if slot is not None and self.slot_status[slot]:
            if not self.buffs['pz'] and self.buffs['hungry']:
                # Skip cooldown check for food
                self.clickActionbarSlot(slot, check_cooldown=False)

    def autoUseSellStone(self):
        if not self._bool_value(getattr(self, "use_auto_sell_stone", False)):
            return
        if self.buffs.get("pz", False):
            return

        slot = self.slots.get("sell_stone")
        if slot is None:
            return
        try:
            interval_s = int(self.auto_sell_stone_interval_s.get())
        except Exception:
            interval_s = 60
        interval_ms = max(5, interval_s) * 1000

        now_ms = timeInMillis()
        if (now_ms - int(getattr(self, "last_auto_sell_stone_ms", 0))) < interval_ms:
            return

        clicks_sent = 0
        for i in range(4):
            if self.clickActionbarSlot(slot, check_cooldown=False, source="sell_stone"):
                clicks_sent += 1
            # Small spacing so the server/client can register repeated uses.
            if i < 3:
                time.sleep(0.05)
        if clicks_sent > 0:
            self.last_auto_sell_stone_ms = now_ms
    
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
        self._battlelist_log(
            f"monsterCount count={count} scan_x={x} first_y={first_pos} step={d} region={self.s_BattleList.region}",
            throttle_ms=500,
        )
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

        # Nothing to do if battle list is empty.
        # `self.monster_count` is refreshed in the main loop every frame.
        if getattr(self, "monster_count", 0) <= 0:
            return

        now_ms = timeInMillis()

        # After sending an attack click, always give the client a short fixed window
        # before re-checking attack state (prevents rapid oscillation on slower servers/themes).
        if now_ms < self.attack_acquire_grace_until_ms:
            return

        is_knight = ((self.vocation or "").lower() == "knight")
        attacked_row_idx = None
        attacked_rel_y = None
        if is_knight:
            attacked_row_idx, attacked_rel_y = self.get_attacked_battlelist_row()

        # Only check delay if we are NOT forcing the attack
        if not force:
            if not self.delays.due("attack_click"):
                return
            if self.isAttacking():
                # Knight policy: keep attacking only if current target is already first row.
                if is_knight:
                    if attacked_row_idx == 0:
                        return
                    # If attacked row is not first (or unknown), keep going and retarget.
                else:
                    return
        else:
            # Even forced reacquire should respect a tiny hard floor between clicks.
            if (now_ms - self.last_attack_click_ms) < 220:
                return
            # Also throttle force requests globally to avoid oscillation spam.
            if (now_ms - self.last_force_attack_request_ms) < 320:
                return

        # 2. Capture and Scan (Rest of your existing logic...)
        region = self.s_BattleList.region
        image = img.screengrab_array(self.hwnd, region)
        if image is None: return

        height, width, _ = image.shape
        # Keep these aligned with monsterCount() scanline constants.
        rel_x, start_y, step_y = 25, 31, 22
        debug_rows = []
        selected_rel_y = None

        for rel_y in range(start_y, height, step_y):
            if rel_y >= height or rel_x >= width:
                break
            p = image[rel_y, rel_x]
            debug_rows.append(
                {
                    "rel_y": int(rel_y),
                    "bgr": (int(p[0]), int(p[1]), int(p[2])),
                    "black": bool(p[0] == 0 and p[1] == 0 and p[2] == 0),
                }
            )

        # Knights should prioritize the first battle-list row (closest target).
        if (self.vocation or "").lower() == "knight":
            if start_y < height and rel_x < width:
                first_pixel = image[start_y, rel_x]
                if first_pixel[0] == 0 and first_pixel[1] == 0 and first_pixel[2] == 0:
                    abs_x, abs_y = region[0] + rel_x, region[1] + start_y
                    selected_rel_y = int(start_y)
                    self.battlelist_debug_last_scan = {
                        "region": tuple(region),
                        "rel_x": int(rel_x),
                        "attack_rel_x": 3,
                        "start_y": int(start_y),
                        "step_y": int(step_y),
                        "height": int(height),
                        "width": int(width),
                        "rows": debug_rows,
                        "attacked_row_idx": attacked_row_idx,
                        "attacked_rel_y": attacked_rel_y,
                        "selected_rel_y": selected_rel_y,
                        "source": "knight_first_row",
                        "force": bool(force),
                        "monster_count": int(getattr(self, "monster_count", 0)),
                    }
                    click_client(self.hwnd, abs_x, abs_y)
                    self.delays.trigger("attack_click")
                    self.last_attack_click_ms = now_ms
                    self.attack_acquire_grace_until_ms = now_ms + self.attack_recheck_delay_ms
                    if force:
                        self.last_force_attack_request_ms = now_ms
                    return

        for rel_y in range(start_y, height, step_y):
            if rel_y >= height or rel_x >= width: break
            pixel = image[rel_y, rel_x]

            if pixel[0] == 0 and pixel[1] == 0 and pixel[2] == 0:
                abs_x, abs_y = region[0] + rel_x, region[1] + rel_y
                selected_rel_y = int(rel_y)
                self.battlelist_debug_last_scan = {
                    "region": tuple(region),
                    "rel_x": int(rel_x),
                    "attack_rel_x": 3,
                    "start_y": int(start_y),
                    "step_y": int(step_y),
                    "height": int(height),
                    "width": int(width),
                    "rows": debug_rows,
                    "attacked_row_idx": attacked_row_idx,
                    "attacked_rel_y": attacked_rel_y,
                    "selected_rel_y": selected_rel_y,
                    "source": "first_black_row_scan",
                    "force": bool(force),
                    "monster_count": int(getattr(self, "monster_count", 0)),
                }
                click_client(self.hwnd, abs_x, abs_y)
                self.delays.trigger("attack_click")
                self.last_attack_click_ms = now_ms
                self.attack_acquire_grace_until_ms = now_ms + self.attack_recheck_delay_ms
                if force:
                    self.last_force_attack_request_ms = now_ms
                return
        # No valid row found; emit sampled row diagnostics.
        samples = []
        row_n = 0
        for rel_y in range(start_y, height, step_y):
            if rel_y >= height or rel_x >= width or row_n >= 8:
                break
            p = image[rel_y, rel_x]
            is_candidate = (p[0] == 0 and p[1] == 0 and p[2] == 0)
            samples.append(f"r{row_n}@y={rel_y}:bgr=({int(p[0])},{int(p[1])},{int(p[2])}) black={int(is_candidate)}")
            row_n += 1
        self._battlelist_log(
            f"clickAttack no target force={force} monster_count={getattr(self, 'monster_count', 0)} "
            f"region={region} samples={' | '.join(samples)}",
            throttle_ms=500,
        )
        self.battlelist_debug_last_scan = {
            "region": tuple(region),
            "rel_x": int(rel_x),
            "attack_rel_x": 3,
            "start_y": int(start_y),
            "step_y": int(step_y),
            "height": int(height),
            "width": int(width),
            "rows": debug_rows,
            "attacked_row_idx": attacked_row_idx,
            "attacked_rel_y": attacked_rel_y,
            "selected_rel_y": None,
            "source": "no_target",
            "force": bool(force),
            "monster_count": int(getattr(self, "monster_count", 0)),
        }

    def get_attacked_battlelist_row(self):
        """
        Returns (row_idx, rel_y) of current attacked target marker in battle list.
        Marker is the red/highlight-red strip on the left side.
        """
        region = self.s_BattleList.region
        image = img.screengrab_array(self.hwnd, region)
        if image is None:
            return None, None

        height, width = image.shape[:2]
        rel_x = 3
        start_y, step_y = 31, 22
        if rel_x >= width:
            return None, None

        for row_idx, rel_y in enumerate(range(start_y, height, step_y)):
            p = image[rel_y, rel_x]
            # BGR red marker variants.
            if (p[2] == 255) and (p[1] in (0, 128)):
                return int(row_idx), int(rel_y)
        return None, None

    def visualize_battlelist_debug(self):
        """
        Real-time debug view for battle-list target scan.
        Draws scan rows, sampled pixel colors, and selected click row.
        """
        try:
            if timeInMillis() < int(getattr(self, "visualize_pause_until_ms", 0)):
                return
            if not self._bool_value(getattr(self, "visualize_battlelist", False)):
                if self.battlelist_visualize_window_alive:
                    try:
                        cv2.destroyWindow("Battle List Debug")
                    except Exception:
                        pass
                    self.battlelist_visualize_window_alive = False
                return

            region = self.s_BattleList.region
            frame = img.screengrab_array(self.hwnd, region)
            if frame is None:
                return
            vis = np.ascontiguousarray(frame, dtype=np.uint8)

            dbg = dict(getattr(self, "battlelist_debug_last_scan", {}) or {})
            rel_x = int(dbg.get("rel_x", 25))
            attack_rel_x = int(dbg.get("attack_rel_x", 3))
            start_y = int(dbg.get("start_y", 31))
            step_y = int(dbg.get("step_y", 22))
            selected_rel_y = dbg.get("selected_rel_y", None)
            attacked_row_idx = dbg.get("attacked_row_idx", None)
            attacked_rel_y = dbg.get("attacked_rel_y", None)
            rows = dbg.get("rows", [])

            # Vertical scanline
            cv2.line(vis, (rel_x, 0), (rel_x, vis.shape[0] - 1), (255, 180, 0), 1)
            cv2.line(vis, (attack_rel_x, 0), (attack_rel_x, vis.shape[0] - 1), (180, 0, 255), 1)

            # Draw sampled rows; green=valid black target pixel, red=non-target.
            if rows:
                for i, row in enumerate(rows[:20]):
                    y = int(row.get("rel_y", start_y + i * step_y))
                    if y < 0 or y >= vis.shape[0]:
                        continue
                    b, g, r = row.get("bgr", (0, 0, 0))
                    is_black = bool(row.get("black", False))
                    color = (0, 255, 0) if is_black else (0, 0, 255)
                    rad = 4 if is_black else 3
                    cv2.circle(vis, (rel_x, y), rad, color, -1)
                    cv2.putText(
                        vis,
                        f"r{i} y={y} bgr=({b},{g},{r})",
                        (min(rel_x + 12, vis.shape[1] - 180), max(10, y - 2)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.35,
                        color,
                        1,
                    )
            else:
                for i, y in enumerate(range(start_y, vis.shape[0], step_y)):
                    color = (255, 255, 0) if i == 0 else (120, 120, 120)
                    cv2.circle(vis, (rel_x, y), 2, color, -1)

            # Highlight first row and selected row.
            if 0 <= start_y < vis.shape[0]:
                cv2.line(vis, (0, start_y), (vis.shape[1] - 1, start_y), (0, 255, 255), 1)
            if selected_rel_y is not None and 0 <= int(selected_rel_y) < vis.shape[0]:
                y = int(selected_rel_y)
                cv2.line(vis, (0, y), (vis.shape[1] - 1, y), (255, 255, 0), 2)
            if attacked_rel_y is not None and 0 <= int(attacked_rel_y) < vis.shape[0]:
                y = int(attacked_rel_y)
                cv2.circle(vis, (attack_rel_x, y), 5, (255, 0, 255), -1)
                cv2.line(vis, (0, y), (vis.shape[1] - 1, y), (255, 0, 255), 1)

            source = str(dbg.get("source", "n/a"))
            mc = int(dbg.get("monster_count", getattr(self, "monster_count", 0)))
            atk = int(bool(self.isAttacking()))
            voc = (self.vocation or "").lower()
            cv2.putText(vis, f"voc={voc} monsters={mc} attacking={atk}", (5, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)
            cv2.putText(vis, f"scan x={rel_x} y0={start_y} step={step_y} src={source}", (5, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 255, 180), 1)
            cv2.putText(
                vis,
                f"attacked_row={attacked_row_idx if attacked_row_idx is not None else 'none'}",
                (5, 46),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (255, 180, 255),
                1,
            )

            cv2.imshow("Battle List Debug", vis)
            cv2.waitKey(1)
            self.battlelist_visualize_window_alive = True
        except Exception:
            pass

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
            self.last_monster_detection_debug_image = None
            return

        # 2. Run detection in fast mode by default.
        # Build debug image only when explicitly requested.
        need_debug = bool(test)
        if need_debug:
            raw_positions, debug_image = dm.detect_monsters(image, return_debug=True)
        else:
            raw_positions = dm.detect_monsters(image, return_debug=False)
            debug_image = None
        
        monster_positions = []
        
        # 3. Filter out Party Members
        # We assume Party Detection uses Sprite Center (Feet).
        # Our new detection ALSO targets Feet.
        # So we can use a tight distance check.
        party_positions = [p[0] for p in getattr(self, "party_positions", [])]
        if not party_positions:
            # Fast path: no party filtering needed.
            monster_positions = list(raw_positions)
        else:
            party_dist_sq = 45 * 45
            for (mx, my) in raw_positions:
                is_party = False
                for (px, py) in party_positions:
                    dx = px - mx
                    dy = py - my
                    if (dx * dx + dy * dy) < party_dist_sq:
                        is_party = True
                        if need_debug and debug_image is not None:
                            cv2.circle(debug_image, (mx, my), 6, (255, 0, 0), 2)
                        if test:
                            cv2.circle(image, (mx, my), 5, (255, 0, 0), -1)
                        break
                if not is_party:
                    monster_positions.append((mx, my))
                    if need_debug and debug_image is not None:
                        cv2.circle(debug_image, (mx, my), 6, (0, 255, 0), 2)
                    if test:
                        cv2.circle(image, (mx, my), 5, (0, 255, 0), -1)
        
        # Optional: visualize party positions used for filtering
        if need_debug and debug_image is not None:
            for (px, py) in party_positions:
                cv2.circle(debug_image, (int(px), int(py)), 4, (255, 0, 255), -1)

        self.monster_positions = monster_positions
        self.last_monster_detection_debug_image = debug_image
        
        if test:
            # Show the live debug window
            img.visualize_fast(image)
        
        return debug_image

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

    def _save_unwalkable_sample_from_frames(
        self,
        game_img,
        map_img,
        scale=None,
        scale_source="detected",
        capture_source="manual",
        tile_info=None,
        collision_unwalkable=None,
        collision_scale=None,
        extra_meta=None,
    ):
        if game_img is None or map_img is None:
            print("[UNW DATA] Failed to save sample: missing game/minimap image.")
            return None

        save_dir = os.path.join(self.base_directory, "training_data", "unwalkable_samples")
        os.makedirs(save_dir, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        game_filename = f"{timestamp}_game.png"
        map_filename = f"{timestamp}_minimap.png"
        json_filename = f"{timestamp}.json"

        game_path = os.path.join(save_dir, game_filename)
        map_path = os.path.join(save_dir, map_filename)
        json_path = os.path.join(save_dir, json_filename)

        if scale is None:
            try:
                scale = int(self.detect_minimap_scale(map_img))
                scale_source = "detected"
            except Exception:
                scale = int(max(1, getattr(self, "map_scale", 2)))
                scale_source = "runtime_fallback"
        scale = int(max(1, scale))

        if tile_info is None:
            tile_info = self._extract_tile_sets_from_map(map_img, scale)
        if collision_unwalkable is None:
            collision_unwalkable = []
        if collision_scale is None:
            collision_scale = int(scale)

        cv2.imwrite(game_path, game_img)
        cv2.imwrite(map_path, map_img)

        auto_unw = tile_info.get("unwalkable", [])
        auto_tp = tile_info.get("tp", [])
        data = {
            "session_type": "unwalkable_sample",
            "timestamp": timestamp,
            "zoom_level": int(scale),
            "zoom_level_source": str(scale_source),
            "sync_gold": bool(self._bool_value(getattr(self, "unwalkable_sync_gold", False))),
            "quality_tag": "sync_gold" if bool(self._bool_value(getattr(self, "unwalkable_sync_gold", False))) else "regular",
            "capture_source": str(capture_source),
            "files": {
                "game_screen": game_filename,
                "minimap": map_filename,
            },
            "map_scale": int(scale),
            "map_scale_runtime": int(max(1, getattr(self, "map_scale", scale))),
            "map_region": [int(v) for v in self.s_Map.region],
            "game_region": [int(v) for v in self.s_GameScreen.region],
            "auto": {
                "unwalkable": auto_unw,
                "tp": auto_tp,
                "collision_unwalkable": list(collision_unwalkable),
                "anchor_dx": int(tile_info.get("anchor_dx", 0)),
                "anchor_dy": int(tile_info.get("anchor_dy", 0)),
                "collision_scale": int(collision_scale),
            },
            # Editable ground-truth labels, seeded from auto detection to reduce manual work.
            "labels": {
                "unwalkable": list(auto_unw),
                "tp": list(auto_tp),
            },
        }
        if isinstance(extra_meta, dict):
            for k, v in extra_meta.items():
                if k in data:
                    continue
                data[k] = v

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=True)

        print(
            f"[UNW DATA] Saved sample {json_filename} "
            f"(src={capture_source} auto_unw={len(auto_unw)} auto_tp={len(auto_tp)} coll_unw={len(collision_unwalkable)})"
        )
        return json_filename

    def capture_unwalkable_sample(self):
        """
        Saves one offline sample for minimap unwalkable-tile annotation:
        - game_screen image
        - minimap image
        - auto-detected tiles (unwalkable/tp) and collision-grid tiles
        Output:
          training_data/unwalkable_samples/<timestamp>_{game|minimap}.png
          training_data/unwalkable_samples/<timestamp>.json
        """
        game_img = img.screengrab_array(self.hwnd, self.s_GameScreen.region)
        map_img = img.screengrab_array(self.hwnd, self.s_Map.region)
        if game_img is None or map_img is None:
            print("[UNW DATA] Failed to capture images (game/minimap).")
            return

        try:
            scale = int(self.detect_minimap_scale(map_img))
            scale_source = "detected"
        except Exception:
            scale = int(max(1, getattr(self, "map_scale", 2)))
            scale_source = "runtime_fallback"
        scale = int(max(1, scale))

        tile_info = self._extract_tile_sets_from_map(map_img, scale)
        coll_grid, coll_scale = self.get_local_collision_map()
        coll_unw = []
        if coll_grid is not None:
            ys, xs = np.where(coll_grid == 1)
            coll_unw = sorted([[int(r), int(c)] for r, c in zip(ys.tolist(), xs.tolist())])
        self._save_unwalkable_sample_from_frames(
            game_img=game_img,
            map_img=map_img,
            scale=scale,
            scale_source=scale_source,
            capture_source="manual",
            tile_info=tile_info,
            collision_unwalkable=coll_unw,
            collision_scale=(coll_scale if coll_scale is not None else scale),
        )
        
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
        # Keep runner-provided unified count (battle list + on-screen fallback).
        self.monster_count = max(int(getattr(self, "monster_count", 0)), len(self.monster_positions))

        # --- Exeta Res ---
        if self.monsters_around > 0:
            if self._bool_value(self.res): # Usamos _bool_value para estar seguros
                if "exeta" in self.slots:
                    self.castExetaRes()

        # --- Amp Res ---
        # Evaluate against full detected monster positions, not only close-range count.
        if self.monster_count > 0:
            if self._bool_value(self.amp_res) and "amp_res" in self.slots:
                if self._should_cast_amp_res():
                    self.castAmpRes(allow_rearm=True)

    def attackAreaSpells(self):
        """
        Attempts to cast Area Spells (Waves, UE).
        Returns True if a spell was cast (triggered GCD).
        """
        # 1. Safety & Cooldown Checks
        if self.buffs.get('pz', False) or int(getattr(self, "monster_count", 0)) == 0:
            return False
            
        # Check explicit delay (Global Cooldown)
        cur_sleep = timeInMillis() - self.last_attack_time
        if cur_sleep <= (100 + self.normal_delay):
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
            if int(getattr(self, "monster_count", 0)) < min_monsters: return False
            # Check internal Rune Timer AND Global Cooldown (Runes share group CD)
            if not self.delays.due("area_rune"): return False
            
            # Don't rune if we just cast a spell (GCD protection)
            cur_sleep = timeInMillis() - self.last_attack_time
            if cur_sleep <= (100 + self.normal_delay):
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
        if self.buffs.get('pz', False) or int(getattr(self, "monster_count", 0)) == 0: return

        cur_sleep = timeInMillis() - self.last_attack_time
        if cur_sleep <= (100 + self.normal_delay):
            return

        # Only cast if we have at least 1 monster
        if self.monsters_around >= 1:
            for slot in self.target_spells_slots:
                if self.check_spell_cooldowns:
                    if self.checkActionBarSlotCooldown(slot):
                        if self.clickActionbarSlot(slot, source="attackTargetSpells"):
                            self.updateLastAttackTime()
                            self.newNormalDelay()
                            return
                else:
                    self.clickActionbarSlot(slot, source="attackTargetSpells")
                    self.updateLastAttackTime()
                    self.newNormalDelay()
                    return
                
    def get_slot_image(self, pos):
        """Helper for GUI to visualize slots"""
        x, y = self.getActionbarSlotPosition(pos)
        region = (x, y, x + 34, y + 34)
        return img.screengrab_array(self.hwnd, region)

    def click_walk_target(self, x, y, min_interval_ms=450, min_delta_px=4):
        """
        Debounced movement click for minimap/pathing targets.
        Prevents spamming nearly identical walk clicks every frame.
        """
        now = timeInMillis()
        if self.last_walk_click_pos is not None:
            lx, ly = self.last_walk_click_pos
            dist = sqrt((x - lx) ** 2 + (y - ly) ** 2)
            if dist < min_delta_px and (now - self.last_walk_click_ms) < min_interval_ms:
                return False

        click_client(self.hwnd, int(x), int(y))
        self.last_walk_click_pos = (int(x), int(y))
        self.last_walk_click_ms = now
        return True
    
    def manageEquipment(self):
        if not self.delays.allow("equip_cycle"):
            return

        now_ms = timeInMillis()
        monster_count = int(getattr(self, "monster_count", 0) or 0)
        in_combat = monster_count > 0

        # Track combat-state transitions for asymmetric equip/unequip behavior.
        if not self.equip_state_initialized:
            self.equip_state_initialized = True
            self.equip_combat_state = in_combat
            self.equip_state_since_ms = now_ms
        elif in_combat != self.equip_combat_state:
            self.equip_combat_state = in_combat
            self.equip_state_since_ms = now_ms

        state_stable_ms = now_ms - self.equip_state_since_ms
        # Allow fast equip when combat starts, but require calm period before unequip.
        if (not in_combat) and state_stable_ms < 1200:
            return
        
        # Define the keys we care about
        equip_keys = ["weapon", "helmet", "armor", "amulet", "ring", "shield"]
        accessories = {"amulet", "ring"}
        
        for key in equip_keys:
            slot_id = self.slots.get(key)
            if slot_id is None: continue
            
            # Use safe access to slot_status
            if slot_id < len(self.slot_status) and self.slot_status[slot_id]:
                if self.isActionbarSlotEnabled(slot_id):
                    # Item is equipped/active. Unequip if safe.
                    if not in_combat:
                        # Accessories are server-sensitive (toggle/use semantics vary).
                        # Keep them equip-only to avoid re-equip/unequip oscillation.
                        if key in accessories:
                            continue
                        # print(f"Disabling {key}")
                        last_click_ms = int(self.equip_last_click_by_slot.get((slot_id, "unequip"), 0))
                        if (now_ms - last_click_ms) < 2500:
                            continue
                        self.clickActionbarSlot(
                            slot_id,
                            source="manageEquipment",
                            key=key,
                            equip_action="unequip",
                        )
                        self.equip_last_click_by_slot[(slot_id, "unequip")] = now_ms
                        return
                else:
                    # Item is unequipped. Equip if fighting.
                    if in_combat:
                        # print(f"Enabling {key}")
                        last_click_ms = int(self.equip_last_click_by_slot.get((slot_id, "equip"), 0))
                        if (now_ms - last_click_ms) < 350:
                            continue
                        self.clickActionbarSlot(
                            slot_id,
                            source="manageEquipment",
                            key=key,
                            equip_action="equip",
                        )
                        self.equip_last_click_by_slot[(slot_id, "equip")] = now_ms
                        return
            
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

    def execute_static_party_lure(self):
        """
        Lure dinámico: Si una marca no es visible, busca la siguiente en la secuencia.
        Siempre prioriza terminar el ciclo volviendo a 'skull'.
        """
        self.monster_count = self.get_effective_monster_count_for_cavebot()
        marks = self.getClosestMarks() # Busca la marca actual (self.current_mark)
        
        # --- ESTADO 1: TANQUEANDO / ESPERANDO EN SKULL ---
        if not self.lure_trip_active:
            if self.current_mark == "skull":
                # Si estamos en la base y el spawn está limpio, iniciamos
                if self.monster_count <= self.kill_stop_amount.get():
                    print("[STATIC LURE] Iniciando ronda de lure...")
                    self.lure_trip_active = True
                    self.nextMark() 
                    return
            else:
                self.current_mark = "skull"
                self.current_mark_index = 0

        # --- ESTADO 2: VIAJE DE LURE ACTIVO ---
        if self.lure_trip_active:
            # --- LÓGICA DE FLEXIBILIDAD (Si no ve la marca actual) ---
            if not marks:
                found_next = False
                # Escaneamos las marcas que siguen en la lista
                for i in range(self.current_mark_index + 1, len(self.mark_list)):
                    temp_mark = self.mark_list[i]
                    # Si alguna de las siguientes marcas es visible en el minimapa
                    if img.locateImage(
                        self.hwnd,
                        f"map_marks/{temp_mark}.png",
                        self.s_Map.region,
                        self._mark_match_threshold(temp_mark),
                    ):
                        print(f"[STATIC LURE] No veo {self.current_mark}, saltando a {temp_mark}")
                        self.current_mark_index = i
                        self.current_mark = temp_mark
                        found_next = True
                        break
                
                # Si llegamos al final de la lista y no vimos NADA, volvemos a Skull
                if not found_next:
                    if self.current_mark != "skull":
                        print("[STATIC LURE] Sin marcas visibles. Abortando regreso a 'skull'...")
                        self.current_mark = "skull"
                        self.current_mark_index = 0
                return

            # --- LÓGICA DE MOVIMIENTO (Si hay marca visible) ---
            dist, abs_pos, _ = marks[0]
            
            # Threshold dinámico: 6 para skull, 15 para el resto
            arrival_threshold = 6 if self.current_mark == "skull" else 15

            if dist <= arrival_threshold:
                if self.current_mark == "skull":
                    print("[STATIC LURE] Regreso exitoso. Tanqueando...")
                    self.lure_trip_active = False
                    self.clickStop(reason="static_lure_reached_skull")
                else:
                    print(f"[STATIC LURE] Marca {self.current_mark} alcanzada. Siguiente...")
                    self.nextMark()
                return

            # Ejecutar caminata
            if self.delays.allow("walk", base_ms=200):
                self.click_walk_target(abs_pos[0], abs_pos[1], min_interval_ms=450, min_delta_px=5)

    def cavebottest(self):
        self._sync_mark_cycle()
        # 1. Update basic state for this frame
        marks = self.getClosestMarks()
        self.monster_count = self.get_effective_monster_count_for_cavebot()
        kill_time = time.time() - self.kill_start_time
        
        # --- 2. STATE MACHINE (Toggle Kill Mode) ---
        if not self.kill:
            if self.monster_count >= self.kill_amount.get():
                print(f"[CAVEBOT] Switching to KITING. Monsters: {self.monster_count}")
                self.kill = True
                self.kill_start_time = time.time()
                self.clickStop(reason="cavebot_enter_kill_mode")
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

            # Tuned progression: avoid early mark switches.
            arrival_threshold = float(getattr(self, "cavebot_arrival_threshold_px", 4.0))
            confirm_frames = max(1, int(getattr(self, "cavebot_arrival_confirm_frames", 2)))
            immediate_px = float(getattr(self, "cavebot_immediate_advance_px", 1.0))

            # Keep streak coherent when target mark changes.
            if self.cavebot_arrival_last_mark != self.current_mark:
                self.cavebot_arrival_streak = 0
                self.cavebot_arrival_last_mark = self.current_mark

            now_ms = timeInMillis()
            reached_now = float(dist) <= arrival_threshold
            if reached_now:
                self.cavebot_arrival_streak += 1
            else:
                self.cavebot_arrival_streak = 0

            immediate_ok = float(dist) <= immediate_px
            confirmed_ok = self.cavebot_arrival_streak >= confirm_frames

            if reached_now and (immediate_ok or confirmed_ok):
                if now_ms < self.next_mark_eligible_ms:
                    self._cavebot_log(
                        f"arrival ignored mark={self.current_mark} dist={int(dist)} "
                        f"cooldown_left={self.next_mark_eligible_ms - now_ms}ms",
                        throttle_ms=120,
                    )
                    return
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
                self.clickStop(reason="cavebot_node_reached")
                self.cavebot_arrival_streak = 0
                self.nextMark()
                
                # REFRESH: Get the NEW mark data immediately so kiting/walking 
                # uses the new destination in this same frame.
                marks = self.getClosestMarks()

        # --- 4. NAVIGATION RESET (Fallback if no marks visible) ---
        if not marks:
            now_ms = timeInMillis()
            if self.current_mark == self.mark_list[-1]:
                if (now_ms - self.last_cavebot_reset_ms) < 800:
                    self._cavebot_log(
                        f"reset throttled mark={self.current_mark} dt={now_ms - self.last_cavebot_reset_ms}ms",
                        throttle_ms=120,
                    )
                    return
                self.loop_count += 1
                self.discovery_mode = False
                print(f"[CAVEBOT] Loop #{self.loop_count} Reset.")
                self.current_mark_index = 0
                self.current_mark = self.mark_list[0]
                self.last_cavebot_reset_ms = now_ms
                self._cavebot_log("reset -> skull (last mark had no candidates)", throttle_ms=0)
                marks = self.getClosestMarks()
                if not marks:
                    return
            else:
                # Do not auto-advance on transient no-visible; this caused pre-reach skips.
                self._cavebot_log(
                    f"no candidates for {self.current_mark}; holding current mark",
                    throttle_ms=200,
                )
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
            self.click_walk_target(abs_pos[0], abs_pos[1], min_interval_ms=500, min_delta_px=5)
    
    
    def executeLureWalk(self, mark_pos):
        # If the setting is off or no monsters, walk normally
        if not self.use_lure_walk.get() or self.monster_count == 0:
            if self.delays.allow("walk", base_ms=200):
                self.click_walk_target(mark_pos[0], mark_pos[1], min_interval_ms=450, min_delta_px=5)
            return

        now = time.time()
        elapsed_ms = (now - self.last_lure_action_time) * 1000

        if self.lure_phase == "walking":
            if elapsed_ms >= self.lure_walk_ms.get():
                # --- THE FIX ---
                # 1. See if we were attacking before we hit Stop
                was_attacking = self.isAttacking()
                
                # 2. Stop movement (and unfortunately, attack)
                self.clickStop(reason="lure_stutter_stop_phase")
                
                # 3. If we were attacking, resume IMMEDIATELY
                if was_attacking:
                    self.request_attack_reacquire(source="lure_stutter")
                # ---------------

                self.lure_phase = "stopping"
                self.last_lure_action_time = now
            else:
                # Maintain direction while walking
                if self.delays.allow("walk", base_ms=250):
                    self.click_walk_target(mark_pos[0], mark_pos[1], min_interval_ms=500, min_delta_px=5)

        elif self.lure_phase == "stopping":
            if elapsed_ms >= self.lure_stop_ms.get():
                self.lure_phase = "walking"
                self.last_lure_action_time = now
                self.click_walk_target(mark_pos[0], mark_pos[1], min_interval_ms=350, min_delta_px=4)

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
        
        # Immediate Attack Resume (throttled)
        self.request_attack_reacquire(source="recenter")
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
            
            self.request_attack_reacquire(source="kiting")

    def reset_marks_history(self):
        """Manually clears the 'visited' status of map marks."""
        print("[CAVEBOT] Resetting mark history. All marks are now fresh.")
        self._sync_mark_cycle(force_reset=True)
        for mark in self.mark_list:
            self.previous_marks[mark] = False
        # Optional: Reset index to start from the beginning of the list
        self.current_mark_index = 0
        self.current_mark = self.mark_list[0]
        # Keep manual painter (F11/F12) aligned with cavebot reset.
        self.add_mark_index = 0
        self.add_mark_type = self.mark_list[0]
        # Clear lap-memory state to truly reset history behavior.
        self.visited_history.clear()
        self.visited_fingerprints = []
        self.only_visited_last_mark = None
        self.only_visited_streak = 0
        self.discovery_mode = True
        self.next_mark_eligible_ms = 0
           
    def request_attack_reacquire(self, source="unknown"):
        """
        Schedules a throttled forced attack reacquire.
        Avoids spam from multiple movement systems requesting it in the same second.
        """
        now_ms = timeInMillis()
        if self.isAttacking():
            return
        if (now_ms - self.last_force_attack_request_ms) < 320:
            return
        self.last_force_attack_request_ms = now_ms
        self.GUI.root.after(50, lambda: self.clickAttack(force=True))

    def clickStop(self, reason="generic"):
        region = self.s_Stop.getCenter()
        if self._is_log_enabled("action"):
            print(f"[ACTION] trying to click STOP reason={reason} at client=({region[0]},{region[1]})")
        click_client(self.hwnd,region[0],region[1])

    def getMonsterDetectionDebugImage(self):
        return self.last_monster_detection_debug_image

    def getCenterMarkImage(self):
        map_center = self.s_Map.center
        region = (map_center[0]-5, map_center[1]-5, map_center[0]+5, map_center[1]+5)
        image = img.screengrab_array(self.hwnd,region)
        return image
    
    def updatePreviousMarks(self):
        self.previous_marks[self.current_mark] = self.getCenterMarkImage()
    
    def nextMark(self):
        self._sync_mark_cycle()
        self.current_mark_index += 1
        if self.current_mark_index >= len(self.mark_list):
            self.current_mark_index = 0
            
        self.current_mark = self.mark_list[self.current_mark_index]
        self.only_visited_last_mark = None
        self.only_visited_streak = 0
        print(f"[CAVEBOT] Next target mark: {self.current_mark}")
        self.next_mark_eligible_ms = timeInMillis() + 450
        
        # Debounce to prevent skipping multiple marks in one frame
        self.delays.trigger("walk", base_ms=500)
    
    def nextAddMark(self):
        """Advances the sequence for the manual painting tool only."""
        self._sync_mark_cycle()
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

    def _mark_match_threshold(self, mark_type):
        # Slightly more permissive thresholds for noisy minimaps/icons.
        # Lock tends to be the most fragile on some servers.
        if mark_type == "lock":
            return 0.80
        if mark_type == "skull":
            return 0.88
        return 0.89

    def getClosestMarks(self):
        scale = 3 
        map_region = self.s_Map.region
        mw, mh = map_region[2] - map_region[0], map_region[3] - map_region[1]
        map_rel_center = (self.s_Map.center[0] - map_region[0], self.s_Map.center[1] - map_region[1])
        
        map_img = img.screengrab_array(self.hwnd, map_region)
        if map_img is None: return []
        map_hd = cv2.resize(map_img, (mw * scale, mh * scale), interpolation=cv2.INTER_CUBIC)
        
        mark_thr = self._mark_match_threshold(self.current_mark)
        positions = img.locateManyImage(
            self.hwnd,
            f"map_marks/{self.current_mark}.png",
            map_region,
            mark_thr,
        )
        
        result = []
        visited_candidates = []
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
                else:
                    dist = distance.euclidean(map_rel_center, (rel_x, rel_y))
                    visited_candidates.append((dist, (map_region[0] + rel_x, map_region[1] + rel_y), (rel_x, rel_y)))

        fallback_used = False
        fallback_waiting = False
        fallback_streak = 0
        fallback_needed = max(1, int(getattr(self, "only_visited_confirm_scans", 3)))

        if result:
            self.only_visited_last_mark = None
            self.only_visited_streak = 0
        elif visited_candidates:
            if self.only_visited_last_mark == self.current_mark:
                self.only_visited_streak += 1
            else:
                self.only_visited_last_mark = self.current_mark
                self.only_visited_streak = 1

            fallback_streak = int(self.only_visited_streak)
            if self.only_visited_streak >= fallback_needed:
                visited_candidates.sort(key=lambda x: x[0])
                result = [visited_candidates[0]]
                fallback_used = True
            else:
                fallback_waiting = True
        else:
            self.only_visited_last_mark = None
            self.only_visited_streak = 0

        self.last_mark_scan_info = {
            "mark": self.current_mark,
            "threshold": float(mark_thr),
            "visible_count": int(len(positions) if positions else 0),
            "candidate_count": int(len(result)),
            "visited_count": int(len(visited_candidates)),
            "fallback_waiting": bool(fallback_waiting),
            "fallback_used": bool(fallback_used),
            "fallback_streak": int(fallback_streak),
            "fallback_needed": int(fallback_needed),
        }
        self._cavebot_log(
            f"scan mark={self.current_mark} thr={mark_thr:.2f} visible={len(positions) if positions else 0} "
            f"candidates={len(result)} visited={len(visited_candidates)} "
            f"fb_wait={int(fallback_waiting)} fb_used={int(fallback_used)} "
            f"fb={fallback_streak}/{fallback_needed}",
            throttle_ms=250,
        )

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

        elif kb.is_pressed('+'):
            if not self.key_debounce:
                self.key_debounce = True

        if kb.is_pressed('-'):
            if not self.key_debounce:
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

    # Ensure these are defined in your class constants or __init__
    COLOR_ROOM_BGR      = [51, 102, 153]    # #996633 (Brown Floor)
    COLOR_RED_TILE_BGR  = [0, 51, 255]      # #FF3300 (Red Tile)
    COLOR_GREY_TILE_BGR = [153, 153, 153]   # #999999 (Grey Tile)
    COLOR_TP_BGR        = [0, 255, 255]     # #FFFF00 (Yellow TP)

    def find_and_enter_tp(self, map_img):
        """Finds the closest yellow TP cluster in the provided map image and clicks it."""
        map_reg = self.s_Map.region
        
        # 1. Tolerant yellow mask (small channel tolerance)
        yellow = self._yellow_mask_bgr(map_img, tol=12)
        tp_mask = (yellow.astype(np.uint8) * 255) if yellow is not None else None
        if tp_mask is None:
            return

        # 2. Use contours to find the cluster center
        contours, _ = cv2.findContours(tp_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            print("[BOSS] No yellow TP pixels found on minimap.")
            return

        map_h, map_w = map_img.shape[:2]
        map_center = np.array([map_w // 2, map_h // 2])
        
        best_point = None
        min_dist = float('inf')

        for cnt in contours:
            M = cv2.moments(cnt)
            if M["m00"] == 0: continue
            
            cX = int(M["m10"] / M["m00"])
            cY = int(M["m01"] / M["m00"])
            
            dist = np.linalg.norm(np.array([cX, cY]) - map_center)
            
            if dist < min_dist:
                min_dist = dist
                best_point = (map_reg[0] + cX, map_reg[1] + cY)

        if best_point:
            print(f"[BOSS] Moving to TP cluster center: {best_point}")
            click_client(self.hwnd, best_point[0], best_point[1])

    def detect_lever_line_minimap(self, map_img):
        """
        Busca la secuencia horizontal de tiles grises.
        Retorna: (coordenadas, se_encontro_rojo)
        """
        map_reg = self.s_Map.region
        h, w, _ = map_img.shape
        S = self.map_scale 

        for y in range(h):
            for x in range(w - S):
                if list(map_img[y, x]) == self.COLOR_GREY_TILE_BGR:
                    # Confirmamos que es una línea viendo el siguiente tile a la derecha
                    if x + S < w and list(map_img[y, x + S]) == self.COLOR_GREY_TILE_BGR:
                        
                        # Buscamos el tile ROJO a la izquierda para tener la referencia exacta
                        if x - S >= 0 and list(map_img[y, x - S]) == self.COLOR_RED_TILE_BGR:
                            return (map_reg[0] + (x - S), map_reg[1] + y), True
                        
                        # Si no hay rojo (mapa negro), retornamos el primer gris para "descubrir"
                        return (map_reg[0] + x, map_reg[1] + y), False
        return None, False
              
    def get_vocation_delay(self):
        order = ["knight", "paladin", "sorcerer", "druid"]
        idx = order.index(self.vocation.lower()) if self.vocation.lower() in order else 4
        return idx * 0.4 

    def execute_boss_hotkey(self):
        """Trigger inicial para ENTRADA"""
        if not self.enable_boss_sequences:
            return
        delay = self.get_vocation_delay()
        print(f"[SEQUENCE] {self.vocation} espera {delay}s...")
        self.GUI.root.after(int(delay * 1000), lambda: self._set_active_sequence("enter"))

    def execute_exit_boss_sequence(self):
        """Trigger inicial para SALIDA"""
        if not self.enable_boss_sequences:
            return
        delay = self.get_vocation_delay()
        print(f"[SEQUENCE] {self.vocation} espera {delay}s...")
        self.GUI.root.after(int(delay * 1000), lambda: self._set_active_sequence("exit"))

    def _set_active_sequence(self, seq_type):
        self.active_sequence = seq_type

    def manage_boss_sequences(self):
        """Ejecuta el flujo completo de entrada o salida de forma automática."""
        if not self.enable_boss_sequences:
            return
        if not self.active_sequence:
            return

        map_reg = self.s_Map.region
        map_img = img.screengrab_array(self.hwnd, map_reg)
        if map_img is None: return

        room_type = self.detect_room_type_minimap(map_img)
        
        # --- SECUENCIA ENTRAR (+) ---
        if self.active_sequence == "enter":
            if room_type == 0: # Hallway
                if self.delays.due("walk"):
                    self.find_and_enter_tp(map_img)
                    self.delays.trigger("walk", base_ms=2500)
            
            elif room_type == 1: # Lever Room
                line_pos, is_red_tile = self.detect_lever_line_minimap(map_img)
                if line_pos:
                    if is_red_tile:
                        # If arrived, stop sequence immediately
                        if self.handle_minimap_lever_positioning(line_pos):
                            print(f"[SEQUENCE] {self.vocation} LISTO. Terminando secuencia.")
                            self.active_sequence = None 
                    else:
                        if self.delays.due("walk"):
                            print("[SEQUENCE] Descubriendo sala del lever...")
                            click_client(self.hwnd, line_pos[0], line_pos[1])
                            self.delays.trigger("walk", base_ms=1500)
                else:
                    if self.delays.due("walk"):
                        click_client(self.hwnd, self.s_Map.center[0], self.s_Map.center[1])
                        self.delays.trigger("walk", base_ms=1000)

        # --- SECUENCIA SALIR (-) ---
        elif self.active_sequence == "exit":
            if room_type == 2 or room_type == 1: # Boss o Lever Room
                if self.delays.due("walk"):
                    print("[SEQUENCE] Saliendo por TP...")
                    self.find_and_enter_tp(map_img)
                    self.delays.trigger("walk", base_ms=2500)
            
            elif room_type == 0: # Ya salimos al Hallway
                print("[SEQUENCE] Saliendo al siguiente boss...")
                self.auto_walk_tp_hall()
                self.active_sequence = None

    def handle_minimap_lever_positioning(self, red_map_pos):
        """Calculates destination based on vocation and moves character."""
        # Knight(1), Paladin(2), Sorcerer(3), Druid(4)
        vocation_map = {
            "knight": 1,
            "paladin": 2,
            "sorcerer": 3,
            "druid": 4
        }
        target_idx = vocation_map.get(self.vocation.lower(), 5)
        S = self.map_scale 

        # Destination on minimap relative to the red tile
        dest_x = red_map_pos[0] + (target_idx * S)
        dest_y = red_map_pos[1]

        map_reg = self.s_Map.region
        current_x = (map_reg[0] + map_reg[2]) // 2
        current_y = (map_reg[1] + map_reg[3]) // 2
        
        dist = sqrt((dest_x - current_x)**2 + (dest_y - current_y)**2)
        
        # INCREASED THRESHOLD: 0.8 tiles instead of 0.5 for stability
        if dist > (S * 0.8):
            if self.delays.due("walk"):
                # Only log when we actually click
                print(f"[BOSS] {self.vocation} moviéndose al tile {target_idx} (dist: {round(dist, 2)})")
                click_client(self.hwnd, dest_x, dest_y)
                self.delays.trigger("walk", base_ms=1500)
            return False
        else:
            print(f"[BOSS] {self.vocation} ha llegado a su posición final.")
            return True
    
    def detect_room_type_minimap(self, map_img):
        map_reg = self.s_Map.region
        mw, mh = map_img.shape[1], map_img.shape[0]
        cx, cy = mw // 2, mh // 2
        S = self.map_scale 

        brown_count = 0
        has_grey_line = False

        for r_tile in range(-6, 7):
            for c_tile in range(-6, 7):
                px = cx + (c_tile * S)
                py = cy + (r_tile * S)
                if 0 <= px < mw and 0 <= py < mh:
                    pixel = list(map_img[py, px])
                    if pixel == self.COLOR_ROOM_BGR:
                        brown_count += 1
                    if pixel == self.COLOR_GREY_TILE_BGR:
                        has_grey_line = True

        if brown_count > 3:
            return 1 if has_grey_line else 2
        return 0
    
    def detect_minimap_scale(self, map_img):
        try:
            mh, mw = map_img.shape[:2]
            cx, cy = mw // 2, mh // 2
            # Focus on center area near player cross: this is the most reliable
            # discovered terrain zone and avoids large black chunks at map borders.
            rx0, rx1 = max(0, cx - 84), min(mw, cx + 84)
            ry0, ry1 = max(0, cy - 64), min(mh, cy + 64)
            roi = map_img[ry0:ry1, rx0:rx1]
            if roi is None or roi.size == 0:
                return self.map_scale

            if not hasattr(self, "_terrain_codes_u32"):
                terrain = np.array(BotConstants.OBSTACLES + BotConstants.WALKABLE, dtype=np.uint8)
                self._terrain_codes_u32 = (
                    (terrain[:, 0].astype(np.uint32) << 16)
                    | (terrain[:, 1].astype(np.uint32) << 8)
                    | terrain[:, 2].astype(np.uint32)
                )

            def accumulate_row_min_widths(img_rows):
                width_counts = Counter()
                for row in img_rows:
                    if row.size == 0 or len(row) < 3:
                        continue
                    codes = (
                        (row[:, 0].astype(np.uint32) << 16)
                        | (row[:, 1].astype(np.uint32) << 8)
                        | row[:, 2].astype(np.uint32)
                    )
                    is_terrain = np.isin(codes, self._terrain_codes_u32, assume_unique=False)
                    # Ignore sparse/noisy rows (usually black/unknown dominated).
                    if int(np.count_nonzero(is_terrain)) < max(10, int(len(row) * 0.18)):
                        continue

                    runs = []
                    i = 0
                    n = len(codes)
                    while i < n:
                        if not is_terrain[i]:
                            i += 1
                            continue
                        c0 = int(codes[i])
                        j = i + 1
                        while j < n and is_terrain[j] and int(codes[j]) == c0:
                            j += 1
                        ln = int(j - i)
                        if 1 <= ln <= 10:
                            runs.append(ln)
                        i = j

                    if not runs:
                        continue

                    # Robust row-min: prefer smallest run length that appears at least twice.
                    # This suppresses isolated 1px noise segments.
                    rc = Counter(runs)
                    repeated = [k for k, v in rc.items() if v >= 2]
                    row_width = min(repeated) if repeated else min(runs)
                    width_counts[int(row_width)] += 1
                return width_counts

            # Horizontal + vertical scan (vertical via transpose) for stronger evidence.
            rows_h = [roi[r, :, :] for r in range(roi.shape[0])]
            roi_t = np.transpose(roi, (1, 0, 2))
            rows_v = [roi_t[r, :, :] for r in range(roi_t.shape[0])]
            widths = accumulate_row_min_widths(rows_h)
            widths.update(accumulate_row_min_widths(rows_v))

            total_votes = int(sum(widths.values()))
            if total_votes < 8:
                new_scale = self.map_scale
                e1 = e2 = e4 = 0.0
            else:
                # Width evidence mapping to scale classes.
                e1 = float(widths.get(1, 0))
                # Important observation from live logs:
                # - width 6 appears often on true x2, so count it mostly for x2.
                e2 = (
                    float(widths.get(2, 0))
                    + 0.3 * float(widths.get(3, 0))
                    + 0.9 * float(widths.get(6, 0))
                )
                e4 = (
                    float(widths.get(4, 0))
                    + 0.6 * float(widths.get(5, 0))
                    + 0.15 * float(widths.get(6, 0))
                    + 0.5 * float(widths.get(8, 0))
                )

                scores = [(1, e1), (2, e2), (4, e4)]
                best_scale, best_score = max(scores, key=lambda kv: kv[1])
                new_scale = int(best_scale) if best_score >= 3.0 else int(self.map_scale)

                # Guard against common collapse of x2/x4 into x1 in noisy scenes.
                if new_scale == 1:
                    if e2 >= max(3.0, 0.75 * e1):
                        new_scale = 2
                    elif e4 >= max(3.0, 0.90 * e1):
                        new_scale = 4
                # Extra guard: prevent x2 -> x4 flip unless x4 evidence clearly dominates.
                if int(self.map_scale) == 2 and new_scale == 4 and e4 < (1.15 * e2):
                    new_scale = 2

            # Diagnostic log: only under perf logging, throttled.
            now_ms = timeInMillis()
            should_log = (
                self._is_log_enabled("perf")
                and (now_ms - int(getattr(self, "last_zoom_widths_log_ms", 0))) >= 600
            )
            if should_log:
                self.last_zoom_widths_log_ms = now_ms
                print(
                    "[ZOOM WIDTHS] "
                    f"[1]:{int(widths.get(1, 0))} [2]:{int(widths.get(2, 0))} "
                    f"[4]:{int(widths.get(4, 0))} [6]:{int(widths.get(6, 0))} "
                    f"[8]:{int(widths.get(8, 0))} | "
                    f"E1={e1:.1f} E2={e2:.1f} E4={e4:.1f} -> {int(new_scale)}"
                )

            if new_scale != self.map_scale:
                print(f"[AUTO-SCALE] Instant switch detected: {new_scale}px/tile")
                self.map_scale = new_scale

            return self.map_scale

        except Exception:
            return self.map_scale

    def _yellow_mask_bgr(self, map_img, tol=12):
        """Returns a boolean mask for minimap yellow (#FFFF00 in BGR) with tolerance."""
        if map_img is None or map_img.size == 0:
            return None
        target = np.array(self.COLOR_TP_BGR, dtype=np.int16)
        diff = np.abs(map_img.astype(np.int16) - target)
        return np.all(diff <= int(max(0, tol)), axis=-1)

    def _refine_local_yellow_tiles(self, local_data, is_yellow, scale):
        """
        Reduce yellow false-positives near true TP tiles (mostly x1/x2 spill).
        Strategy: for each connected yellow component, keep the strongest tile.
        """
        if is_yellow is None:
            return is_yellow
        out = np.array(is_yellow, copy=True)
        s = int(max(1, scale))
        if s >= 4:
            return out

        h, w = out.shape
        visited = np.zeros((h, w), dtype=bool)
        dirs8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
        dirs4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        target_y = np.array(self.COLOR_TP_BGR, dtype=np.int16)
        target_r = np.array(self.COLOR_RED_TILE_BGR, dtype=np.int16)

        def red_neighbors(rr, cc):
            cnt = 0
            for dr, dc in dirs4:
                nr, nc = rr + dr, cc + dc
                if 0 <= nr < h and 0 <= nc < w:
                    d = np.abs(local_data[nr, nc].astype(np.int16) - target_r)
                    if int(np.sum(d)) <= 18:
                        cnt += 1
            return cnt

        for r in range(h):
            for c in range(w):
                if not out[r, c] or visited[r, c]:
                    continue
                comp = []
                stack = [(r, c)]
                visited[r, c] = True
                while stack:
                    cr, cc = stack.pop()
                    comp.append((cr, cc))
                    for dr, dc in dirs8:
                        nr, nc = cr + dr, cc + dc
                        if 0 <= nr < h and 0 <= nc < w and out[nr, nc] and not visited[nr, nc]:
                            visited[nr, nc] = True
                            stack.append((nr, nc))

                if len(comp) <= 1:
                    continue

                best_rc = None
                best_score = None
                for rr, cc in comp:
                    ydiff = int(np.sum(np.abs(local_data[rr, cc].astype(np.int16) - target_y)))
                    rnb = red_neighbors(rr, cc)
                    # Prefer tiles with red support around and purer yellow center color.
                    score = (rnb * 100) - ydiff
                    if best_score is None or score > best_score:
                        best_score = score
                        best_rc = (rr, cc)

                for rr, cc in comp:
                    out[rr, cc] = (rr, cc) == best_rc

        return out

    def _sample_minimap_grid(self, map_img, S):
        """
        Samples 15x11 minimap points with anchor search to avoid phase shifts.
        On x1/x2 zoom the true tile phase can be offset by one tile.
        """
        mh, mw = map_img.shape[:2]
        base_cx, base_cy = mw // 2, mh // 2
        # Empirical per-zoom pixel alignment from offline zoom-set benchmarks.
        # These are pixel shifts in minimap space (not tile shifts).
        if int(S) == 1:
            base_cx += 0
            base_cy += 1
        elif int(S) == 2:
            base_cx += -1
            base_cy += 1
        s = int(max(1, S))

        if not hasattr(self, "_terrain_codes_u32"):
            terrain = np.array(BotConstants.OBSTACLES + BotConstants.WALKABLE, dtype=np.uint8)
            self._terrain_codes_u32 = (
                (terrain[:, 0].astype(np.uint32) << 16)
                | (terrain[:, 1].astype(np.uint32) << 8)
                | terrain[:, 2].astype(np.uint32)
            )

        offsets = [(0, 0)]
        if s <= 2:
            offsets = [(dx, dy) for dy in (-s, 0, s) for dx in (-s, 0, s)]

        best_local = None
        best_meta = (base_cx, base_cy, 0, 0)
        best_score = None

        for dx, dy in offsets:
            cx, cy = base_cx + dx, base_cy + dy
            local = np.zeros((11, 15, 3), dtype=np.uint8)
            for r in range(11):
                for c in range(15):
                    px, py = cx + (c - 7) * s, cy + (r - 5) * s
                    if 0 <= px < mw and 0 <= py < mh:
                        local[r, c] = map_img[py, px]
                    else:
                        local[r, c] = [0, 0, 0]

            codes = (
                (local[:, :, 0].astype(np.uint32) << 16)
                | (local[:, :, 1].astype(np.uint32) << 8)
                | local[:, :, 2].astype(np.uint32)
            )
            terrain_hits = int(np.count_nonzero(np.isin(codes, self._terrain_codes_u32, assume_unique=False)))
            yellow_hits = int(np.count_nonzero(self._yellow_mask_bgr(local, tol=12)))
            center_bias = -int(abs(dx) + abs(dy))
            score = (terrain_hits + yellow_hits, center_bias)

            if (best_score is None) or (score > best_score):
                best_score = score
                best_local = local
                best_meta = (cx, cy, dx, dy)

        if best_local is None:
            best_local = np.zeros((11, 15, 3), dtype=np.uint8)
        cx, cy, dx, dy = best_meta
        return best_local, cx, cy, dx, dy

    def _estimate_player_cross_center(self, map_img):
        """
        Estimate minimap center from player cross pixels near map center.
        Returns (cx, cy) or None when not confidently found.
        """
        try:
            mh, mw = map_img.shape[:2]
            cx0, cy0 = mw // 2, mh // 2

            # Search only around the expected center to avoid UI noise.
            r = 8
            x0, x1 = max(0, cx0 - r), min(mw, cx0 + r + 1)
            y0, y1 = max(0, cy0 - r), min(mh, cy0 + r + 1)
            roi = map_img[y0:y1, x0:x1]
            if roi.size == 0:
                return None

            # Player cross is bright/white-ish on minimap.
            lower = np.array([210, 210, 210], dtype=np.uint8)
            upper = np.array([255, 255, 255], dtype=np.uint8)
            mask = cv2.inRange(roi, lower, upper)
            if int(np.count_nonzero(mask)) < 3:
                return None

            n, _labels, stats, cents = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), connectivity=8)
            if n <= 1:
                return None

            best_idx = None
            best_score = None
            for i in range(1, n):
                area = int(stats[i, cv2.CC_STAT_AREA])
                if area < 2:
                    continue
                cxr, cyr = float(cents[i][0]), float(cents[i][1])
                abs_x = x0 + cxr
                abs_y = y0 + cyr
                dist = float(((abs_x - cx0) ** 2 + (abs_y - cy0) ** 2) ** 0.5)
                # Prefer component closest to center and with moderate size.
                score = dist + (0.15 * abs(area - 6))
                if best_score is None or score < best_score:
                    best_score = score
                    best_idx = i

            if best_idx is None:
                return None
            cxr, cyr = cents[best_idx]
            return int(round(x0 + cxr)), int(round(y0 + cyr))
        except Exception:
            return None

    def _estimate_grid_center_from_transitions(self, map_img, S):
        """
        Estimate minimap grid center phase using terrain color transitions.
        This follows the same 'switch/switch spacing' principle used for zoom detection,
        but solves origin phase (mod S) for x/y sampling.
        """
        try:
            s = int(max(1, S))
            mh, mw = map_img.shape[:2]
            cx0, cy0 = mw // 2, mh // 2
            if s <= 1:
                return cx0, cy0

            # Precompute terrain membership codes.
            if not hasattr(self, "_terrain_codes_u32"):
                terrain = np.array(BotConstants.OBSTACLES + BotConstants.WALKABLE, dtype=np.uint8)
                self._terrain_codes_u32 = (
                    (terrain[:, 0].astype(np.uint32) << 16)
                    | (terrain[:, 1].astype(np.uint32) << 8)
                    | terrain[:, 2].astype(np.uint32)
                )

            x_start, x_end = max(0, cx0 - 90), min(mw, cx0 + 90)
            y_start, y_end = max(0, cy0 - 60), min(mh, cy0 + 60)

            # Horizontal strips (solve x-phase): fixed y, varying x.
            h_strips = [
                (map_img[np.clip(cy0 - 40, 0, mh - 1), x_start:x_end], x_start),
                (map_img[np.clip(cy0 + 40, 0, mh - 1), x_start:x_end], x_start),
            ]
            # Vertical strips (solve y-phase): fixed x, varying y.
            v_strips = [
                (map_img[y_start:y_end, np.clip(cx0 + 45, 0, mw - 1)].reshape(-1, 3), y_start),
                (map_img[y_start:y_end, np.clip(cx0 - 45, 0, mw - 1)].reshape(-1, 3), y_start),
            ]

            def collect_boundary_residues(strips, mod_s):
                residues = []
                for strip, base_idx in strips:
                    if strip.size == 0 or len(strip) < 3:
                        continue
                    codes = (
                        (strip[:, 0].astype(np.uint32) << 16)
                        | (strip[:, 1].astype(np.uint32) << 8)
                        | strip[:, 2].astype(np.uint32)
                    )
                    is_terrain = np.isin(codes, self._terrain_codes_u32, assume_unique=False)
                    changed = np.any(strip[1:] != strip[:-1], axis=1)
                    valid = is_terrain[1:] & is_terrain[:-1] & changed
                    edge_idx = np.flatnonzero(valid) + 1  # local indices
                    for i in edge_idx.tolist():
                        abs_i = int(base_idx + i)
                        residues.append(abs_i % mod_s)
                return residues

            x_res = collect_boundary_residues(h_strips, s)
            y_res = collect_boundary_residues(v_strips, s)

            def align_center(c0, residues, mod_s):
                if not residues:
                    return int(c0)
                counts = Counter(residues)
                boundary_phase = int(max(counts.items(), key=lambda kv: kv[1])[0])
                center_phase = (boundary_phase + (mod_s // 2)) % mod_s
                cur_phase = int(c0 % mod_s)
                delta = center_phase - cur_phase
                # shortest modular adjustment
                if delta > (mod_s // 2):
                    delta -= mod_s
                elif delta < -(mod_s // 2):
                    delta += mod_s
                return int(c0 + delta)

            cx = align_center(cx0, x_res, s)
            cy = align_center(cy0, y_res, s)
            return cx, cy
        except Exception:
            mh, mw = map_img.shape[:2]
            return mw // 2, mh // 2

    def _resolve_minimap_sampling_center(self, map_img, S):
        """Unified minimap sampling center used by collision + visualization."""
        center_from_cross = self._estimate_player_cross_center(map_img)
        if center_from_cross is not None:
            return center_from_cross
        return self._estimate_grid_center_from_transitions(map_img, S)

    def _shift_memory_grid(self, mem, dr, dc, fill_value=-1):
        out = np.full_like(mem, fill_value)
        src_r0 = max(0, -dr)
        src_r1 = min(mem.shape[0], mem.shape[0] - dr)
        src_c0 = max(0, -dc)
        src_c1 = min(mem.shape[1], mem.shape[1] - dc)
        dst_r0 = max(0, dr)
        dst_r1 = min(mem.shape[0], mem.shape[0] + dr)
        dst_c0 = max(0, dc)
        dst_c1 = min(mem.shape[1], mem.shape[1] + dc)
        if src_r1 > src_r0 and src_c1 > src_c0 and dst_r1 > dst_r0 and dst_c1 > dst_c0:
            out[dst_r0:dst_r1, dst_c0:dst_c1] = mem[src_r0:src_r1, src_c0:src_c1]
        return out

    def _detect_cross_occluded_tiles(self, local_data, scale):
        rad = 1 if int(scale) >= 4 else 2
        rr = np.arange(11).reshape(-1, 1)
        cc = np.arange(15).reshape(1, -1)
        near_center = (np.abs(rr - 5) <= rad) & (np.abs(cc - 7) <= rad)
        # Treat the center cross neighborhood as potentially occluded at all times.
        # White-only masks are too brittle across zoom/client themes.
        occluded = near_center.copy()
        occluded[5, 7] = True
        return occluded

    def _apply_minimap_tile_memory(self, map_img, local_data, is_obstacle, is_yellow, scale):
        t0 = time.perf_counter()
        mem = np.array(getattr(self, "minimap_tile_memory", np.full((11, 15), -1, dtype=np.int8)), copy=True)
        mem_y = np.array(getattr(self, "minimap_yellow_memory", np.full((11, 15), -1, dtype=np.int8)), copy=True)
        prev_map = getattr(self, "minimap_memory_prev_map", None)
        prev_scale = int(getattr(self, "minimap_memory_prev_scale", 0))
        S = int(max(1, scale))
        dr = 0
        dc = 0

        if prev_map is None or prev_scale != S:
            mem[:] = -1
            mem_y[:] = -1
        else:
            try:
                map_delta = float(np.mean(cv2.absdiff(map_img, prev_map)))
                dx, dy, conf, _method, valid, _reason = self._estimate_minimap_motion(
                    prev_map,
                    map_img,
                    max_shift=max(6, S * 4),
                    map_delta=map_delta,
                )
                if valid and conf >= 0.50:
                    dc = int(np.clip(round(float(dx) / float(S)), -3, 3))
                    dr = int(np.clip(round(float(dy) / float(S)), -3, 3))
                    if dr != 0 or dc != 0:
                        mem = self._shift_memory_grid(mem, dr, dc, fill_value=-1)
                        mem_y = self._shift_memory_grid(mem_y, dr, dc, fill_value=-1)
                elif map_delta >= 38.0:
                    # Floor change / discontinuity: discard stale local map memory.
                    mem[:] = -1
                    mem_y[:] = -1
            except Exception:
                pass

        occluded = self._detect_cross_occluded_tiles(local_data, S)
        recover_yellow_mask = occluded & (mem_y == 1)
        is_yellow[recover_yellow_mask] = True

        recover_obstacle_mask = occluded & (~is_yellow) & (mem == 1)
        is_obstacle[recover_obstacle_mask] = True
        is_obstacle[is_yellow] = False

        observe_all = ~occluded
        observe_non_yellow = observe_all & (~is_yellow)
        mem[observe_non_yellow] = is_obstacle[observe_non_yellow].astype(np.int8)
        mem_y[observe_all] = is_yellow[observe_all].astype(np.int8)
        mem[5, 7] = 0
        mem_y[5, 7] = 0

        self.minimap_tile_memory = mem
        self.minimap_yellow_memory = mem_y
        self.minimap_memory_prev_map = map_img.copy()
        self.minimap_memory_prev_scale = int(S)
        self.minimap_memory_occluded_count = int(np.count_nonzero(occluded))
        self.minimap_memory_recovered_count = int(np.count_nonzero(recover_obstacle_mask))
        self.minimap_memory_recovered_yellow_count = int(np.count_nonzero(recover_yellow_mask))
        self.minimap_memory_shift_rc = (int(dr), int(dc))
        self.minimap_memory_last_ms = float((time.perf_counter() - t0) * 1000.0)

        if self._is_log_enabled("perf"):
            now_ms = timeInMillis()
            if (now_ms - int(getattr(self, "last_minimap_memory_log_ms", 0))) >= 600:
                self.last_minimap_memory_log_ms = now_ms
                print(
                    "[PERF] minimap_memory "
                    f"dt={self.minimap_memory_last_ms:.2f}ms "
                    f"occ={self.minimap_memory_occluded_count} "
                    f"rec_obs={self.minimap_memory_recovered_count} "
                    f"rec_y={self.minimap_memory_recovered_yellow_count} "
                    f"shift=({dr},{dc})"
                )

        return is_obstacle, is_yellow

    def _extract_tile_sets_from_local_data(self, local_data, scale=2):
        """Returns unwalkable/tp tile sets from 15x11 sampled minimap data."""
        OBS = np.array(BotConstants.OBSTACLES, dtype=np.uint8)
        LOW_CONF_OBS = np.array(getattr(BotConstants, "LOW_CONF_OBSTACLES", []), dtype=np.uint8)
        is_obstacle = np.zeros((11, 15), dtype=bool)
        is_low_conf = np.zeros((11, 15), dtype=bool)
        is_yellow = self._yellow_mask_bgr(local_data, tol=12)
        is_yellow = self._refine_local_yellow_tiles(local_data, is_yellow, scale=scale)

        for r in range(11):
            for c in range(15):
                color = local_data[r, c]
                if np.any(np.all(color == OBS, axis=-1)):
                    is_obstacle[r, c] = True
                if LOW_CONF_OBS.size > 0 and np.any(np.all(color == LOW_CONF_OBS, axis=-1)):
                    is_low_conf[r, c] = True
                if is_yellow[r, c]:
                    is_obstacle[r, c] = False
                    is_low_conf[r, c] = False

        # Same low-confidence cluster heuristic as collision mapping.
        visited = np.zeros((11, 15), dtype=bool)
        dirs = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        for r in range(11):
            for c in range(15):
                if not is_low_conf[r, c] or visited[r, c]:
                    continue
                stack = [(r, c)]
                comp = []
                visited[r, c] = True
                while stack:
                    cr, cc = stack.pop()
                    comp.append((cr, cc))
                    for dr, dc in dirs:
                        nr, nc = cr + dr, cc + dc
                        if 0 <= nr < 11 and 0 <= nc < 15 and not visited[nr, nc] and is_low_conf[nr, nc]:
                            visited[nr, nc] = True
                            stack.append((nr, nc))
                if len(comp) <= 3:
                    for cr, cc in comp:
                        is_obstacle[cr, cc] = True

        unwalkable = {(int(r), int(c)) for r, c in zip(*np.where(is_obstacle))}
        tp = {(int(r), int(c)) for r, c in zip(*np.where(is_yellow))}
        return unwalkable, tp

    def _extract_tile_sets_from_map(self, map_img, scale):
        local_data, _cx, _cy, dx, dy = self._sample_minimap_grid(map_img, scale)
        unwalkable, tp = self._extract_tile_sets_from_local_data(local_data, scale=scale)
        return {
            "unwalkable": sorted([[int(r), int(c)] for (r, c) in unwalkable]),
            "tp": sorted([[int(r), int(c)] for (r, c) in tp]),
            "anchor_dx": int(dx),
            "anchor_dy": int(dy),
        }

    def get_local_collision_map(self):
        t_all0 = time.perf_counter()
        t0 = time.perf_counter()
        map_img = img.screengrab_array(self.hwnd, self.s_Map.region)
        t_capture_ms = (time.perf_counter() - t0) * 1000.0
        if map_img is None: 
            return None, self.map_scale

        # Keep zoom in sync with minimap, but avoid re-detecting every frame.
        # Zoom changes are infrequent; periodic checks reduce collision-path cost.
        now_ms = timeInMillis()
        t_scale_ms = 0.0
        if (now_ms - int(getattr(self, "last_scale_check", 0))) >= 300:
            ts0 = time.perf_counter()
            try:
                self.map_scale = int(self.detect_minimap_scale(map_img))
            except Exception:
                pass
            t_scale_ms = (time.perf_counter() - ts0) * 1000.0
            self.last_scale_check = now_ms
        S = int(max(1, self.map_scale))
        ts0 = time.perf_counter()
        mh, mw = map_img.shape[:2]
        cx, cy = self._resolve_minimap_sampling_center(map_img, S)
        # Same empirical per-zoom alignment used by offline zoom-set benchmarks.
        if int(S) == 1:
            cx += 0
            cy += 0
        elif int(S) == 2:
            cx += -1
            cy += 1
        # Runtime path: use resolved center directly to avoid phase-jump tile shifts.
        local_data = np.zeros((11, 15, 3), dtype=np.uint8)
        for r in range(11):
            for c in range(15):
                px, py = cx + (c - 7) * S, cy + (r - 5) * S
                if 0 <= px < mw and 0 <= py < mh:
                    local_data[r, c] = map_img[py, px]
                else:
                    local_data[r, c] = [0, 0, 0]
        self.minimap_grid_anchor_dx = 0
        self.minimap_grid_anchor_dy = 0
        t_sample_ms = (time.perf_counter() - ts0) * 1000.0
        
        # 1. Prepare obstacle code caches (packed u32 BGR).
        if not hasattr(self, "_obs_codes_u32"):
            obs = np.array(BotConstants.OBSTACLES, dtype=np.uint8)
            self._obs_codes_u32 = (
                (obs[:, 0].astype(np.uint32) << 16)
                | (obs[:, 1].astype(np.uint32) << 8)
                | obs[:, 2].astype(np.uint32)
            )
        if not hasattr(self, "_low_conf_obs_codes_u32"):
            low_obs = np.array(getattr(BotConstants, "LOW_CONF_OBSTACLES", []), dtype=np.uint8)
            if low_obs.size > 0:
                self._low_conf_obs_codes_u32 = (
                    (low_obs[:, 0].astype(np.uint32) << 16)
                    | (low_obs[:, 1].astype(np.uint32) << 8)
                    | low_obs[:, 2].astype(np.uint32)
                )
            else:
                self._low_conf_obs_codes_u32 = np.array([], dtype=np.uint32)

        # 3. Terrain check (vectorized):
        # - Strong obstacles: always blocked.
        # - Low-confidence obstacles: blocked only when part of small clusters (<=3).
        is_yellow = self._yellow_mask_bgr(local_data, tol=12)
        is_yellow = self._refine_local_yellow_tiles(local_data, is_yellow, scale=S)
        ts0 = time.perf_counter()
        codes = (
            (local_data[:, :, 0].astype(np.uint32) << 16)
            | (local_data[:, :, 1].astype(np.uint32) << 8)
            | local_data[:, :, 2].astype(np.uint32)
        )
        is_obstacle = np.isin(codes, self._obs_codes_u32, assume_unique=False)
        if self._low_conf_obs_codes_u32.size > 0:
            is_low_conf = np.isin(codes, self._low_conf_obs_codes_u32, assume_unique=False)
        else:
            is_low_conf = np.zeros((11, 15), dtype=bool)
        is_obstacle[is_yellow] = False
        is_low_conf[is_yellow] = False
        t_classify_ms = (time.perf_counter() - ts0) * 1000.0

        ts0 = time.perf_counter()
        is_obstacle, is_yellow = self._apply_minimap_tile_memory(
            map_img=map_img,
            local_data=local_data,
            is_obstacle=is_obstacle,
            is_yellow=is_yellow,
            scale=S,
        )
        t_memory_ms = (time.perf_counter() - ts0) * 1000.0

        # Low-confidence cluster heuristic:
        # Treat as blocked only if connected cluster size is small (<=3 tiles).
        ts0 = time.perf_counter()
        visited = np.zeros((11, 15), dtype=bool)
        dirs = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        for r in range(11):
            for c in range(15):
                if not is_low_conf[r, c] or visited[r, c]:
                    continue

                stack = [(r, c)]
                comp = []
                visited[r, c] = True

                while stack:
                    cr, cc = stack.pop()
                    comp.append((cr, cc))
                    for dr, dc in dirs:
                        nr, nc = cr + dr, cc + dc
                        if 0 <= nr < 11 and 0 <= nc < 15 and not visited[nr, nc] and is_low_conf[nr, nc]:
                            visited[nr, nc] = True
                            stack.append((nr, nc))

                if len(comp) <= 3:
                    for cr, cc in comp:
                        is_obstacle[cr, cc] = True
        t_lowconf_ms = (time.perf_counter() - ts0) * 1000.0

        # 4. Initialize Grid
        ts0 = time.perf_counter()
        grid = np.zeros((11, 15), dtype=int)
        grid[is_obstacle] = 1
        grid[5, 7] = 3 # Player tile constant
        # Keep pre-interpolation/raw obstacle view for strict nearby-space checks.
        self.raw_collision_grid = grid.copy()

        # 5. Apply 3-Point Connectivity interpolation (Preserved)
        # We KEEP this because it connects detected obstacles to form solid walls
        if S == 1:
            # Keep anti-cross cleanup, but never erase tiles already classified as blocked.
            for rr in range(5, 7):
                for cc in range(5, 11):
                    if not is_obstacle[rr, cc]:
                        grid[rr, cc] = 0
            for rr in range(3, 9):
                for cc in range(7, 9):
                    if not is_obstacle[rr, cc]:
                        grid[rr, cc] = 0
            grid[5, 7] = 3
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
            if not is_obstacle[4, 7]: grid[4, 7] = 0
            if not is_obstacle[6, 7]: grid[6, 7] = 0
            if not is_obstacle[5, 6]: grid[5, 6] = 0
            if not is_obstacle[5, 8]: grid[5, 8] = 0
            if is_obstacle[3, 7] and grid[4, 6] == 1 and grid[4, 8] == 1: grid[4, 7] = 1
            if is_obstacle[7, 7] and grid[6, 6] == 1 and grid[6, 8] == 1: grid[6, 7] = 1
            if is_obstacle[5, 5] and grid[4, 6] == 1 and grid[6, 6] == 1: grid[5, 6] = 1
            if is_obstacle[5, 9] and grid[4, 8] == 1 and grid[6, 8] == 1: grid[5, 8] = 1
        t_grid_ms = (time.perf_counter() - ts0) * 1000.0

        t_total_ms = (time.perf_counter() - t_all0) * 1000.0
        if self._is_log_enabled("perf"):
            now_ms2 = timeInMillis()
            if (now_ms2 - int(getattr(self, "last_collision_map_breakdown_log_ms", 0))) >= 800:
                self.last_collision_map_breakdown_log_ms = now_ms2
                print(
                    "[PERF] collision_map_breakdown "
                    f"total={t_total_ms:.2f}ms "
                    f"capture={t_capture_ms:.2f}ms "
                    f"scale={t_scale_ms:.2f}ms "
                    f"sample={t_sample_ms:.2f}ms "
                    f"classify={t_classify_ms:.2f}ms "
                    f"memory={t_memory_ms:.2f}ms "
                    f"low_conf={t_lowconf_ms:.2f}ms "
                    f"grid_interp={t_grid_ms:.2f}ms"
                )

        return grid, S
    def get_player_grid_pos(self):  
        """Standardized center of the 15x11 grid."""
        return (5, 7) # (row, col)
    
    def visualize_monster_grid(self, collision_grid, current_s):
        try:
            if timeInMillis() < int(getattr(self, "visualize_pause_until_ms", 0)):
                return
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

            # Detect minimap yellow tiles at tile-center samples (same grid logic as
            # obstacle detection) to avoid edge-pixel spill into neighboring tiles.
            tp_tiles = set()
            map_img = img.screengrab_array(self.hwnd, self.s_Map.region)
            if map_img is not None:
                s = int(max(1, self.map_scale))
                # Use the exact same phase-stable sampling as collision extraction.
                local_data, _mcx, _mcy, _adx, _ady = self._sample_minimap_grid(map_img, s)
                yellow_local = self._yellow_mask_bgr(local_data, tol=12)
                ys, xs = np.where(yellow_local)
                for gr, gc in zip(ys.tolist(), xs.tolist()):
                    tp_tiles.add((int(gr), int(gc)))
            mem_y = getattr(self, "minimap_yellow_memory", None)
            if (
                mem_y is not None
                and isinstance(mem_y, np.ndarray)
                and mem_y.shape == (11, 15)
                and map_img is not None
            ):
                # Match runtime collision policy: memory yellow only recovers
                # potentially cross-occluded center cells, not the whole map.
                occluded = self._detect_cross_occluded_tiles(local_data, s)
                ys, xs = np.where((mem_y == 1) & occluded)
                for gr, gc in zip(ys.tolist(), xs.tolist()):
                    tp_tiles.add((int(gr), int(gc)))

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
                    elif (row, col) in tp_tiles:
                        # Minimap yellow tiles (TP) shown in green on spatial view.
                        cv2.rectangle(overlay, (tx, ty), (tx2, ty2), (0, 140, 0), -1)
                    elif collision_grid is not None and collision_grid[row, col] == 1:
                        cv2.rectangle(overlay, (tx, ty), (tx2, ty2), (180, 50, 0), -1)
                    
                    cv2.rectangle(vis, (tx, ty), (tx2, ty2), (45, 45, 45), 1)

            # --- DRAW MONSTERS ---
            unreachable_tiles = set()
            for mx, my in getattr(self, "monster_positions_unreachable", []) or []:
                unreachable_tiles.add((int(my / tile_h_float), int(mx / tile_w_float)))

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
                        
                    if (m_row, m_col) in unreachable_tiles:
                        cv2.rectangle(overlay, (tx, ty), (tx2, ty2), (0, 120, 220), -1)
                        cv2.circle(vis, (int(mx), int(my)), 2, (0, 165, 255), -1)
                    else:
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
            cv2.putText(
                vis,
                f"TP tiles: {len(tp_tiles)}",
                (10, 74),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 255, 120),
                1,
            )
            cv2.putText(
                vis,
                f"Monsters reachable/unreachable: {int(getattr(self, 'monster_count_reachable', 0))}/"
                f"{int(getattr(self, 'monster_count_unreachable', 0))}",
                (10, 96),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 200, 255),
                1,
            )
            mem_occ = int(getattr(self, "minimap_memory_occluded_count", 0))
            mem_rec = int(getattr(self, "minimap_memory_recovered_count", 0))
            mem_rec_y = int(getattr(self, "minimap_memory_recovered_yellow_count", 0))
            mem_dr, mem_dc = getattr(self, "minimap_memory_shift_rc", (0, 0))
            cv2.putText(
                vis,
                f"MM memory occ={mem_occ} rec_obs={mem_rec} rec_y={mem_rec_y} shift=({int(mem_dr)},{int(mem_dc)})",
                (10, 118),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (255, 210, 120),
                1,
            )
            if self.vocation == "knight" and hasattr(self, "amp_res_debug") and self.amp_res_debug:
                dbg = self.amp_res_debug
                reason = str(dbg.get("reason", "n/a"))
                far_count = dbg.get("far_count", 0)
                free_tiles = dbg.get("free_melee_tiles", 0)
                stagnant_ms = dbg.get("stagnant_ms", 0)
                cv2.putText(
                    vis,
                    f"AMP RES | reason={reason} far={far_count} free={free_tiles} stagnant={stagnant_ms}ms",
                    (10, 52),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (0, 200, 255),
                    1
                )
            
            cv2.addWeighted(overlay, 0.4, vis, 0.6, 0, vis)
            cv2.imshow("AI Spatial Vision", vis)
            cv2.waitKey(1)
            self.visualize_window_alive = True
        except Exception as e:
            print("Visualization error:", e)
            self.visualize_window_alive = False
            pass
    
    def debug_boss_tp_minimap(self):
        """Visualizes TPs, walk target, and state info."""
        map_reg = self.s_Map.region
        map_img = img.screengrab_array(self.hwnd, map_reg)
        if map_img is None: return

        scale_factor = 3
        vis_frame = cv2.resize(map_img, (0, 0), fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_NEAREST)
        h, w, _ = map_img.shape
        S = self.map_scale
        found_tps = self.find_boss_tps_list(map_img)

        for x, y in found_tps:
            vx, vy = x * scale_factor, y * scale_factor
            cv2.rectangle(vis_frame, (vx - (S*scale_factor)//2, vy - (S*scale_factor)//2),
                          (vx + (S*scale_factor)//2, vy + (S*scale_factor)//2), (0, 255, 0), 1)

        if hasattr(self, 'current_walk_target') and self.current_walk_target:
            tx_rel, ty_rel = self.current_walk_target[0] - map_reg[0], self.current_walk_target[1] - map_reg[1]
            v_tx, v_ty = tx_rel * scale_factor, ty_rel * scale_factor
            cv2.drawMarker(vis_frame, (v_tx, v_ty), (255, 0, 0), cv2.MARKER_CROSS, 8, 2)
            cx, cy = (w // 2) * scale_factor, (h // 2) * scale_factor
            cv2.line(vis_frame, (cx, cy), (v_tx, v_ty), (255, 255, 0), 1)

        cv2.putText(vis_frame, f"Scale: {S}px/t | TPs: {len(found_tps)}", (10, 20), 0, 0.4, (255, 255, 255), 1)
        cv2.imshow("Boss TP Scanner Debug", vis_frame)
        cv2.waitKey(1)
        return found_tps
    
    def get_minimap_fingerprint(self, map_img):
        """Crops the center 1/3 of the minimap and removes the player cross."""
        h, w = map_img.shape[:2]
        # Center 1/3 dimensions
        ch, cw = h // 3, w // 3
        start_y, start_x = (h - ch) // 2, (w - cw) // 2
        
        fingerprint = map_img[start_y:start_y+ch, start_x:start_x+cw].copy()
        
        # Remove Player Cross: The center of the fingerprint is the player.
        # We paint a small black square over the absolute center.
        f_cy, f_cx = ch // 2, cw // 2
        fingerprint[f_cy-2:f_cy+3, f_cx-2:f_cx+3] = [0, 0, 0]
        
        return fingerprint

    def auto_walk_tp_hall(self):
        """Grid-based clockwise walker with explicit axis forcing for corners."""
        map_reg = self.s_Map.region
        map_img = img.screengrab_array(self.hwnd, map_reg)
        if map_img is None: return

        found_tps = self.find_boss_tps_list(map_img)
        if not found_tps: return

        h, w = map_img.shape[:2]
        cx, cy = w // 2, h // 2
        S = self.map_scale 

        found_tps.sort(key=lambda p: sqrt((p[0]-cx)**2 + (p[1]-cy)**2))
        pivot = found_tps[0]
        px, py = pivot
        
        target_tp = None
        force_axis = None # 'h' or 'v'

        # --- CASE: RIGHT WALL ---
        if px > cx + S:
            col_neighbors = [tp for tp in found_tps if abs(tp[0] - px) < S and tp[1] > py + S]
            if col_neighbors:
                target_tp = sorted(col_neighbors, key=lambda p: p[1])[0]
                force_axis = 'v'
                print("[WALKER] Wall: RIGHT -> Action: Next Down")
            else:
                quadrant = [tp for tp in found_tps if tp[1] > cy + S and tp[0] < cx + S]
                if quadrant:
                    target_tp = sorted(quadrant, key=lambda p: p[0], reverse=True)[0]
                    force_axis = 'h'
                    print("[WALKER] Wall: RIGHT CORNER -> Action: Jump to Bottom Row")

        # --- CASE: BOTTOM WALL ---
        elif py > cy + S:
            row_neighbors = [tp for tp in found_tps if abs(tp[1] - py) < S and tp[0] < px - S]
            if row_neighbors:
                target_tp = sorted(row_neighbors, key=lambda p: p[0], reverse=True)[0]
                force_axis = 'h'
                print("[WALKER] Wall: BOTTOM -> Action: Next Left")
            else:
                quadrant = [tp for tp in found_tps if tp[0] < cx - S and tp[1] < cy + S]
                if quadrant:
                    target_tp = sorted(quadrant, key=lambda p: p[1], reverse=True)[0]
                    force_axis = 'v'
                    print("[WALKER] Wall: BOTTOM CORNER -> Action: Jump to Left Wall")

        # --- CASE: LEFT WALL ---
        elif px < cx - S:
            col_neighbors = [tp for tp in found_tps if abs(tp[0] - px) < S and tp[1] < py - S]
            if col_neighbors:
                target_tp = sorted(col_neighbors, key=lambda p: p[1], reverse=True)[0]
                force_axis = 'v'
                print("[WALKER] Wall: LEFT -> Action: Next Up")
            else:
                quadrant = [tp for tp in found_tps if tp[1] < cy - S and tp[0] > cx - S]
                if quadrant:
                    target_tp = sorted(quadrant, key=lambda p: p[0])[0]
                    force_axis = 'h'
                    print("[WALKER] Wall: LEFT CORNER -> Action: Jump to Top Row")

        # --- CASE: TOP WALL ---
        elif py < cy - S:
            row_neighbors = [tp for tp in found_tps if abs(tp[1] - py) < S and tp[0] > px + S]
            if row_neighbors:
                target_tp = sorted(row_neighbors, key=lambda p: p[0])[0]
                force_axis = 'h'
                print("[WALKER] Wall: TOP -> Action: Next Right")
            else:
                quadrant = [tp for tp in found_tps if tp[0] > cx + S and tp[1] > cy - S]
                if quadrant:
                    target_tp = sorted(quadrant, key=lambda p: p[1])[0]
                    force_axis = 'v'
                    print("[WALKER] Wall: TOP CORNER -> Action: Jump to Right Wall")

        if not target_tp:
            target_tp = next((tp for tp in found_tps if sqrt((tp[0]-cx)**2 + (tp[1]-cy)**2) > S * 2), pivot)

        # Update fingerprint before the move
        fp = self.get_minimap_fingerprint(map_img)
        self._manage_fingerprint_storage(fp)

        self.execute_parallel_walk_click(target_tp, map_reg, map_img, cx, cy, force_axis)

    def execute_parallel_walk_click(self, target_tp, map_reg, map_img, cx, cy, force_axis=None):
        """Forces the click to be 2 tiles 'inward' from the target wall segment."""
        tx, ty = target_tp
        S = self.map_scale
        
        # 1. Determine local orientation
        is_h_segment = list(map_img[ty, tx-S]) == self.COLOR_RED_TILE_BGR or \
                       list(map_img[ty, tx+S]) == self.COLOR_RED_TILE_BGR
        
        is_v_segment = list(map_img[ty-S, tx]) == self.COLOR_RED_TILE_BGR or \
                       list(map_img[ty+S, tx]) == self.COLOR_RED_TILE_BGR

        # 2. Strict Directional Pushing with Override logic
        # Priority: If we specifically know we are moving to a Vertical wall, use V-Push
        if force_axis == 'v' or (is_v_segment and not is_h_segment):
            off_x = 2*S if tx < cx else -2*S
            final_click = (map_reg[0] + tx + off_x, map_reg[1] + ty)
            print(f"[WALKER] V-Wall Push: {'Right' if off_x > 0 else 'Left'}")
            
        elif force_axis == 'h' or is_h_segment:
            off_y = 2*S if ty < cy else -2*S
            final_click = (map_reg[0] + tx, map_reg[1] + ty + off_y)
            print(f"[WALKER] H-Wall Push: {'Down' if off_y > 0 else 'Up'}")
        
        else:
            # Corner/Isolated fallback: Vector towards center
            vx, vy = cx - tx, cy - ty
            mag = max(1, sqrt(vx**2 + vy**2))
            final_click = (map_reg[0] + tx + int((vx/mag)*2*S), map_reg[1] + ty + int((vy/mag)*2*S))
            print("[WALKER] Corner/Isolated Push: Inward to Center")

        # 3. Double Check: Destination floor safety
        rel_x, rel_y = final_click[0] - map_reg[0], final_click[1] - map_reg[1]
        if rel_x < 0 or rel_x >= map_img.shape[1] or rel_y < 0 or rel_y >= map_img.shape[0] or \
           list(map_img[rel_y, rel_x]) != self.COLOR_GREY_TILE_BGR:
            print("[WALKER] Warning: Destination not floor. Using 1-tile safe push.")
            vx, vy = (1 if cx > tx else -1), (1 if cy > ty else -1)
            final_click = (map_reg[0] + tx + vx*S, map_reg[1] + ty + vy*S)

        self.current_walk_target = final_click
        click_client(self.hwnd, final_click[0], final_click[1])
        self.delays.trigger("walk", base_ms=3000)
    
    def _manage_fingerprint_storage(self, fp):
        if not self.hallway_images:
            self.hallway_images.append(fp)
            return

        # Compare current fingerprint with the VERY FIRST one we took
        res = cv2.matchTemplate(fp, self.hallway_images[0], cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        
        if max_val > 0.96 and len(self.hallway_images) > 10:
            print("[WALKER] FULL LAP DETECTED. Stopping walker.")
            self.is_auto_walking = False
            return
        is_duplicate = False
        for saved_fp in self.hallway_images:
            res = cv2.matchTemplate(fp, saved_fp, cv2.TM_CCOEFF_NORMED)
            if cv2.minMaxLoc(res)[1] > 0.95:
                is_duplicate = True
                break
        
        if not is_duplicate:
            self.hallway_images.append(fp)

    def find_boss_tps_list(self, map_img):
        """Helper that returns a list of (x, y) relative coords for TPs."""
        h, w = map_img.shape[:2]
        S = self.map_scale
        tps = []
        yellow = self._yellow_mask_bgr(map_img, tol=12)
        if yellow is None:
            return tps
        for y in range(S, h - S):
            for x in range(S, w - S):
                if yellow[y, x]:
                    # Sandwich check
                    if (list(map_img[y, x-S]) == self.COLOR_RED_TILE_BGR and list(map_img[y, x+S]) == self.COLOR_RED_TILE_BGR) or \
                       (list(map_img[y-S, x]) == self.COLOR_RED_TILE_BGR and list(map_img[y+S, x]) == self.COLOR_RED_TILE_BGR):
                        tps.append((x, y))
        return tps
    
def run_bot_loop(bot=None):
    from .runner import BotRunner

    if bot is None:
        bot = Bot()
    return BotRunner(bot).run()


def main():
    run_bot_loop()


if __name__ == "__main__":
    main()
