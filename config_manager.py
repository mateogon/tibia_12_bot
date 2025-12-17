# config_manager.py
import json
import os
import copy

CONFIG_FILE = "bot_config.json"

# ---- GUI-CONTROLLED KEYS (schema) ----
GUI_BOOL_KEYS = [
    "loop", "attack", "attack_spells", "hp_heal", "mp_heal",
    "manual_loot", "cavebot", "res", "follow_party", "use_area_rune",
    "manage_equipment", "loot_on_spot", "amp_res", "show_area_rune_target",
    "use_utito", 'use_haste', 'use_food',
]
GUI_INT_KEYS = [
    "hp_thresh_high", "hp_thresh_low", "mp_thresh",
    "min_monsters_spell", "min_monsters_rune",
    "kill_amount", "kill_stop_amount",
]
GUI_STR_KEYS = ["party_leader", "waypoint_folder"]

# ---- BASE SCHEMA (includes every GUI-controlled key) ----
BASE_SETTINGS = {
    # bools
    "loop": True,
    "attack": True,
    "attack_spells": True,
    "hp_heal": True,
    "mp_heal": True,
    "manual_loot": False,
    "cavebot": False,
    "res": False,
    "amp_res": False,
    "follow_party": False,
    "use_area_rune": False,
    "manage_equipment": False,
    "loot_on_spot": False,
    "show_area_rune_target": True,
    "use_utito": False,
    "use_haste": True,
    "use_food": False,
    # ints
    "hp_thresh_high": 95,
    "hp_thresh_low": 75,
    "mp_thresh": 50,
    "min_monsters_spell": 1,
    "min_monsters_rune": 1,
    "kill_amount": 5,
    "kill_stop_amount": 1,

    # strings
    "party_leader": "",
    "waypoint_folder": "test",
}

# include every slot key the GUI exposes (use None if not used by a vocation)
BASE_SLOTS = {
    "heal_high": None,
    "heal_low": None,
    "mana": None,
    "sio": None,

    "haste": None,
    "food": None,
    "utito": None,
    "exeta": None,
    "amp_res": None,
    "magic_shield": None,
    "cancel_magic_shield": None,
    "area_rune": None,

    "ring": None,
    "amulet": None,
    "weapon": None,
    "shield": None,
    "armor": None,
    "helmet": None,
}

BASE_SPELLS = {
    "area_slots": [],
    "target_slots": [],
}

def _deep_merge_level1(dst: dict, src: dict) -> dict:
    """
    Merge src into dst.
    - If values are dicts, merge 1 level deep (update keys).
    - Else overwrite.
    """
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            dst[k].update(v)
        else:
            dst[k] = v
    return dst

def make_default(overrides: dict) -> dict:
    d = {
        "slots": copy.deepcopy(BASE_SLOTS),
        "spells": copy.deepcopy(BASE_SPELLS),
        "settings": copy.deepcopy(BASE_SETTINGS),
    }
    return _deep_merge_level1(d, overrides)

# ---- FACTORY DEFAULTS (read-only templates) ----
# These include the full schema because they are built on BASE_*.
DEFAULTS = {
    "knight": make_default({
        "slots": {
            "heal_high": 0, "heal_low": 1, "mana": 2,
            "utito": 15, "exeta": 9, "amp_res": 14,
            "haste": 10, "food": 12,
            "ring": 20, "amulet": 19, "weapon": 17, "helmet": 16, "armor": 18, "shield": 21,
            "area_rune": 5,
        },
        "spells": {"area_slots": [3, 4, 5], "target_slots": [6, 7]},
        "settings": {
            "hp_thresh_high": 90, "hp_thresh_low": 60, "mp_thresh": 10,
            "res": True,
            "amp_res": False,
            "use_utito": True,
            "use_haste": True,
            "use_food": True,
            "use_area_rune": False,
            "min_monsters_spell": 2, "min_monsters_rune": 1,
            "kill_amount": 5, "kill_stop_amount": 1,
        },
    }),
    "druid": make_default({
        "slots": {
            "heal_high": 0, "heal_low": 1, "mana": 2,
            "sio": 13, "haste": 10, "food": 12, "area_rune": 8,
            "magic_shield": 15, "cancel_magic_shield": 31,
            "ring": 20, "amulet": 19,
        },
        "spells": {"area_slots": [3, 4], "target_slots": [6, 7]},
        "settings": {
            "hp_thresh_high": 95, "hp_thresh_low": 75, "mp_thresh": 50,
            "res": False,
            "amp_res": False,
            "use_utito": False,
            "use_haste": True,
            "use_food": True,
            "use_area_rune": True,
            "min_monsters_spell": 1, "min_monsters_rune": 2,
            "kill_amount": 5, "kill_stop_amount": 1,
        },
    }),
    "sorcerer": make_default({
        "slots": {
            "heal_high": 0, "heal_low": 1, "mana": 2,
            "haste": 10, "food": 12, "area_rune": 8,
            "magic_shield": 15, "cancel_magic_shield": 31,
            "ring": 20, "amulet": 19,
        },
        "spells": {"area_slots": [3, 4], "target_slots": [6, 7]},
        "settings": {
            "hp_thresh_high": 95, "hp_thresh_low": 70, "mp_thresh": 50,
            "res": False,
            "amp_res": False,
            "use_utito": False,
            "use_haste": True,
            "use_food": True,
            "use_area_rune": True,
            "min_monsters_spell": 1, "min_monsters_rune": 2,
            "kill_amount": 5, "kill_stop_amount": 1,
        },
    }),
    "paladin": make_default({
        "slots": {
            "heal_high": 0, "heal_low": 1, "mana": 2,
            "haste": 10, "food": 12, "area_rune": 8,
            "magic_shield": 15, "cancel_magic_shield": 31,
            "ring": 20, "amulet": 19,
        },
        "spells": {"area_slots": [3, 4], "target_slots": [6, 7]},
        "settings": {
            "hp_thresh_high": 92, "hp_thresh_low": 65, "mp_thresh": 40,
            "res": False,
            "amp_res": False,
            "use_utito": True,
            "use_haste": True,
            "use_food": True,
            "use_area_rune": True,
            "min_monsters_spell": 3, "min_monsters_rune": 1,
            "kill_amount": 5, "kill_stop_amount": 1,
        },
    }),
}

