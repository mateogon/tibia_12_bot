import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import json
import os
import glob

# Configuration
DATA_FOLDER = "training_data"
DOT_RADIUS = 5
DOT_COLOR = "#00FF00"      # Green (Detected)
SELECTED_COLOR = "#FF0000" # Red (Selected)
GRID_COLOR = "#00FFFF"     # Cyan (Grid lines)

# Game Constants (from screen_elements.py)
TILES_X = 15
TILES_Y = 11

class AnnotationTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Monster Detection Annotation Tool")
        self.root.geometry("900x700")
        
        # Data state
        self.file_list = []
        self.current_index = 0
        self.current_data = {}
        self.current_image = None
        self.tk_image = None
        self.coordinates = [] # List of [x, y]
        self.dot_ids = {}     # Map canvas_id -> index in self.coordinates
        self.selected_dot_index = None
        
        # View state
        self.show_grid = True

        # Load file list
        self.load_file_list()

        # UI Layout
        self.setup_ui()

        # Load first image
        if self.file_list:
            self.load_current_file()
        else:
            messagebox.showinfo("Info", "No data found in 'training_data' folder.")

    def load_file_list(self):
        search_path = os.path.join(os.getcwd(), DATA_FOLDER, "*.json")
        self.file_list = sorted(glob.glob(search_path))
        print(f"Found {len(self.file_list)} samples.")

    def setup_ui(self):
        # Toolbar
        toolbar = tk.Frame(self.root, bd=1, relief=tk.RAISED)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        self.lbl_status = tk.Label(toolbar, text="No Data")
        self.lbl_status.pack(side=tk.LEFT, padx=5)

        # Right side buttons
        btn_next = tk.Button(toolbar, text="Next (->)", command=self.next_image)
        btn_next.pack(side=tk.RIGHT, padx=5)

        btn_prev = tk.Button(toolbar, text="Prev (<-)", command=self.prev_image)
        btn_prev.pack(side=tk.RIGHT, padx=5)

        btn_save = tk.Button(toolbar, text="Save (S)", command=self.save_current_data)
        btn_save.pack(side=tk.RIGHT, padx=5)

        # Grid Toggle
        self.btn_grid = tk.Button(toolbar, text="Grid: ON (G)", command=self.toggle_grid, bg="#ddd")
        self.btn_grid.pack(side=tk.RIGHT, padx=20)
        
        # Help label
        lbl_help = tk.Label(self.root, text="L-Click: Add/Move | R-Click: Delete | 'G': Toggle Grid | Arrows: Nav", bg="#ddd")
        lbl_help.pack(side=tk.BOTTOM, fill=tk.X)

        # Main Canvas area
        self.canvas_frame = tk.Frame(self.root)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.canvas_frame, bg="#222", cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Bind events
        self.canvas.bind("<Button-1>", self.on_left_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", self.on_right_click) 
        
        # Keyboard shortcuts
        self.root.bind("<Right>", lambda e: self.next_image())
        self.root.bind("<Left>", lambda e: self.prev_image())
        self.root.bind("s", lambda e: self.save_current_data())
        self.root.bind("g", lambda e: self.toggle_grid())

    def load_current_file(self):
        if not self.file_list: return
        
        json_path = self.file_list[self.current_index]
        
        # Load JSON
        with open(json_path, 'r') as f:
            self.current_data = json.load(f)
        
        # Load Image
        img_filename = self.current_data.get("image_file", "")
        img_path = os.path.join(os.getcwd(), DATA_FOLDER, img_filename)
        
        if not os.path.exists(img_path):
            print(f"Image not found: {img_path}")
            return

        self.current_image = Image.open(img_path)
        self.tk_image = ImageTk.PhotoImage(self.current_image)

        # Load Coordinates
        self.coordinates = self.current_data.get("coordinates", [])
        
        self.redraw_canvas()
        self.update_status()

    def toggle_grid(self):
        self.show_grid = not self.show_grid
        status = "ON" if self.show_grid else "OFF"
        self.btn_grid.config(text=f"Grid: {status} (G)")
        self.redraw_canvas()

    def redraw_canvas(self):
        self.canvas.delete("all")
        
        if self.tk_image:
            # Draw Image
            self.canvas.create_image(0, 0, image=self.tk_image, anchor=tk.NW)
            self.canvas.config(scrollregion=self.canvas.bbox(tk.ALL))
            
            # Draw Grid (if enabled)
            if self.show_grid:
                self.draw_grid_lines()

        # Draw Dots
        self.dot_ids = {}
        for i, (x, y) in enumerate(self.coordinates):
            self.draw_dot(x, y, i)

    def draw_grid_lines(self):
        if not self.current_image: return
        
        w = self.current_image.width
        h = self.current_image.height
        
        step_x = w / TILES_X
        step_y = h / TILES_Y

        # Draw Vertical Lines
        for i in range(1, TILES_X):
            x = i * step_x
            self.canvas.create_line(x, 0, x, h, fill=GRID_COLOR, dash=(2, 4), tag="grid")

        # Draw Horizontal Lines
        for i in range(1, TILES_Y):
            y = i * step_y
            self.canvas.create_line(0, y, w, y, fill=GRID_COLOR, dash=(2, 4), tag="grid")

    def draw_dot(self, x, y, index):
        x1 = x - DOT_RADIUS
        y1 = y - DOT_RADIUS
        x2 = x + DOT_RADIUS
        y2 = y + DOT_RADIUS
        
        color = DOT_COLOR
        if index == self.selected_dot_index:
            color = SELECTED_COLOR
            
        dot_id = self.canvas.create_oval(x1, y1, x2, y2, fill=color, outline="black", width=1)
        self.dot_ids[dot_id] = index

    def update_status(self):
        fname = os.path.basename(self.file_list[self.current_index])
        count = len(self.coordinates)
        self.lbl_status.config(text=f"File: {fname} ({self.current_index+1}/{len(self.file_list)}) | Monsters: {count}")

    # --- Interaction Logic ---

    def find_dot_at(self, x, y):
        # We look for overlapping items, but filter only for dots (not grid lines or image)
        overlap = self.canvas.find_overlapping(x-5, y-5, x+5, y+5)
        # Iterate backwards (topmost items first)
        for item_id in reversed(overlap):
            if item_id in self.dot_ids:
                return self.dot_ids[item_id]
        return None

    def on_left_click(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        dot_index = self.find_dot_at(x, y)
        
        if dot_index is not None:
            self.selected_dot_index = dot_index
            self.redraw_canvas()
        else:
            self.coordinates.append([int(x), int(y)])
            self.selected_dot_index = len(self.coordinates) - 1
            self.redraw_canvas()

    def on_drag(self, event):
        if self.selected_dot_index is not None:
            x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            # Update coordinate live
            self.coordinates[self.selected_dot_index] = [int(x), int(y)]
            self.redraw_canvas()

    def on_release(self, event):
        self.selected_dot_index = None
        self.redraw_canvas()

    def on_right_click(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        dot_index = self.find_dot_at(x, y)
        
        if dot_index is not None:
            del self.coordinates[dot_index]
            self.selected_dot_index = None
            self.redraw_canvas()
            self.update_status()

    # --- File Operations ---

    def save_current_data(self):
        if not self.file_list: return
        json_path = self.file_list[self.current_index]
        self.current_data["coordinates"] = self.coordinates
        self.current_data["monster_count"] = len(self.coordinates)
        with open(json_path, 'w') as f:
            json.dump(self.current_data, f, indent=4)
        print(f"Saved {os.path.basename(json_path)}")

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
    app = AnnotationTool(root)
    root.mainloop()