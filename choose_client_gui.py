import os
import tkinter as tk
from tkinter import messagebox
import psutil
import configparser
import win32gui
import win32process
import json
import image as img

# Colores de tu identidad visual
BG_COLOR = img.rgb((30, 30, 30))
BTN_COLOR = img.rgb((60, 60, 60))
TEXT_COLOR = img.rgb((240, 240, 240))
ACCENT_COLOR = img.rgb((0, 200, 100))  # Verde ‚xito
INFO_COLOR = "#3498db"                # Azul info

def get_client_metadata(hwnd):
    """Detecta Servidor y Nombre del Personaje."""
    server_id = "desconocido"
    char_name = "Sin Nombre"
    title = win32gui.GetWindowText(hwnd)
    
    if " - " in title:
        char_name = title.split(" - ")[1].strip()

    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid)
        exe_path = proc.exe()
        base_dir = os.path.dirname(exe_path)
        
        # L¢gica de carpetas bin/conf
        paths = [
            os.path.join(base_dir, "config.ini"),
            os.path.join(os.path.dirname(base_dir), "conf", "config.ini")
        ]
        
        for p in paths:
            if os.path.exists(p):
                cp = configparser.ConfigParser()
                cp.read(p)
                url = cp.get('URLS', 'loginWebService', fallback='unknown')
                server_id = url.replace('https://', '').replace('http://', '').split('/')[0]
                break
    except: pass
    return server_id, char_name

