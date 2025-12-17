import json
import os

CONFIG_FILE = "bot_config.json"

# Your exact configuration structure
DEFAULT_CONFIG = {
    "last_character": "Mateo Gon",
    "characters": {
        "Mateogon": {"vocation": "sorcerer", "spell_area": 6},
        "Mateo Gon": {"vocation": "knight", "spell_area": 3},
        "Thyrion": {"vocation": "paladin", "spell_area": 5},
        "Zane": {"vocation": "sorcerer", "spell_area": 3},
        "Helios": {"vocation": "paladin", "spell_area": 6},
        "Kaz": {"vocation": "druid", "spell_area": 6},
        "Master": {"vocation": "druid", "spell_area": 6}
    },
    "presets": {
        "knight": {
            "slots": {
                "heal_high": 0, "heal_low": 1, "mana": 2, 
                "utito": 15, "exeta": 9, "amp_res": 14, 
                "haste": 10, "food": 12, 
                "ring": 20, "amulet": 19, 
                "weapon": 17, "helmet": 16, "armor": 18, "shield": 21
            },
            "spells": {"area_slots": [3, 4, 5], "target_slots": [6, 7]},
            "settings": {
                "hp_thresh_high": 90, "hp_thresh_low": 60, "mp_thresh": 10,
                "attack_spells": True, "res": True, "amp_res": False, 
                "use_utito": True, "use_area_rune": False,
                "min_monsters_spell": 2, "min_monsters_rune": 1
            }
        },
        "druid": {
            "slots": {
                "heal_high": 0, "heal_low": 1, "mana": 2, 
                "sio": 13, "haste": 10, "food": 12, "area_rune": 8, 
                "magic_shield": 15, "cancel_magic_shield": 31, 
                "ring": 20, "amulet": 19
            },
            "spells": {"area_slots": [3, 4], "target_slots": [6, 7]},
            "settings": {
                "hp_thresh_high": 95, "hp_thresh_low": 75, "mp_thresh": 50,
                "attack_spells": True, "res": False, "amp_res": False, 
                "use_utito": False, "use_area_rune": True,
                "min_monsters_spell": 1, "min_monsters_rune": 2
            }
        },
        "sorcerer": {
            "slots": {
                "heal_high": 0, "heal_low": 1, "mana": 2, 
                "haste": 10, "food": 12, "area_rune": 8, 
                "magic_shield": 15, "cancel_magic_shield": 31, 
                "ring": 20, "amulet": 19
            },
            "spells": {"area_slots": [3, 4], "target_slots": [6, 7]},
            "settings": {
                "hp_thresh_high": 95, "hp_thresh_low": 70, "mp_thresh": 50,
                "attack_spells": True, "res": False, "amp_res": False, 
                "use_utito": False, "use_area_rune": True,
                "min_monsters_spell": 1, "min_monsters_rune": 2
            }
        },
        "paladin": {
            "slots": {
                "heal_high": 0, "heal_low": 1, "mana": 2, 
                "haste": 10, "food": 12, "area_rune": 8, 
                "magic_shield": 15, "cancel_magic_shield": 31, 
                "ring": 20, "amulet": 19
            },
            "spells": {"area_slots": [3, 4], "target_slots": [6, 7]},
            "settings": {
                "hp_thresh_high": 92, "hp_thresh_low": 65, "mp_thresh": 40,
                "attack_spells": True, "res": False, "amp_res": False, 
                "use_utito": True, "use_area_rune": True,
                "min_monsters_spell": 3, "min_monsters_rune": 1
            }
        }
    }
}

class ConfigManager:
    def __init__(self):
        self.data = self._load_config()

    def _load_config(self):
        if not os.path.exists(CONFIG_FILE):
            print("[CONFIG] Creating new config file from defaults...")
            self._save_to_file(DEFAULT_CONFIG)
            return DEFAULT_CONFIG
        
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                # Simple merge to ensure new keys exist if file is old
                for voc, preset in DEFAULT_CONFIG["presets"].items():
                    if voc not in data["presets"]:
                        data["presets"][voc] = preset
                return data
        except Exception as e:
            print(f"[CONFIG] Error loading config: {e}. Using defaults.")
            return DEFAULT_CONFIG

    def _save_to_file(self, data):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=4)

    def save(self):
        self._save_to_file(self.data)

    def get_character(self, name):
        return self.data["characters"].get(name, {"vocation": "knight", "spell_area": 3})

    def get_preset(self, vocation):
        return self.data["presets"].get(vocation.lower(), self.data["presets"]["knight"])