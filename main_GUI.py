import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk
import cv2
import numpy as np

class ModernBotGUI:
    def __init__(self, bot, char_name, vocation):
        self.bot = bot
        self.char_name = char_name
        self.vocation = vocation

        # Theme Setup
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        # Root Window
        self.root = ctk.CTk()
        self.root.title(f"TibiaBot 2025 - {char_name} ({self.vocation.title()})")
        self.root.geometry("600x850")
        
        # Variable Storage
        self.vars = {}
        # CONTROL FLAGS
        self.running = True           # Master flag for the GUI state
        self._map_timer_id = None     # To track and cancel the map loop
        self._preview_timer = None    # To track and cancel the slot preview
        # --- FIX: Initialize Image References & Timer ---
        self.map_tk_image = None
        self.map_label = None
        self.slot_preview_label = None
        self._current_preview_image = None  # Prevents pyimage error
        self._preview_timer = None          # Prevents AttributeError


        # Start Loops
        self._update_map_loop()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    def setup_vars_and_ui(self):
        """Called by Bot after it creates its Tkinter variables"""
        self._init_variables()  # 1. Links self.vars['attack'] = bot.attack
        self._build_ui()        # 2. Creates tabs (this looks into self.vars)
        self._update_map_loop()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _init_variables(self):
        """
        Links GUI variables to the pre-existing Var objects on the Bot.
        """
        # Map bot attributes to self.vars for GUI widget use
        keys = [
            'loop', 'attack', 'attack_spells', 'hp_heal', 'mp_heal', 
            'manual_loot', 'cavebot', 'res', 'follow_party', 'use_area_rune', 
            'manage_equipment', 'loot_on_spot', 'amp_res', 'show_area_rune_target',
            'use_utito', 'use_haste', 'use_food',
            'hp_thresh_high', 'hp_thresh_low', 'mp_thresh', 
            'min_monsters_around_spell', 'min_monsters_for_rune',
            'kill_amount', 'kill_stop_amount',
            'party_leader', 'waypoint_folder',
            'use_lure_walk', 'lure_walk_ms', 'lure_stop_ms',
            'use_recenter', 'use_kiting',
        ]
        
        for key in keys:
            bot_var = getattr(self.bot, key)
            self.vars[key] = bot_var
            
            # Setup trace so the GUI updates the bot's internal profile dictionary live
            # (Matches your existing saving logic)
            def trace_callback(*args, k=key, v=bot_var):
                # Integer and string vars update s[json_key] inside save_config
                pass 
                
            bot_var.trace_add('write', trace_callback)

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
        val = str_var.get()
        if val == "": return 
        
        if val.isdigit():
            getattr(self.bot, key).set(int(val))
        else:
            numeric_filter = ''.join(filter(str.isdigit, val))
            str_var.set(numeric_filter)

    # --- UI BUILDING ---
    def _build_ui(self):
        # 1. Header
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkLabel(header, text=f"{self.char_name}", font=("Segoe UI", 20, "bold")).pack(side="left")
        ctk.CTkLabel(header, text=f" [{self.vocation.upper()}]", font=("Segoe UI", 16), text_color="gray").pack(side="left", padx=5)
        
        ctk.CTkButton(
            header,
            text="Save Config",
            width=100,
            height=28,
            command=self.save_config,
            fg_color="#006400",
            hover_color="#008000",
        ).pack(side="right", padx=(0, 8))

        ctk.CTkButton(
            header,
            text="Update Vision",
            width=100,
            height=28,
            command=self.bot.updateAllElements
        ).pack(side="right")

        # 2. Tabs
        self.tabs = ctk.CTkTabview(self.root)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        self.tabs.add("Combat")
        self.tabs.add("Healing")
        self.tabs.add("Slots") 
        self.tabs.add("Cavebot")
        self.tabs.add("Map")
        self.tabs.add("Settings")

        self._build_combat_tab(self.tabs.tab("Combat"))
        self._build_healing_tab(self.tabs.tab("Healing"))
        self._build_slots_tab(self.tabs.tab("Slots")) 
        self._build_cavebot_tab(self.tabs.tab("Cavebot"))
        self._build_map_tab(self.tabs.tab("Map"))
        self._build_settings_tab(self.tabs.tab("Settings"))

        # 3. Footer
        footer = ctk.CTkFrame(self.root, height=40)
        footer.pack(fill="x", side="bottom")
        ctk.CTkButton(footer, text="EXIT BOT", fg_color="#8B0000", hover_color="#B22222", 
                      command=self._on_close).pack(fill="both", padx=5, pady=5)

    def _create_section(self, parent, title):
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(frame, text=title, font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=10, pady=(5,0))
        return frame

    def _build_combat_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(parent)
        scroll.pack(fill="both", expand=True)

        f_gen = self._create_section(scroll, "General Combat")
        self._switch(f_gen, "Attack Monsters (Battle List)", "attack")
        self._switch(f_gen, "Use Attack Spells", "attack_spells")
        self._switch(f_gen, "Use Utito Tempo", "use_utito")

        f_rune = self._create_section(scroll, "Area Runes (GFB/Ava)")
        self._switch(f_rune, "Enable Area Runes", "use_area_rune")
        self._switch(f_rune, "Visualize Targeting (Debug)", "show_area_rune_target")
        self._entry_row(f_rune, "Min Monsters to Rune:", "min_monsters_for_rune")

        f_spells = self._create_section(scroll, "Area Spells")
        self._entry_row(f_spells, "Min Monsters to Cast:", "min_monsters_around_spell")
        
        f_tools = self._create_section(scroll, "Utility")
        self._switch(f_tools, "Use Haste", "use_haste")
        self._switch(f_tools, "Use Food", "use_food")
        self._switch(f_tools, "Equip/Unequip Equipment", "manage_equipment")

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

    def _build_slots_tab(self, parent):
        """
        New Tab to configure Action Bar IDs (0 to N)
        """
        # Container to split Left/Right
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True)

        # Left: Scrollable Inputs
        scroll = ctk.CTkScrollableFrame(container)
        scroll.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        # Right: Fixed Preview Panel
        preview_panel = ctk.CTkFrame(container, width=150)
        preview_panel.pack(side="right", fill="y", padx=5, pady=5)
        
        ctk.CTkLabel(preview_panel, text="Slot Preview", font=("Segoe UI", 12, "bold")).pack(pady=10)
        self.slot_preview_label = ctk.CTkLabel(preview_panel, text="[Click Slot ID]", width=80, height=80, fg_color="#1a1a1a")
        self.slot_preview_label.pack(padx=10, pady=5)

        ctk.CTkLabel(scroll, text="Action Bar Slots (0=F1, 1=F2...)", text_color="yellow").pack(pady=5)

        # 1. Healing
        f_heal = self._create_section(scroll, "Healing Slots")
        self._slot_entry(f_heal, "Light Heal:", "heal_high")
        self._slot_entry(f_heal, "Heavy Heal:", "heal_low")
        self._slot_entry(f_heal, "Mana Potion:", "mana")
        self._slot_entry(f_heal, "Sio (Druid):", "sio")

        # 2. Support
        f_supp = self._create_section(scroll, "Support Slots")
        self._slot_entry(f_supp, "Haste:", "haste")
        self._slot_entry(f_supp, "Food:", "food")
        self._slot_entry(f_supp, "Utito / Buff:", "utito")
        self._slot_entry(f_supp, "Exeta Res:", "exeta")
        self._slot_entry(f_supp, "Amp Res:", "amp_res")
        self._slot_entry(f_supp, "Magic Shield:", "magic_shield")
        self._slot_entry(f_supp, "Cancel Shield:", "cancel_magic_shield")
        self._slot_entry(f_supp, "Area Rune:", "area_rune")

        # 3. Equipment
        f_equip = self._create_section(scroll, "Equipment")
        self._slot_entry(f_equip, "Ring:", "ring")
        self._slot_entry(f_equip, "Amulet:", "amulet")
        self._slot_entry(f_equip, "Weapon:", "weapon")
        self._slot_entry(f_equip, "Shield:", "shield")
        self._slot_entry(f_equip, "Armor:", "armor")
        self._slot_entry(f_equip, "Helmet:", "helmet")

        # 4. Rotations (Lists)
        f_rot = self._create_section(scroll, "Attack Rotations (Comma Separated)")
        self._list_entry(f_rot, "Area Spells:", "area_spells_slots")
        self._list_entry(f_rot, "Target Spells:", "target_spells_slots")

    def _build_cavebot_tab(self, parent):
        # 1. Navigation Section
        f_nav = self._create_section(parent, "Navigation")
        
        # Row: Cavebot Switch + Reset Button
        row_frame = ctk.CTkFrame(f_nav, fg_color="transparent")
        row_frame.pack(fill="x", padx=10, pady=5)
        
        cb_switch = ctk.CTkSwitch(row_frame, text="Enable Cavebot Walker", variable=self.vars['cavebot'])
        cb_switch.pack(side="left")
        
        reset_btn = ctk.CTkButton(row_frame, text="Reset History", width=100, height=24,
                                  fg_color="#D2691E", hover_color="#A0522D", 
                                  command=self.bot.reset_marks_history)
        reset_btn.pack(side="right")

        # Follow logic (Now correctly placed inside Navigation before other sections start)
        self._switch(f_nav, "Follow Party Leader", "follow_party")
        self._entry_row(f_nav, "Party Leader Name:", "party_leader")

        # 2. Tactical Positioning Section
        f_tactics = self._create_section(parent, "Tactical Positioning")
        self._switch(f_tactics, "Recenter (Dive into Pack)", "use_recenter")
        self._switch(f_tactics, "Kite (Keep Distance)", "use_kiting")

        # 3. Lure Section
        f_lure = self._create_section(parent, "Lure / Stutter Walk")
        self._switch(f_lure, "Enable Lure Stutter", "use_lure_walk")
        self._entry_row(f_lure, "Walk Duration (ms):", "lure_walk_ms")
        self._entry_row(f_lure, "Stop Duration (ms):", "lure_stop_ms")

        # 4. Looting Section
        f_loot = self._create_section(parent, "Looting")
        self._switch(f_loot, "Loot Monsters", "manual_loot")
        self._switch(f_loot, "Loot On Spot (Right Click)", "loot_on_spot")

        # 5. Stop Conditions Section
        f_logic = self._create_section(parent, "Stop Conditions")
        self._entry_row(f_logic, "Stop when X Monsters Left:", "kill_stop_amount")
        self._entry_row(f_logic, "Kill Amount (Batch):", "kill_amount")

    def _build_map_tab(self, parent):
        f_ctrl = ctk.CTkFrame(parent)
        f_ctrl.pack(fill="x", padx=5, pady=5)
        
        l1 = ctk.CTkLabel(f_ctrl, text="■ Goal", text_color="green")
        l1.pack(side="left", padx=10)
        l2 = ctk.CTkLabel(f_ctrl, text="■ Path", text_color="red")
        l2.pack(side="left", padx=10)

        self.map_label = ctk.CTkLabel(parent, text="Waiting for Map Data...")
        self.map_label.pack(fill="both", expand=True, padx=10, pady=10)

    def _build_settings_tab(self, parent):
        f_snap = self._create_section(parent, "Developer Tools")
        ctk.CTkButton(f_snap, text="Save Snapshot (Training Data)",
                      command=self.bot.capture_training_data,
                      fg_color="#4B0082").pack(fill="x", padx=10, pady=10)

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

    def _slot_entry(self, parent, text, slot_key):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f, text=text, width=150, anchor="w").pack(side="left")
        
        curr = self.bot.slots.get(slot_key, "")
        var = ctk.StringVar(value=str(curr))
        
        def _upd(*a):
            if var.get().isdigit(): 
                self.bot.slots[slot_key] = int(var.get())
        
        var.trace_add("write", _upd)
        entry = ctk.CTkEntry(f, textvariable=var, width=50)
        entry.pack(side="right")
        
        # Debounced Preview on Click/Type
        entry.bind("<FocusIn>", lambda e: self._schedule_preview(var.get()))
        entry.bind("<KeyRelease>", lambda e: self._schedule_preview(var.get()))

    def _list_entry(self, parent, text, attr_name):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(f, text=text, width=150, anchor="w").pack(side="left")
        
        # Access the list on the bot using the EXACT name
        curr = getattr(self.bot, attr_name, [])
        str_val = ", ".join(map(str, curr))
        var = ctk.StringVar(value=str_val)
        
        def _upd(*a):
            try:
                # 1. Parse Input
                raw = var.get()
                new_list = [int(x.strip()) for x in raw.split(',') if x.strip().isdigit()]
                
                # 2. Update Runtime Bot Attribute (Immediate effect)
                setattr(self.bot, attr_name, new_list)
                
                # 3. Update JSON Profile Structure (For saving)
                # CHANGE: Use 'profile' instead of 'preset'
                if "area" in attr_name: 
                    self.bot.profile["spells"]["area_slots"] = new_list
                elif "target" in attr_name: 
                    self.bot.profile["spells"]["target_slots"] = new_list
                    
            except Exception as e:
                print(f"List update error: {e}")

        var.trace_add("write", _upd)
        entry = ctk.CTkEntry(f, textvariable=var, width=150)
        entry.pack(side="right")
        
        # Debounced Preview
        entry.bind("<FocusIn>", lambda e: self._schedule_preview(var.get()))
        entry.bind("<KeyRelease>", lambda e: self._schedule_preview(var.get()))

    # --- PREVIEW LOGIC (DEBOUNCED) ---
    def _schedule_preview(self, slot_input):
        """Cancels pending update and schedules a new one (Debouncing)"""
        if self._preview_timer:
            self.root.after_cancel(self._preview_timer)
        
        # Wait 300ms after user stops typing
        self._preview_timer = self.root.after(300, lambda: self._preview_slot(slot_input))

    def _preview_slot(self, slot_input):
        # 1. Parse Input
        ids = []
        if "," in slot_input:
            parts = slot_input.split(',')
            for p in parts:
                if p.strip().isdigit(): ids.append(int(p.strip()))
        elif slot_input.strip().isdigit():
            ids.append(int(slot_input.strip()))
            
        if not ids: 
            try:
                self.slot_preview_label.configure(text="", image=None)
            except: pass
            return

        # 2. Fetch Images
        images = []
        if hasattr(self.bot, "get_slot_image"):
            for sid in ids:
                try:
                    cv_img = self.bot.get_slot_image(sid)
                    if cv_img is not None:
                        cv_img = np.ascontiguousarray(cv_img)
                        cv_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                        pil = Image.fromarray(cv_img)
                        pil = pil.resize((68, 68), Image.Resampling.NEAREST)
                        images.append(pil)
                except Exception as e:
                    print(f"Error fetching slot {sid}: {e}")

        if not images:
            try:
                self.slot_preview_label.configure(text="[No Data]", image=None)
            except: pass
            return

        # 3. Stack Images
        w, h = 68, 68
        gap = 4
        total_h = (h * len(images)) + (gap * (len(images) - 1))
        
        combined = Image.new('RGB', (w, total_h), color=(30, 30, 30))
        y_off = 0
        for img in images:
            combined.paste(img, (0, y_off))
            y_off += h + gap

        # 4. Update Label (CRASH PROOFED)
        try:
            ctk_img = ctk.CTkImage(light_image=combined, dark_image=combined, size=(w, total_h))
            self._current_preview_image = ctk_img 
            
            if self.slot_preview_label.winfo_exists():
                self.slot_preview_label.configure(image=self._current_preview_image, text="")
                
        except Exception as e:
            # If it's the pyimage error, just ignore it silently
            if "pyimage" in str(e):
                pass 
            else:
                print(f"[GUI Warning] Preview skipped: {e}")

    # --- SAVE CONFIG ---
    def save_config(self):
        """Saves current state to JSON via ConfigManager (char + vocation key)."""

        # 1) Ensure structure exists
        self.bot.profile.setdefault("settings", {})
        self.bot.profile.setdefault("slots", {})
        self.bot.profile.setdefault("spells", {"area_slots": [], "target_slots": []})

        s = self.bot.profile["settings"]

        integer_keys = {
            "hp_thresh_high", "hp_thresh_low", "mp_thresh",
            "min_monsters_spell", "min_monsters_rune",
            "kill_amount", "kill_stop_amount",
            "lure_walk_ms", "lure_stop_ms",
        }

        # 2) Sync GUI vars -> profile["settings"]
        for key, var in self.vars.items():
            val = var.get()

            json_key = key
            if key == "min_monsters_around_spell":
                json_key = "min_monsters_spell"
            elif key == "min_monsters_for_rune":
                json_key = "min_monsters_rune"

            if isinstance(val, bool):
                s[json_key] = val
            else:
                if json_key in integer_keys:
                    s[json_key] = int(val) if str(val).isdigit() else 0
                else:
                    s[json_key] = val

        # 3) Sync runtime structures -> profile
        self.bot.profile["slots"] = dict(self.bot.slots)
        self.bot.profile["spells"]["area_slots"] = list(getattr(self.bot, "area_spells_slots", []))
        self.bot.profile["spells"]["target_slots"] = list(getattr(self.bot, "target_spells_slots", []))

        # 4) Commit to file (NEW signature: char + vocation)
        self.bot.config.update_config(self.bot.character_name, self.bot.vocation, self.bot.profile)

        print(f"[GUI] Saved configuration for {self.bot.character_name} ({self.bot.vocation}) to JSON.")


    # --- MAP LOOP ---
    def _update_map_loop(self):
        # 1. Stop immediately if we are shutting down
        if not self.running: 
            return

        # 2. Logic (Safe Check)
        if hasattr(self.bot, "current_map_image") and self.bot.current_map_image is not None:
            try:
                cv_img = cv2.cvtColor(self.bot.current_map_image, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(cv_img)
                
                # Check widget existence before asking for height/width
                if self.map_label.winfo_exists():
                    h = self.map_label.winfo_height() or 300
                    w = self.map_label.winfo_width() or 300
                    pil_img = pil_img.resize((w, h), Image.Resampling.NEAREST)
                    ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(w, h))
                    self.map_label.configure(image=ctk_img, text="")
            except Exception:
                pass # Ignore resize errors during shutdown

        # 3. Schedule next run AND save the ID
        if self.running:
            self._map_timer_id = self.root.after(200, self._update_map_loop)

    def _on_close(self):
        print("[GUI] Shutting down...")
        try:
            self.save_config()
        except:
            pass
        # 1. Stop logical loops
        self.running = False
        self.bot.loop.set(False)
        
        # 2. Cancel our own timers (Polite cleanup)
        if self._map_timer_id: 
            try: self.root.after_cancel(self._map_timer_id)
            except: pass
            
        if self._preview_timer: 
            try: self.root.after_cancel(self._preview_timer)
            except: pass
        
        # 3. Destroy the window
        try:
            self.root.destroy()
        except:
            pass

        # 4. HARD EXIT (The Fix)
        # This kills the process instantly, preventing CustomTkinter's 
        # internal animation callbacks from firing on a dead window.
        import os
        os._exit(0)

    def loop(self):
        if not self.running:
            return
        try:
            self.root.update()
        except Exception:
            # If the window is dead, stop trying
            self.running = False
            self.bot.loop.set(False)