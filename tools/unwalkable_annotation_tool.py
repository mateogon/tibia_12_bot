import glob
import json
import os
import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageTk


DATA_FOLDER = os.path.join("training_data", "unwalkable_samples")
GRID_ROWS = 11
GRID_COLS = 15


class UnwalkableAnnotationTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Unwalkable Tile Annotation Tool")
        self.root.geometry("1250x800")

        self.file_list = []
        self.current_index = 0
        self.current_data = {}

        self.minimap_image = None
        self.minimap_local_image = None
        self.game_image = None
        self.tk_minimap = None
        self.tk_game = None
        self.minimap_disp_size = (0, 0)
        self.game_disp_size = (0, 0)

        self.painting = False
        self.paint_mode = "unw"  # 'unw' or 'erase'

        self.labels_unw = set()  # {(r, c)}
        self.labels_tp = set()   # kept for metadata roundtrip

        self.load_file_list()
        self.setup_ui()

        if self.file_list:
            self.load_current_file()
        else:
            messagebox.showinfo("Info", f"No samples found in '{DATA_FOLDER}'.")

    def load_file_list(self):
        pattern = os.path.join(os.getcwd(), DATA_FOLDER, "*.json")
        self.file_list = sorted(glob.glob(pattern))
        print(f"[UNW TOOL] Found {len(self.file_list)} samples")

    def setup_ui(self):
        toolbar = tk.Frame(self.root, bd=1, relief=tk.RAISED)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        self.lbl_status = tk.Label(toolbar, text="No Data")
        self.lbl_status.pack(side=tk.LEFT, padx=6)

        self.lbl_mode = tk.Label(toolbar, text="L-Click paint | R-Click delete", fg="#D2691E")
        self.lbl_mode.pack(side=tk.LEFT, padx=12)

        tk.Button(toolbar, text="Prev (<-)", command=self.prev_image).pack(side=tk.RIGHT, padx=4)
        tk.Button(toolbar, text="Next (->)", command=self.next_image).pack(side=tk.RIGHT, padx=4)
        tk.Button(toolbar, text="Save (S)", command=self.save_current_data).pack(side=tk.RIGHT, padx=8)

        help_text = (
            "L-Click/Drag: Paint | R-Click/Drag: Delete | C: Clear | "
            "A: Reset to Auto | I/J/K/L: Align | S: Save | Arrows: Prev/Next"
        )
        tk.Label(self.root, text=help_text, bg="#e5e5e5").pack(side=tk.BOTTOM, fill=tk.X)

        body = tk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True)

        left = tk.Frame(body)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=8, pady=8)
        tk.Label(left, text="Minimap + 15x11 Grid", font=("Segoe UI", 11, "bold")).pack(anchor="w")

        self.canvas = tk.Canvas(left, bg="#222", width=420, height=420, cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=False)

        right = tk.Frame(body)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)
        tk.Label(right, text="Game Screen (context)", font=("Segoe UI", 11, "bold")).pack(anchor="w")

        self.game_canvas = tk.Canvas(right, bg="#111")
        self.game_canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<Button-1>", self.on_left_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", self.on_right_click)
        self.canvas.bind("<B3-Motion>", self.on_right_drag)
        self.canvas.bind("<ButtonRelease-3>", self.on_release)
        self.game_canvas.bind("<Button-1>", self.on_game_left_click)
        self.game_canvas.bind("<B1-Motion>", self.on_game_drag)
        self.game_canvas.bind("<ButtonRelease-1>", self.on_release)
        self.game_canvas.bind("<Button-3>", self.on_game_right_click)
        self.game_canvas.bind("<B3-Motion>", self.on_game_right_drag)
        self.game_canvas.bind("<ButtonRelease-3>", self.on_release)

        self.root.bind("<Right>", lambda e: self.next_image())
        self.root.bind("<Left>", lambda e: self.prev_image())
        self.root.bind("s", lambda e: self.save_current_data())
        self.root.bind("c", lambda e: self.clear_labels())
        self.root.bind("a", lambda e: self.reset_to_auto())
        self.root.bind("i", lambda e: self.nudge_align(0, -1))
        self.root.bind("k", lambda e: self.nudge_align(0, 1))
        self.root.bind("j", lambda e: self.nudge_align(-1, 0))
        self.root.bind("l", lambda e: self.nudge_align(1, 0))

    def load_current_file(self):
        if not self.file_list:
            return

        path = self.file_list[self.current_index]
        with open(path, "r", encoding="utf-8") as f:
            self.current_data = json.load(f)

        files = self.current_data.get("files", {})
        map_file = files.get("minimap", "")
        game_file = files.get("game_screen", "")

        map_path = os.path.join(os.getcwd(), DATA_FOLDER, map_file)
        game_path = os.path.join(os.getcwd(), DATA_FOLDER, game_file)
        if not os.path.exists(map_path):
            messagebox.showerror("Error", f"Minimap image missing:\n{map_path}")
            return

        self.minimap_image = Image.open(map_path).convert("RGB")
        self.game_image = Image.open(game_path).convert("RGB") if os.path.exists(game_path) else None
        self.minimap_local_image = self._build_local_minimap_view(self.minimap_image, self.current_data)

        labels = self.current_data.get("labels", {})
        if labels and isinstance(labels, dict):
            raw_unw = labels.get("unwalkable", [])
            raw_tp = labels.get("tp", [])
        else:
            raw_unw = (self.current_data.get("auto", {}) or {}).get("unwalkable", [])
            raw_tp = (self.current_data.get("auto", {}) or {}).get("tp", [])

        self.labels_unw = self._pairs_to_set(raw_unw)
        self.labels_tp = self._pairs_to_set(raw_tp)

        self.redraw()
        self.update_status()

    def _build_local_minimap_view(self, full_map_img, meta):
        """
        Build the exact local 15x11 minimap window used by runtime collision sampling.
        """
        w, h = full_map_img.size
        zoom = int(meta.get("zoom_level") or meta.get("map_scale") or 2)
        zoom = max(1, zoom)
        auto = meta.get("auto", {}) or {}
        anchor_dx = int(auto.get("anchor_dx", 0))
        anchor_dy = int(auto.get("anchor_dy", 0))

        cx = (w // 2) + anchor_dx
        cy = (h // 2) + anchor_dy

        tile_w = zoom
        tile_h = zoom
        out_w = GRID_COLS * tile_w
        out_h = GRID_ROWS * tile_h
        align = meta.get("tool_align", {}) if isinstance(meta.get("tool_align", {}), dict) else {}
        off_x = int(align.get("offset_x", 0))
        off_y = int(align.get("offset_y", 0))
        zoom_row_shift = zoom if zoom <= 2 else 0
        x0 = int(round(cx - (7 * tile_w) + off_x))
        y0 = int(round(cy - (5 * tile_h) + off_y + zoom_row_shift))
        x1 = x0 + out_w
        y1 = y0 + out_h

        # Clamp+paste into fixed-size canvas so grid always maps to 15x11.
        out = Image.new("RGB", (out_w, out_h), (0, 0, 0))
        sx0 = max(0, x0)
        sy0 = max(0, y0)
        sx1 = min(w, x1)
        sy1 = min(h, y1)
        if sx1 > sx0 and sy1 > sy0:
            crop = full_map_img.crop((sx0, sy0, sx1, sy1))
            dx = sx0 - x0
            dy = sy0 - y0
            out.paste(crop, (dx, dy))
        return out

    def _pairs_to_set(self, pairs):
        out = set()
        for p in pairs or []:
            if not isinstance(p, (list, tuple)) or len(p) != 2:
                continue
            r, c = int(p[0]), int(p[1])
            if 0 <= r < GRID_ROWS and 0 <= c < GRID_COLS:
                out.add((r, c))
        return out

    def _set_to_pairs(self, s):
        return sorted([[int(r), int(c)] for (r, c) in s])

    def redraw(self):
        self.canvas.delete("all")
        self.game_canvas.delete("all")

        if self.minimap_local_image is not None:
            w, h = self.minimap_local_image.size
            scale = max(1, int(min(420 / max(1, w), 420 / max(1, h))))
            disp_w = w * scale
            disp_h = h * scale
            self.minimap_disp_size = (disp_w, disp_h)
            disp = self.minimap_local_image.resize((disp_w, disp_h), Image.Resampling.NEAREST)
            self.tk_minimap = ImageTk.PhotoImage(disp)
            self.canvas.create_image(0, 0, image=self.tk_minimap, anchor=tk.NW)

            tile_w = disp_w / GRID_COLS
            tile_h = disp_h / GRID_ROWS

            for r in range(GRID_ROWS):
                for c in range(GRID_COLS):
                    x1 = c * tile_w
                    y1 = r * tile_h
                    x2 = (c + 1) * tile_w
                    y2 = (r + 1) * tile_h

                    if (r, c) in self.labels_unw:
                        self.canvas.create_rectangle(x1, y1, x2, y2, fill="#d2691e", stipple="gray50", outline="")
                    elif (r, c) in self.labels_tp:
                        self.canvas.create_rectangle(x1, y1, x2, y2, fill="#2d8f2d", stipple="gray50", outline="")

                    self.canvas.create_rectangle(x1, y1, x2, y2, outline="#00b7ff", width=1)

            self.canvas.config(scrollregion=self.canvas.bbox(tk.ALL))

        if self.game_image is not None:
            gw, gh = self.game_image.size
            max_w = max(250, self.game_canvas.winfo_width() or 700)
            max_h = max(250, self.game_canvas.winfo_height() or 700)
            scale = min(max_w / max(1, gw), max_h / max(1, gh))
            scale = max(0.3, scale)
            dw, dh = int(gw * scale), int(gh * scale)
            self.game_disp_size = (dw, dh)
            disp = self.game_image.resize((dw, dh), Image.Resampling.NEAREST)
            self.tk_game = ImageTk.PhotoImage(disp)
            self.game_canvas.create_image(0, 0, image=self.tk_game, anchor=tk.NW)
            # Draw 15x11 tile grid over game screen for spatial reference.
            step_x = dw / GRID_COLS
            step_y = dh / GRID_ROWS
            for r in range(GRID_ROWS):
                for c in range(GRID_COLS):
                    x1 = c * step_x
                    y1 = r * step_y
                    x2 = (c + 1) * step_x
                    y2 = (r + 1) * step_y
                    if (r, c) in self.labels_unw:
                        self.game_canvas.create_rectangle(x1, y1, x2, y2, fill="#d2691e", stipple="gray50", outline="")
                    elif (r, c) in self.labels_tp:
                        self.game_canvas.create_rectangle(x1, y1, x2, y2, fill="#2d8f2d", stipple="gray50", outline="")
            for i in range(1, GRID_COLS):
                x = i * step_x
                self.game_canvas.create_line(x, 0, x, dh, fill="#44cfff", dash=(2, 4), width=1)
            for i in range(1, GRID_ROWS):
                y = i * step_y
                self.game_canvas.create_line(0, y, dw, y, fill="#44cfff", dash=(2, 4), width=1)
            self.game_canvas.config(scrollregion=self.game_canvas.bbox(tk.ALL))

    def update_status(self):
        if not self.file_list:
            self.lbl_status.config(text="No Data")
            return
        name = os.path.basename(self.file_list[self.current_index])
        auto_unw = len((self.current_data.get("auto", {}) or {}).get("unwalkable", []))
        zoom = int(self.current_data.get("zoom_level") or self.current_data.get("map_scale") or 0)
        align = self.current_data.get("tool_align", {}) if isinstance(self.current_data.get("tool_align", {}), dict) else {}
        ax = int(align.get("offset_x", 0))
        ay = int(align.get("offset_y", 0))
        self.lbl_status.config(
            text=(
                f"File: {name} ({self.current_index+1}/{len(self.file_list)}) | "
                f"Zoom={zoom}x | Align=({ax},{ay}) | Labels unwalkable={len(self.labels_unw)} | Auto={auto_unw}"
            )
        )

    def set_mode(self, mode):
        self.paint_mode = mode
        if mode == "unw":
            self.lbl_mode.config(text="L-Click paint | R-Click delete", fg="#D2691E")
        else:
            self.lbl_mode.config(text="L-Click paint | R-Click delete", fg="#B22222")

    def _event_to_cell(self, event):
        if self.minimap_local_image is None:
            return None
        disp_w, disp_h = self.minimap_disp_size
        if disp_w <= 0 or disp_h <= 0:
            return None
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        if x < 0 or y < 0 or x >= disp_w or y >= disp_h:
            return None
        c = int(x / (disp_w / GRID_COLS))
        r = int(y / (disp_h / GRID_ROWS))
        if not (0 <= r < GRID_ROWS and 0 <= c < GRID_COLS):
            return None
        return r, c

    def _game_event_to_cell(self, event):
        disp_w, disp_h = self.game_disp_size
        if disp_w <= 0 or disp_h <= 0:
            return None
        x = self.game_canvas.canvasx(event.x)
        y = self.game_canvas.canvasy(event.y)
        if x < 0 or y < 0 or x >= disp_w or y >= disp_h:
            return None
        c = int(x / (disp_w / GRID_COLS))
        r = int(y / (disp_h / GRID_ROWS))
        if not (0 <= r < GRID_ROWS and 0 <= c < GRID_COLS):
            return None
        return r, c

    def _apply_cell(self, rc):
        if rc is None:
            return
        r, c = rc
        if self.paint_mode == "unw":
            self.labels_unw.add((r, c))
            if (r, c) in self.labels_tp:
                self.labels_tp.remove((r, c))
        else:
            self.labels_unw.discard((r, c))

    def on_left_click(self, event):
        self.set_mode("unw")
        self.painting = True
        self._apply_cell(self._event_to_cell(event))
        self.redraw()
        self.update_status()

    def on_drag(self, event):
        if not self.painting:
            return
        self._apply_cell(self._event_to_cell(event))
        self.redraw()
        self.update_status()

    def on_release(self, event):
        self.painting = False

    def on_right_click(self, event):
        self.set_mode("erase")
        self.painting = True
        self._apply_cell(self._event_to_cell(event))
        self.redraw()
        self.update_status()

    def on_right_drag(self, event):
        if not self.painting:
            return
        self.set_mode("erase")
        self._apply_cell(self._event_to_cell(event))
        self.redraw()
        self.update_status()

    def on_game_left_click(self, event):
        self.set_mode("unw")
        self.painting = True
        self._apply_cell(self._game_event_to_cell(event))
        self.redraw()
        self.update_status()

    def on_game_drag(self, event):
        if not self.painting:
            return
        self._apply_cell(self._game_event_to_cell(event))
        self.redraw()
        self.update_status()

    def on_game_right_click(self, event):
        self.set_mode("erase")
        self.painting = True
        self._apply_cell(self._game_event_to_cell(event))
        self.redraw()
        self.update_status()

    def on_game_right_drag(self, event):
        if not self.painting:
            return
        self.set_mode("erase")
        self._apply_cell(self._game_event_to_cell(event))
        self.redraw()
        self.update_status()

    def clear_labels(self):
        self.labels_unw.clear()
        self.redraw()
        self.update_status()

    def reset_to_auto(self):
        auto = (self.current_data.get("auto", {}) or {}).get("unwalkable", [])
        self.labels_unw = self._pairs_to_set(auto)
        self.redraw()
        self.update_status()

    def nudge_align(self, dx, dy):
        align = self.current_data.setdefault("tool_align", {})
        align["offset_x"] = int(align.get("offset_x", 0)) + int(dx)
        align["offset_y"] = int(align.get("offset_y", 0)) + int(dy)
        if self.minimap_image is not None:
            self.minimap_local_image = self._build_local_minimap_view(self.minimap_image, self.current_data)
        self.redraw()
        self.update_status()

    def save_current_data(self):
        if not self.file_list:
            return
        path = self.file_list[self.current_index]
        labels = self.current_data.setdefault("labels", {})
        labels["unwalkable"] = self._set_to_pairs(self.labels_unw)
        labels["tp"] = self._set_to_pairs(self.labels_tp)
        labels["version"] = 1
        align = self.current_data.setdefault("tool_align", {})
        align["offset_x"] = int(align.get("offset_x", 0))
        align["offset_y"] = int(align.get("offset_y", 0))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.current_data, f, indent=2, ensure_ascii=True)
        print(f"[UNW TOOL] Saved {os.path.basename(path)}")

    def next_image(self):
        self.save_current_data()
        if self.current_index < len(self.file_list) - 1:
            self.current_index += 1
            self.load_current_file()

    def prev_image(self):
        self.save_current_data()
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_file()


if __name__ == "__main__":
    root = tk.Tk()
    app = UnwalkableAnnotationTool(root)
    root.mainloop()
