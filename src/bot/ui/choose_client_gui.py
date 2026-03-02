import os
import tkinter as tk
from tkinter import messagebox
import psutil
import configparser
import win32gui
import win32process
import json
import re
from urllib.parse import urlparse
from ..vision import image as img

# Colores de tu identidad visual
BG_COLOR = img.rgb((30, 30, 30))
BTN_COLOR = img.rgb((60, 60, 60))
TEXT_COLOR = img.rgb((240, 240, 240))
ACCENT_COLOR = img.rgb((0, 200, 100))  # Verde ‚xito
INFO_COLOR = "#3498db"                # Azul info
DEBUG_CLIENT_SELECTION = True
_EXE_SERVER_CACHE = {}


def _client_debug(msg):
    if DEBUG_CLIENT_SELECTION:
        print(f"[CLIENT_SELECT] {msg}")


def _read_tail_lines(path, max_lines=800):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return lines[-max_lines:]
    except Exception as e:
        _client_debug(f"Failed reading log tail '{path}': {e}")
        return []


def _detect_server_from_client_exe(exe_path):
    if exe_path in _EXE_SERVER_CACHE:
        cached = _EXE_SERVER_CACHE[exe_path]
        _client_debug(f"EXE fallback cache hit for '{exe_path}' -> '{cached}'")
        return cached

    _client_debug(f"EXE fallback scanning '{exe_path}'")
    if not os.path.exists(exe_path):
        _client_debug("EXE fallback path does not exist")
        _EXE_SERVER_CACHE[exe_path] = None
        return None

    try:
        with open(exe_path, "rb") as f:
            blob = f.read()
    except Exception as e:
        _client_debug(f"EXE fallback read error: {e}")
        _EXE_SERVER_CACHE[exe_path] = None
        return None

    patterns = [
        re.compile(rb"(?:loginWebService|clientWebService)=([^\x00\r\n\t ]+)"),
        re.compile(rb"(https?://[A-Za-z0-9\.-]+(?:/[^\x00\r\n\t ]*)?)"),
    ]
    server_host = None
    detected_url = None

    # First try explicit keys; then generic URLs as last resort.
    for idx, regex in enumerate(patterns):
        for m in regex.finditer(blob):
            raw = m.group(1)
            try:
                url = raw.decode("utf-8", errors="ignore").strip()
            except Exception:
                continue
            if not url.startswith("http"):
                continue
            if idx == 1 and "api/login" not in url:
                continue
            parsed = urlparse(url)
            host = (parsed.netloc or "").strip()
            if host:
                server_host = host
                detected_url = url
                break
        if server_host:
            break

    if server_host:
        _client_debug(f"EXE fallback resolved url='{detected_url}' host='{server_host}'")
    else:
        _client_debug("EXE fallback did not find a usable web service URL")

    _EXE_SERVER_CACHE[exe_path] = server_host
    return server_host


def _detect_server_from_client_log(base_dir, char_name):
    log_path = os.path.join(os.path.dirname(base_dir), "log", "client.log")
    _client_debug(f"Log fallback candidate='{log_path}'")
    if not os.path.exists(log_path):
        _client_debug("Log fallback file not found")
        return None

    lines = _read_tail_lines(log_path, max_lines=1200)
    if not lines:
        _client_debug("Log fallback had no readable lines")
        return None

    request_with_name_re = re.compile(
        r'Request connection to gameserver\s+"([^"]+)"\s+"([^"]+)"'
    )
    request_with_char_re = re.compile(
        r'Request connection to gameserver\s+"([^"]+)"\s+\(unprotected:\s+"[^"]+"\s+\)\s+requested\s+\(Charakter\s+"([^"]+)"\s+\)'
    )

    label_line_candidates = []
    for idx, line in enumerate(lines):
        m = request_with_name_re.search(line)
        if m:
            label_line_candidates.append((idx, m.group(1), m.group(2)))

    if not label_line_candidates:
        _client_debug("Log fallback found no labeled gameserver lines")
        return None

    # Prefer entries matched to the currently selected character.
    if char_name and char_name != "Sin Nombre":
        for idx in range(len(lines) - 1, -1, -1):
            m = request_with_char_re.search(lines[idx])
            if not m:
                continue
            endpoint, seen_char = m.group(1), m.group(2)
            if seen_char != char_name:
                continue
            for j in range(min(len(lines) - 1, idx + 3), max(-1, idx - 3), -1):
                m2 = request_with_name_re.search(lines[j])
                if m2 and m2.group(1) == endpoint:
                    server_name = m2.group(2).strip()
                    _client_debug(
                        f"Log fallback matched char='{char_name}' endpoint='{endpoint}' server='{server_name}'"
                    )
                    return server_name or None

    # Otherwise use most recent labeled entry.
    _, endpoint, server_name = label_line_candidates[-1]
    server_name = (server_name or "").strip()
    _client_debug(f"Log fallback recent endpoint='{endpoint}' server='{server_name}'")
    return server_name or None

