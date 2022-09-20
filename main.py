# region Imports
#import pyautogui
from tkinter import LEFT
import win32gui
import win32con
import win32api
import win32ui
import win32com.client
from ctypes import windll
import time
import pytesseract
import cv2
import numpy as np
import PIL
import os
import keyboard as kb
import re
from pynput import keyboard
from math import sqrt

# data
from collections import deque
import winsound
import scipy.stats as stats
#from natsort import natsorted
import difflib
import atexit
import array, struct
import operator

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


import data
import image as img
from screen_elements import *
from window_interaction import *
from extras import *
from client_manager import *
# endregion

class Bot():
    
    def __init__(self):
        self.base_directory = os.getcwd()
        self.original_title,self.hwnd = attachToClient()
        
        self.left, self.top, self.right, self.bottom = win32gui.GetWindowRect(self.hwnd)
        self.actionbar_moved = {'color': False}
        
        self.s_Stop = ScreenElement("Stop",self.hwnd,'stop.png',lambda w,h: (w - 200, 0 , w, int(h/2)))
        
        self.s_ActionBar = BoundScreenElement("ActionBar",self.hwnd,'action_bar_start.png','action_bar_end.png',lambda w,h: (0, int(h/4), int(w/3), h),lambda w,h: (int(2*w/3), int(h/4), w, h),(2,0))
        
        self.s_BattleList = ScreenWindow("BattleList",self.hwnd,'battle_list.png',2)
        self.s_Skills = ScreenWindow("Skills",self.hwnd,'skills.png',1)
        self.s_Party = ScreenWindow("Party",self.hwnd,'party_list.png',3)
        
        self.s_Map = RelativeScreenElement("Map",self.hwnd,self.s_Stop,(-118,-259,-52,-161)) #
        self.s_Bless = RelativeScreenElement("Bless",self.hwnd,self.s_Stop,(-104,-144,-135,-147))
        self.s_Buffs = RelativeScreenElement("Buffs",self.hwnd,self.s_Stop,(-118,0,-53,-1))
        self.s_Health = RelativeScreenElement("Health",self.hwnd,self.s_Stop,(-103,+18,-53,+14))
        self.s_Mana = RelativeScreenElement("Mana",self.hwnd,self.s_Stop,(-103,+31,-53,+27))
        self.s_Capacity = RelativeScreenElement("Capacity",self.hwnd,self.s_Stop,(-45,-13,-52,-15))
        self.s_WindowButtons = RelativeScreenElement("WindowButtons",self.hwnd,self.s_Stop,(-118,71,-52,164))
        
        self.ScreenElements = [self.s_Stop]
        self.BoundScreenElements = [self.s_ActionBar]
        self.ScreenWindows = [self.s_BattleList,self.s_Skills,self.s_Party]
        self.RelativeScreenElements = [self.s_Map,self.s_Bless,self.s_Buffs,self.s_Health,self.s_Mana,self.s_Capacity,self.s_WindowButtons]
        #element order is important
        self.ElementsLists = [self.ScreenElements,self.BoundScreenElements,self.RelativeScreenElements,self.ScreenWindows,]
        
        #hp history for burst damage
        self.hp_queue = deque([], maxlen=3)
        for i in range(0, 3):
            self.hp_queue.append(100)
        #buff dict
        self.buffs = {}
        self.heal_spell_hotkey = 'F1'
        self.heal_potion_hotkey = 'F3'
        self.strong_heal_hotkey = False
        self.use_hp_pot = False
        self.rune_heal_hotkey = False
        self.mana_hotkey = 'F3'
        self.mp_thresh = 30
        self.hp_thresh_hi = 90
        self.hp_thresh_lo = 70
        
    def maximizeWindow(self):
        tup = win32gui.GetWindowPlacement(self.hwnd)
        if tup[1] == win32con.SW_SHOWMINIMIZED:
            win32gui.ShowWindow(self.hwnd, win32con.SW_MAXIMIZE)
            time.sleep(0.2)
    
    def updateWindowCoordinates(self):
        self.maximizeWindow()
        l, t, r, b = win32gui.GetWindowRect(self.hwnd)
        if (self.left, self.top, self.right, self.bottom) != (l, t, r, b):
            print("window rect changed")
            self.left, self.top, self.right, self.bottom = l, t, r, b
            self.height = abs(self.bottom - self.top)
            self.width = abs(self.right - self.left)
            bot.updateAllElements()
        else:
            if self.checkActionbarMoved():
                print("actionbar moved")
                bot.updateBoundElements()
    def checkNotDetectedElements(self):
        for elem_type in self.ElementsLists:
            for elem in elem_type:
                if not elem.detected:
                    print("not detected: "+elem.name)
                    return True
        return False
    def updateAllElements(self):
        for elem_type in self.ElementsLists:
            for elem in elem_type:
                if elem_type == self.ScreenElements:
                    if not elem.update():
                        elem.update()
                elif elem_type == self.BoundScreenElements:
                    if not elem.update():
                        pass
                    else:
                        pass
                elif elem_type == self.ScreenWindows:
                    while not elem.update():
                        if elem.button_position:
                            print("clicking button for window: "+ elem.name + " position: "+str(elem.button_position))
                            self.clickWindowButton(elem.button_position)
                            time.sleep(0.5)
                        else:
                            print("window button position is None")
                            break      
                elif elem_type == self.RelativeScreenElements:
                    if not elem.update():
                        pass
    def updateNotDetectedElements(self):
        for elem_type in self.ElementsLists:
            for elem in elem_type:
                if elem_type != self.ScreenWindows:
                    if not elem.detected:
                        elem.update()
                else:
                    while not elem.detected:
                        elem.update()
                        if elem.button_position:
                            print("clicking button for window: "+ elem.name + " position: "+str(elem.button_position))
                            self.clickWindowButton(elem.button_position)
                            time.sleep(0.5)
                        else:
                            print("window button position is None")
                            break      
                        
    def updateBoundElements(self):
        for elem in self.BoundScreenElements:
            elem.update()
            
    def checkActionbarMoved(self):
        if self.s_ActionBar.detected:
            #(117, 117, 117) at (-14,81) and (-13,81)
            #(120, 120, 120) at (-12,81)
            x,y,_,_ = self.s_ActionBar.region
            dx = -14
            dy = 82
            x += dx
            y += dy
            #colors = {(117, 117, 117) : [] ,(120, 120, 120) : []}
            
            pixel_color = img.GetPixelRGBColor(self.hwnd, (x,y))
            if pixel_color != (117,117,117):
                print(pixel_color)
                return True
        return False
        '''
        if type(self.actionbar_moved['color']) is bool:
            #not yet initialized
            self.actionbar_moved['color'] = img.GetPixelRGBColor(self.hwnd, (x,y))
            return False
        else:
            pixel_color = img.GetPixelRGBColor(self.hwnd, (x,y))
            if self.actionbar_moved['color'] != pixel_color:
                return True
        '''
        
    def clickWindowButton(self,pos):
        '''pos: starts from 1'''
        region = self.s_WindowButtons.region
        w,h = self.s_WindowButtons.getWidth(),self.s_WindowButtons.getHeight()
        
        row_amount = 5
        column = (pos - 1) % row_amount
        row = int((pos - 1) / row_amount)
        
        button_width,button_height = 19, 19 # pixels
        in_between = 3 #pixels
        distance = button_width + in_between
        area = (region[0]+column*distance, region[1]+row*distance,region[0]+column*distance+button_width, region[1]+row*distance+button_height)
        x = int((area[2]+area[0])/2)
        y = int((area[3]+area[1])/2)
        print((x,y))
        click(self.hwnd,x,y)
    
    def getActionbarSlotPosition(self,pos):
        box_width = 34
        
        y = self.s_ActionBar.region[1]
        x = self.s_ActionBar.region[0]+(box_width*(pos))+2*pos
        return (x,y)
    def checkActionBarSlotCooldown(self,pos):

        x,y = self.getActionbarSlotPosition(pos)
        x2,y2 = x+34,y+34
        #full slot
        #image = img.screengrab_array(self.hwnd,(x,y,x2,y2),True)
        #center region to check cooldown time
        image = img.screengrab_array(self.hwnd,(x+15,y+18,x2-15,y2-12),True)
        comp = np.all(image == (223, 223, 223), axis=-1) 
        if (np.count_nonzero(comp) > 0):
            #print("pos "+str(pos) + " IS on cooldown")
            return False
        #print("pos "+str(pos) + " is NOT on cooldown")
        return True
    
    def getVitals(self):
        #returns hp % and mp % in a tuple
        hppc = 0
        mppc = 0
        cant = 0
        region = self.s_Health.region
        
        y = region[1]+6
        bar_width = self.s_Health.getWidth()
        delta = 4
        #counts gray pixels in a line of hp region
        for x in range(region[0], region[2], delta):
            color = img.GetPixelRGBColor(self.hwnd,(x, y))
            dist = img.ColorDistance(color, (95, 95, 95))
            if (dist <= 15):
                cant += 1
        cant *= delta
        hppc = 100 * (bar_width-cant)/bar_width
        
        region = self.s_Mana.region
        y = region[1]+6
        cant = 0
        #counts gray pixels in a line of mp region
        for x in range(region[0], region[2], delta):
            color = img.GetPixelRGBColor(self.hwnd,(x, y))
            dist = img.ColorDistance(color, (95, 95, 95))
            if (dist <= 15):
                cant += 1
        cant *= delta
        mppc = 100 * (bar_width-cant)/bar_width
        return (hppc, mppc)
    def getBurstDamage(self):
        current = self.hp_queue[0]
        val = []
        for i in range(0, 3):
            val.append(self.hp_queue[i]-current)
        return max(val)
    def manageVitals(self):
        hppc, mppc = self.getVitals()
        self.hp_queue.pop()
        self.hp_queue.appendleft(hppc)

        burst = self.getBurstDamage()
        if hppc < self.hp_thresh_lo:
            if self.rune_heal_hotkey and hppc < 35:
                press(self.hwnd,self.rune_heal_hotkey)
            else:
                if self.heal_potion_hotkey:
                    press(self.hwnd,self.heal_potion_hotkey)
        if hppc < 50 or burst > 40:
            if self.strong_heal_hotkey:
                self.press(self.strong_heal_hotkey)
        if (hppc <= self.hp_thresh_hi or burst > 12):
            press(self.hwnd,self.heal_spell_hotkey)
        if (mppc <= self.mp_thresh):
            press(self.hwnd,self.mana_hotkey)
    def isAttacking(self):
        b_x, b_y,_,b_y2 = self.s_BattleList.region
        #w, h = self.s_BattleList.getWidth(),self.s_BattleList.getHeight()
        # x 3 y 22
        #found = lookForColor([(255,0,0),(255,128,128)],(x,y,w-150,h))
        
        colors = [(255, 0, 0), (255, 128, 128)]
        x = b_x+3  # constant
        first_pos = b_y+24  # about mid of first square
        d = 22  # dist between boxes, 19+3
        #battlelist = img.screengrab_array(self.hwnd,self.s_BattleList.region)

        for y in range(first_pos, b_y2, d):
            #cv2.line(battlelist, (3,y-b_y), (3,y-b_y+5), (255,255,255), 1) 
            color = img.GetPixelRGBColor(self.hwnd,(x, y))
            if (color in colors):
                #if (vocation == "knight" and y != first_pos):
                #    return False
                return True
        #img.visualize(battlelist)
        return False
    def getBuffs(self):
        lista = ['haste', 'pz', 'hungry', 'magicshield']
        area = self.s_Buffs.region
        os.chdir(self.base_directory)
        self.buffs = img.imageListExist(self.hwnd,lista, 'buffs', area, 0.95)

    def attack(self):
        _x, _y, _x2,_y2 = self.s_BattleList.region
        # x 3 y 22
        #found = lookForColor([(255,0,0),(255,128,128)],(x,y,w-150,h))
        x = _x+25#x = _x+12  # constant
        first_pos = _y+30  # about mid of first square
        d = 22  # dist between boxes, 19+3
        if not self.isAttacking() and not self.buffs['pz']:
            for y in range(first_pos, _y2, d):
                    color = img.GetPixelRGBColor(self.hwnd,(x, y))
                    if (color == (0,0,0)):
                        click(self.hwnd,x, y)
                        time.sleep(0.001)
                        return
'''TODO
Update search regions on window dimension change
implement a check for dimension change

'''
            
            
if __name__ == "__main__":
    
    bot = Bot()
    
    bot.updateAllElements()
    loop = True
    
    while(loop):
        bot.updateWindowCoordinates()
        if (bot.checkNotDetectedElements()):
            print("not detected elements, updating")
            bot.updateNotDetectedElements()
            time.sleep(1)
        bot.manageVitals()
        bot.getBuffs()
        bot.attack()
        
        