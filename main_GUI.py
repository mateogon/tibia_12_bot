import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk
import cv2
import numpy as np

# --- VOCATION PRESETS ---
# Define default settings for each class
PRESETS = {
    "knight": {
        "hp_thresh_high": 90, "hp_thresh_low": 60, "mp_thresh": 20,
        "attack_spells": True, "res": True, "amp_res": False,
        "use_area_rune": False, "use_utito": True,
        "min_monsters_around_spell": 2, 
        "min_monsters_for_rune": 1
    },
    "druid": {
        "hp_thresh_high": 95, "hp_thresh_low": 75, "mp_thresh": 50,
        "attack_spells": True, "res": False, "amp_res": False,
        "use_area_rune": True, "use_utito": False,
        "min_monsters_around_spell": 2,
        "min_monsters_for_rune": 1
    },
    "sorcerer": {
        "hp_thresh_high": 95, "hp_thresh_low": 70, "mp_thresh": 50,
        "attack_spells": True, "res": False, "amp_res": False,
        "use_area_rune": True, "use_utito": False,
        "min_monsters_around_spell": 2,
        "min_monsters_for_rune": 1
    },
    "paladin": {
        "hp_thresh_high": 92, "hp_thresh_low": 65, "mp_thresh": 40,
        "attack_spells": True, "res": False, "amp_res": False,
        "use_area_rune": True, "use_utito": True,
        "min_monsters_around_spell": 3,
        "min_monsters_for_rune": 1
    }
}

