import win32gui

LOADED_STRING = " - [Loaded]"

def getClientList():
    clients = []
    
    def enumHandler(hwnd, lParam):
        if win32gui.GetClassName(hwnd) == "Qt5QWindowOwnDCIcon" and "Tibia" in win32gui.GetWindowText(hwnd):
            clients.append((win32gui.GetWindowText(hwnd),hwnd))
    win32gui.EnumWindows(enumHandler, None)
    return clients

def getUnloadedClient():
    clients = getClientList()
    for client in clients:
        c_name, c_hwnd = client
        if LOADED_STRING not in c_name:
            return (c_name,c_hwnd)
    if len(client) > 0:
        #fix titles
        print("clients found but none unloaded, fixing")
        for client in clients:
            c_name, c_hwnd = client
            original_title = c_name.split(LOADED_STRING)[0]
            win32gui.SetWindowText(c_hwnd,original_title)
        return getUnloadedClient()
    return False

def attachToClient():
    result = getUnloadedClient()
    if not result:
        print("no client available")
        return False
    original_title, hwnd = result
    win32gui.SetWindowText(hwnd,original_title+LOADED_STRING)
    return (original_title,hwnd)