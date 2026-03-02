"""Main runtime loop orchestration for the bot."""

from __future__ import annotations

import time

from .perf import PerfTracker


class BotRunner:
    """Runs one bot instance loop and its periodic orchestration."""

    def __init__(self, bot) -> None:
        self.bot = bot
        self.count = 0
        self.start_time = time.time()
        self.perf_last_bg_seq = -1
        self.last_slot_status_second = -1
        self.perf = PerfTracker(should_print_fn=self._should_print_perf)

    def _should_print_perf(self):
        try:
            return bool(self.bot._is_log_enabled("perf"))
        except Exception:
            return False

    def _ingest_bg_metrics(self) -> None:
        bg_seq = getattr(self.bot.bg, "metrics_seq", -1)
        if bg_seq == self.perf_last_bg_seq:
            return

        self.perf_last_bg_seq = bg_seq
        bgm = getattr(self.bot.bg, "last_metrics", None)
        if not bgm:
            return

        self.perf.add_value_ms("bg_capture", float(bgm.get("capture_ms", 0.0)))
        self.perf.add_value_ms("bg_crop_convert", float(bgm.get("crop_convert_ms", 0.0)))
        if bgm.get("throttled", False):
            self.perf.add_value_ms("bg_throttled_frames", 1.0)

    def _periodic_actionbar_and_loot(self) -> None:
        current_time = int(time.time() - self.start_time)
        if current_time % 10 != 0 or current_time == self.last_slot_status_second:
            return

        self.last_slot_status_second = current_time
        t0 = time.perf_counter(); self.bot.updateActionbarSlotStatus(); self.perf.add_span("slot_status_update", t0)
        if self.bot.loot_on_spot.get():
            t0 = time.perf_counter(); self.bot.lootAround(True); self.perf.add_span("loot_on_spot", t0)

    def _update_minimap_scale(self) -> None:
        if self.count % 30 != 0:
            return

        from src.bot.vision import image as img

        t0 = time.perf_counter()
        map_img = img.screengrab_array(self.bot.hwnd, self.bot.s_Map.region)
        self.bot.map_scale = self.bot.detect_minimap_scale(map_img)
        self.perf.add_span("scale_detect", t0)

    def _update_monsters(self) -> None:
        t0 = time.perf_counter(); battle_count = self.bot.monsterCount(); self.perf.add_span("monster_count", t0)
        self.bot.monster_count_battlelist = int(battle_count)

        # Always refresh on-screen detections; battle-list color scan can miss on some clients.
        t0 = time.perf_counter()
        self.bot.updateMonsterPositions()
        self.bot.monster_positions = self.bot.get_filtered_monsters()
        self.perf.add_span("monster_positions", t0)

        screen_count = len(self.bot.monster_positions)
        self.bot.monster_count = max(int(battle_count), int(screen_count))

    def _update_collision_map_if_needed(self) -> None:
        need_collision = (
            self.bot.cavebot.get()
            or self.bot.use_area_rune.get()
            or self.bot.use_recenter.get()
            or self.bot.use_kiting.get()
            or self.bot._bool_value(self.bot.amp_res)
        )
        if not need_collision:
            return

        cadence = 1 if self.bot.monster_count > 0 else 2
        if (self.count % cadence != 0) and (self.bot.collision_grid is not None):
            return

        t0 = time.perf_counter(); self.bot.collision_grid, _ = self.bot.get_local_collision_map(); self.perf.add_span("collision_map", t0)

    def _run_actions(self) -> None:
        if self.bot.attack.get():
            t0 = time.perf_counter(); self.bot.clickAttack(); self.perf.add_span("attack_click", t0)

        if self.bot.cavebot.get():
            if self.bot.use_static_lure.get():
                t0 = time.perf_counter(); self.bot.execute_static_party_lure(); self.perf.add_span("cavebot_static_lure", t0)
            else:
                t0 = time.perf_counter(); self.bot.cavebottest(); self.perf.add_span("cavebot_main", t0)

        if self.bot.hp_heal.get():
            t0 = time.perf_counter(); self.bot.manageHealth(); self.perf.add_span("heal_hp", t0)
            t0 = time.perf_counter(); self.bot.manageMagicShield(); self.perf.add_span("magic_shield", t0)
        if self.bot.mp_heal.get():
            t0 = time.perf_counter(); self.bot.manageMana(); self.perf.add_span("heal_mp", t0)

        t0 = time.perf_counter(); self.bot.manageKnightSupport(); self.perf.add_span("knight_support", t0)

        if self.bot.attack_spells.get():
            t0 = time.perf_counter(); did_aoe = self.bot.attackAreaSpells(); self.perf.add_span("spells_area", t0)
            did_rune = False
            if not did_aoe and self.bot.use_area_rune.get():
                t0 = time.perf_counter(); did_rune = self.bot.useAreaRune(); self.perf.add_span("spells_area_rune", t0)
            if not did_aoe and not did_rune:
                t0 = time.perf_counter(); self.bot.attackTargetSpells(); self.perf.add_span("spells_target", t0)

        if self.bot._bool_value(self.bot.use_haste):
            t0 = time.perf_counter(); self.bot.haste(); self.perf.add_span("haste", t0)
        if self.bot._bool_value(self.bot.use_food):
            t0 = time.perf_counter(); self.bot.eat(); self.perf.add_span("food", t0)
        if self.bot.manage_equipment.get():
            t0 = time.perf_counter(); self.bot.manageEquipment(); self.perf.add_span("equipment", t0)

        if self.bot.character_name != self.bot.party_leader.get() and self.bot.follow_party.get():
            t0 = time.perf_counter(); self.bot.manageFollow(); self.perf.add_span("follow_party", t0)
            if self.count % 300 == 0:
                t0 = time.perf_counter(); self.bot.getPartyList(); self.perf.add_span("party_scan", t0)

        if self.bot.use_area_rune.get() and self.bot.vocation != "knight":
            t0 = time.perf_counter(); self.bot.useAreaRune(); self.perf.add_span("extra_area_rune", t0)
        if len(self.bot.party.keys()) > 0:
            t0 = time.perf_counter(); self.bot.healParty(); self.perf.add_span("heal_party", t0)

    def _visualize(self) -> None:
        if self.bot._bool_value(self.bot.show_area_rune_target) and self.count % 3 == 0:
            t0 = time.perf_counter(); self.bot.visualize_monster_grid(self.bot.collision_grid, self.bot.map_scale); self.perf.add_span("visualize", t0)

    def run(self):
        self.bot.updateFrame()
        self.bot.updateAllElements()
        self.bot.updateActionbarSlotStatus()

        try:
            while True:
                frame_t0 = time.perf_counter()
                if not self.bot.loop.get():
                    break

                t0 = time.perf_counter(); self.bot.GUI.loop(); self.perf.add_span("gui_loop", t0)
                t0 = time.perf_counter(); self.bot.updateFrame(); self.perf.add_span("update_frame", t0)

                self._ingest_bg_metrics()

                t0 = time.perf_counter(); self.bot.updateWindowCoordinates(); self.perf.add_span("window_coords", t0)
                t0 = time.perf_counter(); self.bot.manageKeysSync(); self.perf.add_span("keys_sync", t0)
                t0 = time.perf_counter(); self.bot.checkAndDetectElements(); self.perf.add_span("detect_elements", t0)
                if self.count % 2 == 0:
                    t0 = time.perf_counter(); self.bot.getBuffs(); self.perf.add_span("buff_scan", t0)
                t0 = time.perf_counter(); self.bot.manage_boss_sequences(); self.perf.add_span("boss_seq", t0)

                self._periodic_actionbar_and_loot()
                self._update_minimap_scale()
                t0 = time.perf_counter(); self.bot.record_cavebot_tick(); self.perf.add_span("cavebot_rec", t0)
                self._update_monsters()
                self._update_collision_map_if_needed()
                self._run_actions()
                self._visualize()

                self.count += 1
                self.perf.add_sample()
                self.perf.add_span("frame_total", frame_t0)
                self.perf.report_if_due(self.count)
        finally:
            self.bot.bg.stop()

        return self.bot
