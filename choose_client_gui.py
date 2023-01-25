"""
starts the selection page to choose window of capture
"""

import time
import os
import threading
import tkinter as tk
import image as img
import win32gui
#titles = get_titles()
#conf = ConfManager.get('conf.json')
#script = f'scripts/{conf["preferences_name"]}'
clients = {}
bots = []
client_selector_count = 0

def botEnumHandler(hwnd, lParam):
    try:
        title = win32gui.GetWindowText(hwnd)
        if win32gui.GetClassName(hwnd) == "TkTopLevel":
            if "Choose window" in title:
                global client_selector_count
                client_selector_count += 1
            else:
                client_hwnd = title.split(" - ")[1]
                bots.append(client_hwnd)
    except:
        pass
def enumHandler(hwnd, lParam):
    title = win32gui.GetWindowText(hwnd)
    if win32gui.GetClassName(hwnd) == "Qt5QWindowOwnDCIcon" and "Tibia" in title and str(hwnd) not in bots:
        clients[hwnd] = title
win32gui.EnumWindows(botEnumHandler, None)
win32gui.EnumWindows(enumHandler, None)
hwnd = -1
def choose_capture_window():
    global hwnd
    window = tk.Tk()
    w = 260
    h = 90
    x = w+(w*client_selector_count)#(window.winfo_screenwidth() - w) / (3 - client_selector_count*0.4)
    y = (window.winfo_screenheight() - h) / 2.4
    window.geometry('%dx%d+%d+%d' % (w, h, x, y))
    window.resizable(width=False, height=False)
    window.title('Choose window')
    window.configure(background=img.rgb((120, 98, 51)), takefocus=True)
    

    def destroy():
        """
        destroy current window and exit with success status
        """

        print('Exiting...')

        window.destroy()
        exit(0)

    def bootstrap():
        """
        load-up configurations and pass to conf page
        """
        global hwnd
        hwnd =  list(clients.keys())[list(clients.values()).index(selected_window.get())]
        print(hwnd)
        window.destroy()
    
    selected_window = tk.StringVar()
    selected_window.set(list(clients.values())[client_selector_count])

    select_window_list = tk.OptionMenu(window, selected_window, *list(clients.values()))
    select_window_list.configure(anchor='w')
    select_window_list.pack()
    select_window_list.place(w=230, h=24, x=15, y=17)

    bootstrap_button = tk.Button(window, width=15, text="Attach", command=bootstrap,
                                     bg=img.rgb((127, 17, 8)),
                                     fg='white',
                                     activebackground=img.rgb((123, 13, 5)))
    bootstrap_button.pack()
    bootstrap_button.place(w=85, h=25, x=35, y=53)

    exit_button = tk.Button(window, width=15, text="Exit", command=destroy, bg=img.rgb((127, 17, 8)),
                            fg='white',
                            activebackground=img.rgb((123, 13, 5)))
    exit_button.pack()
    exit_button.place(w=85, h=25, x=140, y=53)
    
    window.mainloop()
    return hwnd