# ---- STARTER CHARACTERS (optional; keep if you want prefilled) ----
DEFAULT_CHARACTERS = {
    "Mateogon": {"vocation": "sorcerer", "spell_area": 6},
    "Mateo Gon": {"vocation": "knight", "spell_area": 3},
    "Thyrion": {"vocation": "paladin", "spell_area": 5},
    "Zane": {"vocation": "sorcerer", "spell_area": 3},
    "Helios": {"vocation": "paladin", "spell_area": 6},
    "Kaz": {"vocation": "druid", "spell_area": 6},
    "Master": {"vocation": "druid", "spell_area": 6},
}

BASE_JSON = {
    "last_character": "",
    "characters": copy.deepcopy(DEFAULT_CHARACTERS),
    "profiles": {},
    # keep old sections if present; not required by the new system
    # "presets": {}  # (optional legacy)
}

class ConfigManager:
    def __init__(self):
        self.data = self._load_config()

    # ---------- IO ----------
    def _save_to_file(self, data: dict):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def save(self):
        self._save_to_file(self.data)

    def _load_config(self) -> dict:
        if not os.path.exists(CONFIG_FILE):
            self._save_to_file(copy.deepcopy(BASE_JSON))
            return copy.deepcopy(BASE_JSON)

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = copy.deepcopy(BASE_JSON)

        # ensure required top-level structure
        if not isinstance(data, dict):
            data = copy.deepcopy(BASE_JSON)

        data.setdefault("last_character", "")
        data.setdefault("characters", copy.deepcopy(DEFAULT_CHARACTERS))
        data.setdefault("profiles", {})

        # do not delete legacy keys (presets, etc). just keep them.
        return data

    # ---------- helpers ----------
    def _profile_key(self, char_name: str, vocation: str) -> str:
        n = (char_name or "").strip()
        v = (vocation or "").strip().lower()
        return f"{n}::{v}"

    def _ensure_profile_schema(self, profile: dict, vocation: str) -> dict:
        """
        Fill missing keys without overwriting existing values.
        Uses vocation defaults which are built on BASE schema, so it fills every GUI key.
        """
        voc = (vocation or "knight").lower()
        base = DEFAULTS.get(voc, DEFAULTS["knight"])

        if not isinstance(profile, dict):
            profile = {}

        profile.setdefault("slots", {})
        profile.setdefault("spells", {})
        profile.setdefault("settings", {})

        # fill slots
        for k, v in base["slots"].items():
            profile["slots"].setdefault(k, v)

        # fill spells
        for k, v in base["spells"].items():
            if k not in profile["spells"]:
                profile["spells"][k] = copy.deepcopy(v)

        # fill settings
        for k, v in base["settings"].items():
            profile["settings"].setdefault(k, v)

        return profile

    # ---------- public API ----------
    def get_character_info(self, name: str) -> dict:
        return self.data.get("characters", {}).get(
            name, {"vocation": "knight", "spell_area": 3}
        )

    # backward-compat alias if older code still calls get_character()
    def get_character(self, name: str) -> dict:
        return self.get_character_info(name)

    def get_config(self, char_name: str, vocation: str) -> dict:
        """
        Returns profile for (char_name + vocation).
        If missing, creates it from DEFAULTS[vocation].
        Also migrates old profiles keyed only by char_name.
        Also fills any missing keys (schema repair).
        """
        profiles = self.data.setdefault("profiles", {})

        key = self._profile_key(char_name, vocation)
        old_key = (char_name or "").strip()

        # migration: old "profiles[char_name]" -> "profiles[char_name::vocation]"
        if old_key and old_key in profiles and key not in profiles:
            profiles[key] = profiles.pop(old_key)

        if key not in profiles:
            voc = (vocation or "knight").lower()
            template = DEFAULTS.get(voc, DEFAULTS["knight"])
            profiles[key] = copy.deepcopy(template)

        # schema repair (fills missing keys; no overwrite)
        profiles[key] = self._ensure_profile_schema(profiles[key], vocation)

        # persist any migration / schema fill immediately
        self.save()
        return profiles[key]

    def update_config(self, char_name: str, vocation: str, new_config_data: dict):
        """
        Saves profile for (char_name + vocation).
        Also schema-repairs before writing.
        """
        profiles = self.data.setdefault("profiles", {})
        key = self._profile_key(char_name, vocation)

        profiles[key] = self._ensure_profile_schema(new_config_data, vocation)
        self.save()