def get_client_metadata(hwnd):
    """Detecta Servidor y Nombre del Personaje."""
    server_id = "desconocido"
    char_name = "Sin Nombre"
    title = win32gui.GetWindowText(hwnd)
    _client_debug(f"Reading metadata for hwnd={hwnd}, title='{title}'")
    
    if " - " in title:
        char_name = title.split(" - ")[1].strip()
    _client_debug(f"Parsed character name='{char_name}'")

    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid)
        exe_path = proc.exe()
        base_dir = os.path.dirname(exe_path)
        _client_debug(f"pid={pid}, exe_path='{exe_path}'")
        
        # L¢gica de carpetas bin/conf
        paths = [
            os.path.join(base_dir, "config.ini"),
            os.path.join(os.path.dirname(base_dir), "conf", "config.ini")
        ]
        _client_debug(f"Config candidates={paths}")
        
        for p in paths:
            _client_debug(f"Checking config path='{p}' exists={os.path.exists(p)}")
            if os.path.exists(p):
                cp = configparser.ConfigParser()
                read_ok = cp.read(p)
                _client_debug(f"ConfigParser.read -> {read_ok}, sections={cp.sections()}")
                url = cp.get('URLS', 'loginWebService', fallback='unknown')
                _client_debug(f"Raw loginWebService='{url}'")

                parsed = urlparse(url)
                parsed_host = parsed.netloc or parsed.path.split('/')[0]
                parsed_host = parsed_host.strip()
                if parsed_host:
                    server_id = parsed_host
                else:
                    server_id = url.replace('https://', '').replace('http://', '').split('/')[0]
                _client_debug(f"Parsed server_id='{server_id}'")
                break

        if server_id == "desconocido":
            fallback_server = _detect_server_from_client_exe(exe_path)
            if fallback_server:
                server_id = fallback_server
                _client_debug(f"Server id from EXE fallback='{server_id}'")
            else:
                _client_debug("EXE fallback did not resolve server id; trying log fallback")
                fallback_server = _detect_server_from_client_log(base_dir, char_name)
                if fallback_server:
                    server_id = fallback_server
                    _client_debug(f"Server id from log fallback='{server_id}'")
                else:
                    _client_debug("Server id fallback did not resolve a value")
    except Exception as e:
        _client_debug(f"Metadata read failed for hwnd={hwnd}: {e}")
    _client_debug(f"Final metadata hwnd={hwnd}: server='{server_id}', char='{char_name}'")
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
        _client_debug(f"UI selection changed -> '{selection}'")
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
                _client_debug(f"Session updated -> hwnd={h}, server='{sid}', char='{char}', vocation='{session['vocation']}'")
                break
        if not found:
            server_lbl_var.set("SERVER: ---")
            char_lbl_var.set("PERSONAJE: ---")
            voc_lbl_var.set("VOCACION: ---")
            session.update({"hwnd": None, "server": None, "name": None, "vocation": None})
            _client_debug("No matching client found for selection; session reset")

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
        _client_debug(f"scan_clients found {len(clients)} candidates")
        for h, t in clients.items():
            _client_debug(f" - hwnd={h}, title='{t}'")

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