class ModernBotGUI:
    def __init__(self, bot, char_name, vocation):
        self.bot = bot
        self.char_name = char_name
        
        # Normalize vocation string
        clean_voc = vocation.lower()
        if "knight" in clean_voc: self.vocation = "knight"
        elif "druid" in clean_voc: self.vocation = "druid"
        elif "sorc" in clean_voc: self.vocation = "sorcerer"
        elif "paladin" in clean_voc: self.vocation = "paladin"
        else: self.vocation = "knight" # Default

        # Theme Setup
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        # Root Window
        self.root = ctk.CTk()
        self.root.title(f"TibiaBot 2025 - {char_name} ({self.vocation.title()})")
        self.root.geometry("600x750")
        
        # Variable Storage
        self.vars = {}
        self._init_variables()
        
        # Apply Preset defaults immediately
        self.apply_preset(self.vocation)

        # Image references
        self.map_tk_image = None
        self.map_label = None

        # Build UI
        self._build_ui()

        # Start Map Timer
        self.root.after(500, self._update_map_loop)

        # Handle Close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _init_variables(self):
        """
        Binds GUI variables directly to the Bot object.
        Uses tracing to validate inputs (Prevent Strings in Int fields).
        """
        # Boolean Variables
        bool_keys = [
            'loop', 'attack', 'attack_spells', 'hp_heal', 'mp_heal', 
            'manual_loot', 'cavebot', 'res', 'follow_party', 'use_area_rune', 
            'manage_equipment', 'loot_on_spot', 'amp_res', 'show_area_rune_target',
            'use_utito'
        ]
        for key in bool_keys:
            # Create Var
            val = getattr(self.bot, key, False)
            if hasattr(val, 'get'): val = val.get() # Handle existing vars
            
            var = ctk.BooleanVar(value=bool(val))
            self.vars[key] = var
            # Two-way binding: update bot when GUI changes
            var.trace_add('write', lambda *a, k=key, v=var: setattr(self.bot, k, v))
            # Set initial bot value to be the Var object (so bot logic can .get() it)
            setattr(self.bot, key, var)

        # Integer Variables (With Validation)
        int_keys = [
            'hp_thresh_high', 'hp_thresh_low', 'mp_thresh', 
            'min_monsters_around_spell', 'min_monsters_for_rune',
            'kill_amount', 'kill_stop_amount'
        ]
        for key in int_keys:
            val = getattr(self.bot, key, 0)
            if hasattr(val, 'get'): val = val.get()

            var = ctk.StringVar(value=str(val)) # Use String for entry validation
            self.vars[key] = var
            
            # Validation Trace
            var.trace_add('write', lambda *a, k=key, v=var: self._validate_and_set_int(k, v))
            
            # Create a separate IntVar on the bot side for logic
            bot_int_var = ctk.IntVar(value=val)
            setattr(self.bot, key, bot_int_var)

        # String Variables
        str_keys = ['party_leader', 'waypoint_folder']
        for key in str_keys:
            val = getattr(self.bot, key, "")
            if hasattr(val, 'get'): val = val.get()
            var = ctk.StringVar(value=str(val))
            self.vars[key] = var
            var.trace_add('write', lambda *a, k=key, v=var: setattr(self.bot, k, v))
            setattr(self.bot, key, var)

    def _validate_and_set_int(self, key, str_var):
        """Ensures input is numeric only"""
        val = str_var.get()
        if val == "": return # Allow empty for typing
        
        if val.isdigit():
            # Valid number, update the actual bot variable
            getattr(self.bot, key).set(int(val))
        else:
            # Invalid input (letters), revert to previous known good value
            # Or just strip non-digits
            numeric_filter = ''.join(filter(str.isdigit, val))
            str_var.set(numeric_filter)

    def apply_preset(self, vocation):
        """Loads settings based on Vocation"""
        if vocation not in PRESETS: return
        
        print(f"[GUI] Applying preset for {vocation}...")
        data = PRESETS[vocation]
        
        for key, val in data.items():
            if key in self.vars:
                self.vars[key].set(val)

    # --- UI BUILDING ---
    def _build_ui(self):
        # 1. Header
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkLabel(header, text=f"{self.char_name}", font=("Segoe UI", 20, "bold")).pack(side="left")
        ctk.CTkLabel(header, text=f" [{self.vocation.upper()}]", font=("Segoe UI", 16), text_color="gray").pack(side="left", padx=5)
        
        ctk.CTkButton(header, text="Update Vision", width=100, height=28, 
                      command=self.bot.updateAllElements).pack(side="right")

        # 2. Tabs
        self.tabs = ctk.CTkTabview(self.root)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        self.tabs.add("Combat")
        self.tabs.add("Healing")
        self.tabs.add("Cavebot")
        self.tabs.add("Map")
        self.tabs.add("Settings")

        self._build_combat_tab(self.tabs.tab("Combat"))
        self._build_healing_tab(self.tabs.tab("Healing"))
        self._build_cavebot_tab(self.tabs.tab("Cavebot"))
        self._build_map_tab(self.tabs.tab("Map"))
        self._build_settings_tab(self.tabs.tab("Settings"))

        # 3. Footer
        footer = ctk.CTkFrame(self.root, height=40)
        footer.pack(fill="x", side="bottom")
        ctk.CTkButton(footer, text="EXIT BOT", fg_color="#8B0000", hover_color="#B22222", 
                      command=self._on_close).pack(fill="both", padx=5, pady=5)

    def _create_section(self, parent, title):
        """Helper to make labeled groups"""
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(frame, text=title, font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=10, pady=(5,0))
        return frame

    def _build_combat_tab(self, parent):
        # Scrollable frame for lots of options
        scroll = ctk.CTkScrollableFrame(parent)
        scroll.pack(fill="both", expand=True)

        # General
        f_gen = self._create_section(scroll, "General Combat")
        self._switch(f_gen, "Attack Monsters (Battle List)", "attack")
        self._switch(f_gen, "Use Attack Spells", "attack_spells")
        self._switch(f_gen, "Use Utito Tempo", "use_utito")

