import tkinter as tk
from tkinter import ttk, BooleanVar, StringVar, IntVar, PhotoImage
import customtkinter as ctk
import numpy as np
import cv2
from PIL import Image, ImageTk
from functools import partial
import time

class ModernBotGUI:
    def __init__(self, bot, char_name, vocation):
        self.bot = bot
        
        # Set up theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Main window setup
        self.root = ctk.CTk()
        self.root.title(f"{char_name} - {str(bot.hwnd)}")
        self.root.geometry("550x700")
        self.root.resizable(False, False)
        
        # Initialize variables from bot and override bot attributes with Tkinter variables
        self._init_variables()
        
        self.map_image_label = None  # Initialize explicitly
        self.map_tk_image = None
        
        # Create GUI layout
        self._create_header_frame(char_name, vocation)
        self._create_main_tabs()
        self._create_footer()
        
        # Debug check - add this
        print(f"After UI creation, map_image_label: {self.map_image_label}")
        
        # Setup protocol for closing
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
        
        # Update timer for map
        self.update_map_timer_id = None
        self.root.after(1000, self.start_map_updates)
    def _init_variables(self):
        """Initialize all variables from the bot object and override with Tk variables"""
        # Create a dictionary to store the traced variables
        self.traced_vars = {}
        
        # Boolean variables
        bool_variables = [
            'loop', 'attack', 'attack_spells', 'hp_heal', 'mp_heal', 
            'manual_loot', 'cavebot', 'res', 'follow_party', 'use_area_rune', 
            'manage_equipment', 'loot_on_spot', 'amp_res', 'show_area_rune_target'
        ]
        
        for var_name in bool_variables:
            current_value = getattr(self.bot, var_name)
            traced_var = BooleanVar(value=current_value)
            self.traced_vars[var_name] = traced_var
            # Override the bot attribute with the Tkinter variable
            setattr(self.bot, var_name, traced_var)
            # Trace callback simply prints the new value
            traced_var.trace_add("write", lambda *args, vn=var_name, tv=traced_var: 
                                  print(f"Updated {vn} to {tv.get()}"))
        
        # Numeric variables
        num_variables = [
            'hp_thresh_high', 'hp_thresh_low', 'mp_thresh', 
            'min_monsters_around_spell', 'kill_amount', 'kill_stop_amount'
        ]
        
        for var_name in num_variables:
            current_value = getattr(self.bot, var_name)
            traced_var = IntVar(value=current_value)
            self.traced_vars[var_name] = traced_var
            setattr(self.bot, var_name, traced_var)
            traced_var.trace_add("write", lambda *args, vn=var_name, tv=traced_var: 
                                  print(f"Updated {vn} to {tv.get()}"))
        
        # String variables
        str_variables = ['party_leader']
        for var_name in str_variables:
            current_value = getattr(self.bot, var_name)
            traced_var = StringVar(value=current_value)
            self.traced_vars[var_name] = traced_var
            setattr(self.bot, var_name, traced_var)
            traced_var.trace_add("write", lambda *args, vn=var_name, tv=traced_var: 
                                  print(f"Updated {vn} to {tv.get()}"))
    
    def _create_header_frame(self, char_name, vocation):
        """Create header with character info and status"""
        header_frame = ctk.CTkFrame(self.root)
        header_frame.pack(fill="x", padx=10, pady=10)
        
        # Character info
        char_info = ctk.CTkLabel(
            header_frame, 
            text=f"Character: {char_name} | Vocation: {vocation}",
            font=("Roboto", 16, "bold")
        )
        char_info.pack(side="left", padx=10)
        
        # Update button
        update_btn = ctk.CTkButton(
            header_frame,
            text="Update Elements",
            command=self.bot.updateAllElements,
            width=140
        )
        update_btn.pack(side="right", padx=10)
        
    def _create_main_tabs(self):
        """Create tabbed interface for different functional areas"""
        tabview = ctk.CTkTabview(self.root)
        tabview.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Add tabs
        healing_tab = tabview.add("Healing")
        combat_tab = tabview.add("Combat")
        navigation_tab = tabview.add("Navigation")
        settings_tab = tabview.add("Settings")
        
        self._setup_healing_tab(healing_tab)
        self._setup_combat_tab(combat_tab)
        self._setup_navigation_tab(navigation_tab)
        self._setup_settings_tab(settings_tab)

    def _configure_entry(self, entry_widget):
        """Helper method to configure entry widgets with proper selection behavior"""
        entry_widget.bind("<FocusIn>", lambda event: entry_widget.select_range(0, 'end'))
        entry_widget.bind("<Control-a>", lambda event: entry_widget.select_range(0, 'end'))
        return entry_widget
    
    def _setup_healing_tab(self, parent):
        """Setup healing settings"""
        # HP Healing section
        hp_frame = ctk.CTkFrame(parent)
        hp_frame.pack(fill="x", padx=20, pady=10)
        
        hp_label = ctk.CTkLabel(hp_frame, text="HP Healing", font=("Roboto", 14, "bold"))
        hp_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        
        hp_switch = ctk.CTkSwitch(hp_frame, text="Enable HP Healing", variable=self.traced_vars['hp_heal'])
        hp_switch.grid(row=1, column=0, sticky="w", padx=10, pady=5)
        
        # Light healing threshold
        light_frame = ctk.CTkFrame(hp_frame)
        light_frame.grid(row=2, column=0, sticky="w", padx=10, pady=5)
        
        light_label = ctk.CTkLabel(light_frame, text="Light Heal Threshold:")
        light_label.pack(side="left", padx=5)
        
        light_entry = ctk.CTkEntry(light_frame, width=60, textvariable=self.traced_vars['hp_thresh_high'])
        light_entry.pack(side="left")
        self._configure_entry(light_entry)
        #light_entry.configure(validate="key", validatecommand=(parent.register(self._validate_digit), "%P"))
        
        pct_label = ctk.CTkLabel(light_frame, text="%")
        pct_label.pack(side="left", padx=5)
        
        # Heavy healing threshold
        heavy_frame = ctk.CTkFrame(hp_frame)
        heavy_frame.grid(row=3, column=0, sticky="w", padx=10, pady=5)
        
        heavy_label = ctk.CTkLabel(heavy_frame, text="Heavy Heal Threshold:")
        heavy_label.pack(side="left", padx=5)
        
        heavy_entry = ctk.CTkEntry(heavy_frame, width=60, textvariable=self.traced_vars['hp_thresh_low'])
        heavy_entry.pack(side="left")
        self._configure_entry(heavy_entry)
        #heavy_entry.configure(validate="key", validatecommand=(parent.register(self._validate_digit), "%P"))
        
        pct_label = ctk.CTkLabel(heavy_frame, text="%")
        pct_label.pack(side="left", padx=5)
        
        # MP Healing section
        mp_frame = ctk.CTkFrame(parent)
        mp_frame.pack(fill="x", padx=20, pady=10)
        
        mp_label = ctk.CTkLabel(mp_frame, text="MP Healing", font=("Roboto", 14, "bold"))
        mp_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        
        mp_switch = ctk.CTkSwitch(mp_frame, text="Enable MP Healing", variable=self.traced_vars['mp_heal'])
        mp_switch.grid(row=1, column=0, sticky="w", padx=10, pady=5)
        
        mp_thresh_frame = ctk.CTkFrame(mp_frame)
        mp_thresh_frame.grid(row=2, column=0, sticky="w", padx=10, pady=5)
        
        mp_thresh_label = ctk.CTkLabel(mp_thresh_frame, text="MP Threshold:")
        mp_thresh_label.pack(side="left", padx=5)
        
        mp_thresh_entry = ctk.CTkEntry(mp_thresh_frame, width=60, textvariable=self.traced_vars['mp_thresh'])
        mp_thresh_entry.pack(side="left")
        self._configure_entry(mp_thresh_entry)
        #mp_thresh_entry.configure(validate="key", validatecommand=(parent.register(self._validate_digit), "%P"))
        
        mp_pct_label = ctk.CTkLabel(mp_thresh_frame, text="%")
        mp_pct_label.pack(side="left", padx=5)
        
    def _setup_combat_tab(self, parent):
        """Setup combat settings"""
        # Main combat switches
        main_combat_frame = ctk.CTkFrame(parent)
        main_combat_frame.pack(fill="x", padx=20, pady=10)
        
        combat_label = ctk.CTkLabel(main_combat_frame, text="Combat Controls", font=("Roboto", 14, "bold"))
        combat_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        
        attack_switch = ctk.CTkSwitch(main_combat_frame, text="Attack (Battle)", variable=self.traced_vars['attack'])
        attack_switch.grid(row=1, column=0, sticky="w", padx=10, pady=5)
        
        spell_switch = ctk.CTkSwitch(main_combat_frame, text="Attack Spells", variable=self.traced_vars['attack_spells'])
        spell_switch.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        
        area_rune_switch = ctk.CTkSwitch(main_combat_frame, text="Use Area Rune", variable=self.traced_vars['use_area_rune'])
        area_rune_switch.grid(row=2, column=0, sticky="w", padx=10, pady=5)

        area_rune_vis_switch = ctk.CTkSwitch(
            main_combat_frame,
            text="Show Rune Target",
            variable=self.traced_vars['show_area_rune_target'],
        )
        area_rune_vis_switch.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        
        res_switch = ctk.CTkSwitch(main_combat_frame, text="Exeta Res", variable=self.traced_vars['res'])
        res_switch.grid(row=3, column=1, sticky="w", padx=10, pady=5)
        
        amp_res_switch = ctk.CTkSwitch(main_combat_frame, text="Amp Res", variable=self.traced_vars['amp_res'])
        amp_res_switch.grid(row=3, column=0, sticky="w", padx=10, pady=5)
        
        # Combat parameters
        combat_params_frame = ctk.CTkFrame(parent)
        combat_params_frame.pack(fill="x", padx=20, pady=10)
        
        params_label = ctk.CTkLabel(combat_params_frame, text="Combat Parameters", font=("Roboto", 14, "bold"))
        params_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        
        # Monsters around for spell
        monsters_frame = ctk.CTkFrame(combat_params_frame)
        monsters_frame.grid(row=1, column=0, sticky="w", padx=10, pady=5, columnspan=2)
        
        monsters_label = ctk.CTkLabel(monsters_frame, text="Min. monsters for area spell:")
        monsters_label.pack(side="left", padx=5)
        
        monsters_entry = ctk.CTkEntry(monsters_frame, width=60, textvariable=self.traced_vars['min_monsters_around_spell'])
        monsters_entry.pack(side="left")
        self._configure_entry(monsters_entry)
        #monsters_entry.configure(validate="key", validatecommand=(parent.register(self._validate_digit), "%P"))
        
        # Kill amounts
        kill_frame = ctk.CTkFrame(combat_params_frame)
        kill_frame.grid(row=2, column=0, sticky="w", padx=10, pady=5)
        
        kill_label = ctk.CTkLabel(kill_frame, text="Kill amount:")
        kill_label.pack(side="left", padx=5)
        
        kill_entry = ctk.CTkEntry(kill_frame, width=60, textvariable=self.traced_vars['kill_amount']) 
        kill_entry.pack(side="left")
        self._configure_entry(kill_entry)
        #kill_entry.configure(validate="key", validatecommand=(parent.register(self._validate_digit), "%P"))
        
        # Kill stop amount
        kill_stop_frame = ctk.CTkFrame(combat_params_frame)
        kill_stop_frame.grid(row=3, column=0, sticky="w", padx=10, pady=5)
        
        kill_stop_label = ctk.CTkLabel(kill_stop_frame, text="Kill stop amount:")
        kill_stop_label.pack(side="left", padx=5)
        
        kill_stop_entry = ctk.CTkEntry(kill_stop_frame, width=60, textvariable=self.traced_vars['kill_stop_amount'])
        kill_stop_entry.pack(side="left")
        self._configure_entry(kill_stop_entry)
        #kill_stop_entry.configure(validate="key", validatecommand=(parent.register(self._validate_digit), "%P"))
        
    def _setup_navigation_tab(self, parent):
        """Setup navigation settings with map visualization"""
        # Navigation controls
        nav_frame = ctk.CTkFrame(parent)
        nav_frame.pack(fill="x", padx=20, pady=10)
        
        nav_label = ctk.CTkLabel(nav_frame, text="Navigation", font=("Roboto", 14, "bold"))
        nav_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        
        cavebot_switch = ctk.CTkSwitch(nav_frame, text="Cavebot", variable=self.traced_vars['cavebot'])
        cavebot_switch.grid(row=1, column=0, sticky="w", padx=10, pady=5)
        
        follow_switch = ctk.CTkSwitch(nav_frame, text="Follow Party", variable=self.traced_vars['follow_party'])
        follow_switch.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        
        # Party leader
        leader_frame = ctk.CTkFrame(nav_frame)
        leader_frame.grid(row=2, column=0, sticky="w", padx=10, pady=5, columnspan=2)
        
        leader_label = ctk.CTkLabel(leader_frame, text="Party leader:")
        leader_label.pack(side="left", padx=5)
        
        leader_entry = ctk.CTkEntry(leader_frame, width=160, textvariable=self.traced_vars['party_leader'])
        self._configure_entry(leader_entry)
        leader_entry.pack(side="left", padx=5)

        # Map visualization section
        map_frame = ctk.CTkFrame(parent)
        map_frame.pack(fill="both", expand=True, padx=20, pady=10)
        map_title = ctk.CTkLabel(map_frame, text="Map Visualization", font=("Roboto", 14, "bold"))
        map_title.pack(anchor="w", padx=10, pady=5)
        
        # Add compact horizontal legend for map visualization
        legend_frame = ctk.CTkFrame(map_frame)
        legend_frame.pack(fill="x", padx=10, pady=5)


        # Create a single horizontal frame with all legend items side by side
        legend_title = ctk.CTkLabel(legend_frame, text="Legend:", anchor="w")
        legend_title.pack(side="left", padx=5, pady=2)

        # Green legend item
        green_box = ctk.CTkLabel(legend_frame, text="", width=15, height=10, fg_color="green")
        green_box.pack(side="left", padx=5)
        green_text = ctk.CTkLabel(legend_frame, text="Closest mark")
        green_text.pack(side="left", padx=2)

        # Separator
        separator1 = ctk.CTkLabel(legend_frame, text="|", width=5)
        separator1.pack(side="left", padx=2)

        # Blue legend item
        blue_box = ctk.CTkLabel(legend_frame, text="", width=15, height=10, fg_color="blue")
        blue_box.pack(side="left", padx=5)
        blue_text = ctk.CTkLabel(legend_frame, text="Other marks")
        blue_text.pack(side="left", padx=2)

        # Separator
        separator2 = ctk.CTkLabel(legend_frame, text="|", width=5)
        separator2.pack(side="left", padx=2)

        # Red legend item
        red_box = ctk.CTkLabel(legend_frame, text="", width=15, height=10, fg_color="red")
        red_box.pack(side="left", padx=5)
        red_text = ctk.CTkLabel(legend_frame, text="Recently walked")
        red_text.pack(side="left", padx=2)
        
        
        # Create a placeholder for the map image
        map_container = ctk.CTkFrame(map_frame)
        map_container.pack(fill="both", expand=True, padx=10, pady=5)
        
        # VERY explicitly set self.map_image_label
        self.map_image_label = ctk.CTkLabel(map_container, text="Map will be displayed here")
        self.map_image_label.pack(fill="both", expand=True)
        
        self.root.update_idletasks()

    def _setup_settings_tab(self, parent):
        """Setup general settings"""
        # Looting section
        loot_frame = ctk.CTkFrame(parent)
        loot_frame.pack(fill="x", padx=20, pady=10)
        
        loot_label = ctk.CTkLabel(loot_frame, text="Looting", font=("Roboto", 14, "bold"))
        loot_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        
        manual_loot_switch = ctk.CTkSwitch(loot_frame, text="Manual Loot", variable=self.traced_vars['manual_loot'])
        manual_loot_switch.grid(row=1, column=0, sticky="w", padx=10, pady=5)
        
        loot_spot_switch = ctk.CTkSwitch(loot_frame, text="Loot on Spot", variable=self.traced_vars['loot_on_spot'])
        loot_spot_switch.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        
        # Test loot button
        test_button = ctk.CTkButton(
            loot_frame,
            text="Test Loot",
            command=self.bot.lootAround,
            width=120
        )
        test_button.grid(row=2, column=0, padx=10, pady=10)
        
        # Sell all button
        sell_button = ctk.CTkButton(
            loot_frame,
            text="Sell All to NPC",
            command=self.bot.sellAllNPC,
            width=120
        )
        sell_button.grid(row=2, column=1, padx=10, pady=10)
        
        # Equipment section
        equip_frame = ctk.CTkFrame(parent)
        equip_frame.pack(fill="x", padx=20, pady=10)
        
        equip_label = ctk.CTkLabel(equip_frame, text="Equipment", font=("Roboto", 14, "bold"))
        equip_label.grid(row=0, column=0, sticky="w", padx=10, pady=5)
        
        manage_equip_switch = ctk.CTkSwitch(equip_frame, text="Manage Equipment", variable=self.traced_vars['manage_equipment'])
        manage_equip_switch.grid(row=1, column=0, sticky="w", padx=10, pady=5)
        
    def _create_footer(self):
        """Create footer with exit button and status"""
        footer_frame = ctk.CTkFrame(self.root)
        footer_frame.pack(fill="x", padx=10, pady=10, side="bottom")
        
        # Status indicator (could be expanded)
        status_label = ctk.CTkLabel(footer_frame, text="Status: Ready")
        status_label.pack(side="left", padx=10)
        
        # Exit button
        exit_btn = ctk.CTkButton(
            footer_frame,
            text="Exit",
            command=self.on_exit,
            width=100,
            fg_color="#B22222",  # Dark red color
            hover_color="#8B0000"  # Darker red on hover
        )
        exit_btn.pack(side="right", padx=10)
        
    def update_map_display(self):
        try:

            # Try a different approach to check if the widget exists
            if not hasattr(self, 'map_image_label') or self.map_image_label is None:
                print("Map label is None, will retry")
                self.update_map_timer_id = self.root.after(1000, self.update_map_display)
                return
            
            # Don't use winfo_exists() which might not work properly with customtkinter
            # Instead, try a simple operation to see if the widget is functional
            try:
                # Test if we can use configure on the widget
                current_text = self.map_image_label.cget("text")
                
                # If we get here, the widget is working
                if hasattr(self.bot, 'current_map_image') and self.bot.current_map_image is not None:
                    cv_image = self.bot.current_map_image
                    pil_image = Image.fromarray(cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB))
                    display_size = (300, 300)
                    pil_image = pil_image.resize(display_size, Image.LANCZOS)
                    self.map_tk_image = ImageTk.PhotoImage(pil_image)
                    self.map_image_label.configure(image=self.map_tk_image, text="")
                else:
                    # No map image available
                    self.map_image_label.configure(text="No map data available")
            except Exception as e:
                print(f"Widget not ready: {e}")
                self.update_map_timer_id = self.root.after(1000, self.update_map_display)
                return
                
        except Exception as e:
            print(f"Error updating map: {e}")
        
        # Schedule next update
        self.update_map_timer_id = self.root.after(500, self.update_map_display)
                    
    def _validate_digit(self, value):
        return value.isdigit() and value != ""

        
    def start_map_updates(self):
        """Start periodic updates of the map display"""
        self.update_map_display()
    
    def stop_map_updates(self):
        """Stop map updates"""
        if self.update_map_timer_id:
            self.root.after_cancel(self.update_map_timer_id)
            self.update_map_timer_id = None
    
    def on_exit(self):
        """Handle application exit"""
        self.stop_map_updates()  # Stop map updates before exiting
        print("Exiting...")
        # Ensure the bot loop variable is updated appropriately
        # Here, since self.bot.loop is a Tk variable, you can call .set(False)
        self.bot.loop.set(False)
        self.root.destroy()
        raise SystemExit
    
    def loop(self):
        """Update the GUI without blocking - similar to the old implementation"""
        if self.root.winfo_exists():  # Check if window still exists
            self.root.update()
            # The update method processes all pending events and then returns,
            # allowing your bot's main loop to continue running
            return True
        return False