def choose_capture_window():
    window = tk.Tk()
    window.title('Tibia Bot - Session Selector')
    window.geometry('450x450')
    window.configure(bg=BG_COLOR)

    # Variables de estado
    clients = {}
    selected_option = tk.StringVar()
    server_lbl_var = tk.StringVar(value="SERVER: ---")
    char_lbl_var = tk.StringVar(value="CHAR: ---")
    voc_lbl_var = tk.StringVar(value="VOCACION: ---")
    
    session = {"hwnd": None, "server": None, "name": None, "vocation": None}
    is_submitted = [False]

    def get_known_vocation(server, name):
        """Revisa si el perfil ya existe en el bot_config.json"""
        if not name or name == "Sin Nombre":
            return None
        if os.path.exists("bot_config.json"):
            try:
                with open("bot_config.json", "r") as f:
                    data = json.load(f)
                    profiles = data.get("profiles", {})
                    prefix = f"{server}::{name}::"
                    for key in profiles:
                        if key.startswith(prefix):
                            return key.split("::")[-1]
            except: pass
        return None

    def update_display(*args):
        """Actualiza los logs visuales al cambiar la selecci¢n"""
        selection = selected_option.get()
        found = False
        for h, t in clients.items():
            if t == selection:
                sid, char = get_client_metadata(h)
                voc = get_known_vocation(sid, char)
                
                server_lbl_var.set(f"SERVER: {sid}")
                char_lbl_var.set(f"PERSONAJE: {char}")
                
                if voc:
                    voc_lbl_var.set(f"VOCACION: {voc.upper()}")
                    session.update({"hwnd": h, "server": sid, "name": char, "vocation": voc})
                else:
                    voc_lbl_var.set("VOCACION: [NUEVO PERFIL]")
                    session.update({"hwnd": h, "server": sid, "name": char, "vocation": ""})
                found = True
                break
        if not found:
            server_lbl_var.set("SERVER: ---")
            char_lbl_var.set("PERSONAJE: ---")
            voc_lbl_var.set("VOCACION: ---")
            session.update({"hwnd": None, "server": None, "name": None, "vocation": None})

    # --- UI Dise¤o Mateo ---
    tk.Label(window, text="GESTOR DE SESIONES", bg=BG_COLOR, fg=TEXT_COLOR, 
             font=("Verdana", 12, "bold")).pack(pady=20)

    selected_option.trace("w", update_display)

    # Men£ desplegable estilizado + boton reload
    select_frame = tk.Frame(window, bg=BG_COLOR)
    select_frame.pack(pady=10, padx=50, fill="x")

    opt = tk.OptionMenu(select_frame, selected_option, "Buscando...")
    opt.config(bg=BTN_COLOR, fg=TEXT_COLOR, highlightthickness=0, relief="flat")
    opt["menu"].config(bg=BTN_COLOR, fg=TEXT_COLOR)
    opt.pack(side="left", expand=True, fill="x", padx=(0, 5))

    def scan_clients():
        """Escanea ventanas y actualiza el OptionMenu."""
        clients.clear()
        def enumHandler(hwnd, lParam):
            if "Tibia" in win32gui.GetWindowText(hwnd) and "Qt" in win32gui.GetClassName(hwnd):
                clients[hwnd] = win32gui.GetWindowText(hwnd)
        win32gui.EnumWindows(enumHandler, None)

        menu = opt["menu"]
        menu.delete(0, "end")
        titles = list(clients.values())
        if titles:
            for title in titles:
                menu.add_command(label=title, command=lambda v=title: selected_option.set(v))
            if not selected_option.get() or selected_option.get() not in titles:
                selected_option.set(titles[0])
        else:
            selected_option.set("No se detectaron clientes")

    btn_reload = tk.Button(select_frame, text="🔄", bg=BTN_COLOR, fg=TEXT_COLOR,
                           command=scan_clients, relief="flat", font=("Verdana", 10))
    btn_reload.pack(side="right")

    # Zona de Feedback (Logs)
    log_frame = tk.Frame(window, bg=BG_COLOR, pady=10)
    log_frame.pack()
    
    tk.Label(log_frame, textvariable=server_lbl_var, bg=BG_COLOR, fg=ACCENT_COLOR, 
             font=("Consolas", 10, "bold")).pack()
    tk.Label(log_frame, textvariable=char_lbl_var, bg=BG_COLOR, fg=INFO_COLOR, 
             font=("Consolas", 10, "bold")).pack()
    tk.Label(log_frame, textvariable=voc_lbl_var, bg=BG_COLOR, fg="#f1c40f", 
             font=("Consolas", 10, "bold")).pack()

    def on_attach():
        if not session["hwnd"]:
            return
        if session["name"] == "Sin Nombre":
            messagebox.showwarning("Error", "Inicia sesion en el juego primero para detectar el nombre.")
            return
        is_submitted[0] = True
        if not session["vocation"]:
            # Si no hay vocaci¢n, mostramos la pantalla de elecci¢n
            show_vocation_choice()
        else:
            window.destroy()

    def on_close():
        is_submitted[0] = False
        window.destroy()

    window.protocol("WM_DELETE_WINDOW", on_close)

    btn_attach = tk.Button(window, text="CONECTAR", bg=ACCENT_COLOR, fg="white",
                           font=("Verdana", 10, "bold"), command=on_attach,
                           relief="flat", padx=30, pady=10)
    btn_attach.pack(pady=20)

    def show_vocation_choice():
        # Limpiar ventana para elegir vocaci¢n
        for widget in window.winfo_children():
            widget.destroy()
        
        tk.Label(window, text="CONFIGURACION INICIAL", bg=BG_COLOR, fg=TEXT_COLOR, 
                 font=("Verdana", 12, "bold")).pack(pady=20)
        tk.Label(window, text=f"¨Qu‚ vocaci¢n es {session['name']}?", 
                 bg=BG_COLOR, fg=TEXT_COLOR).pack(pady=10)
        
        vocs = [("Knight", "#c0392b"), ("Sorcerer", "#8e44ad"), 
                ("Druid", "#2980b9"), ("Paladin", "#d4ac0d")]
        
        for v_name, color in vocs:
            tk.Button(window, text=v_name, bg=color, fg="white", width=20,
                      command=lambda vn=v_name.lower(): finalize(vn)).pack(pady=5)

    def finalize(v):
        session["vocation"] = v
        window.destroy()

    scan_clients()

    window.mainloop()
    if not is_submitted[0] and not session["vocation"]:
        return None, None, None, None
    return session["hwnd"], session["server"], session["name"], session["vocation"]