# Runes
        f_rune = self._create_section(scroll, "Area Runes (GFB/Ava)")
        self._switch(f_rune, "Enable Area Runes", "use_area_rune")
        self._switch(f_rune, "Visualize Targeting (Debug)", "show_area_rune_target")
        # NEW ENTRY
        self._entry_row(f_rune, "Min Monsters to Rune:", "min_monsters_for_rune")

        # Spells (Add separate label for clarity)
        f_spells = self._create_section(scroll, "Instant Spells (Exevo...)")
        self._entry_row(f_spells, "Min Monsters to Cast:", "min_monsters_around_spell")
        
        # Tools
        f_tools = self._create_section(scroll, "Utility Spells")
        self._switch(f_tools, "Equip/Unequip Rings", "manage_equipment")
        
        # Vocation Specific UI tweaks
        if self.vocation == "knight":
            self._switch(f_tools, "Use Exeta Res", "res")
            self._switch(f_tools, "Use Amp Res", "amp_res")

    def _build_healing_tab(self, parent):
        f_hp = self._create_section(parent, "Health Restoration")
        self._switch(f_hp, "Enable HP Healing", "hp_heal")
        self._entry_row(f_hp, "Light Heal %:", "hp_thresh_high")
        self._entry_row(f_hp, "Heavy Heal %:", "hp_thresh_low")

        f_mp = self._create_section(parent, "Mana Restoration")
        self._switch(f_mp, "Enable Mana Potions", "mp_heal")
        self._entry_row(f_mp, "Drink Mana at %:", "mp_thresh")

    def _build_cavebot_tab(self, parent):
        f_nav = self._create_section(parent, "Navigation")
        self._switch(f_nav, "Enable Cavebot Walker", "cavebot")
        self._switch(f_nav, "Follow Party Leader", "follow_party")
        self._entry_row(f_nav, "Party Leader Name:", "party_leader")

        f_loot = self._create_section(parent, "Looting")
        self._switch(f_loot, "Loot Monsters", "manual_loot")
        self._switch(f_loot, "Loot On Spot (Right Click)", "loot_on_spot")

        f_logic = self._create_section(parent, "Stop Conditions")
        self._entry_row(f_logic, "Stop after X Kills:", "kill_stop_amount")
        self._entry_row(f_logic, "Kill Amount (Batch):", "kill_amount")

    def _build_map_tab(self, parent):
        f_ctrl = ctk.CTkFrame(parent)
        f_ctrl.pack(fill="x", padx=5, pady=5)
        
        # Legend
        l1 = ctk.CTkLabel(f_ctrl, text="■ Goal", text_color="green")
        l1.pack(side="left", padx=10)
        l2 = ctk.CTkLabel(f_ctrl, text="■ Path", text_color="red")
        l2.pack(side="left", padx=10)

        # Image Container
        self.map_label = ctk.CTkLabel(parent, text="Waiting for Map Data...")
        self.map_label.pack(fill="both", expand=True, padx=10, pady=10)

    def _build_settings_tab(self, parent):
        f_snap = self._create_section(parent, "Developer Tools")
        ctk.CTkButton(f_snap, text="Save Snapshot (Training Data)", 
                      command=self.bot.capture_training_data,
                      fg_color="#4B0082").pack(fill="x", padx=10, pady=10)

        f_pre = self._create_section(parent, "Load Preset Manual")
        
        def _manual_load(voc):
            self.apply_preset(voc)
            
        cbox = ctk.CTkComboBox(f_pre, values=list(PRESETS.keys()), command=_manual_load)
        cbox.set(self.vocation)
        cbox.pack(padx=10, pady=10)

    # --- WIDGET HELPERS ---
    def _switch(self, parent, text, var_key):
        s = ctk.CTkSwitch(parent, text=text, variable=self.vars[var_key])
        s.pack(anchor="w", padx=10, pady=5)
        return s

    def _entry_row(self, parent, text, var_key):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f, text=text, width=150, anchor="w").pack(side="left")
        e = ctk.CTkEntry(f, textvariable=self.vars[var_key], width=80)
        e.pack(side="right")
        return e

    # --- LOGIC ---
    def _update_map_loop(self):
        """Safely updates the map image without blocking"""
        if self.bot.loop and hasattr(self.bot, "current_map_image"):
            if self.bot.current_map_image is not None:
                # Convert CV2 (BGR) to PIL (RGB)
                cv_img = cv2.cvtColor(self.bot.current_map_image, cv2.COLOR_BGR2RGB)
                img_pil = Image.fromarray(cv_img)
                
                # Resize to fit frame (simple aspect fill)
                h = self.map_label.winfo_height() or 300
                w = self.map_label.winfo_width() or 300
                img_pil = img_pil.resize((w, h), Image.Resampling.NEAREST)
                
                ctk_img = ctk.CTkImage(light_image=img_pil, dark_image=img_pil, size=(w, h))
                self.map_label.configure(image=ctk_img, text="")
        
        self.root.after(200, self._update_map_loop)

    def _on_close(self):
        self.bot.loop.set(False)
        self.root.destroy()
        exit()

    def loop(self):
        """Called by main.py loop"""
        self.root.update()