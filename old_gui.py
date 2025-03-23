from wsgiref import validate
from GUI import *
from tkinter import BooleanVar,StringVar,IntVar,PhotoImage
from pynput import keyboard
from functools import partial
class ModernBotGUI:
    def __init__(self,bot, CharName, vocation):
        self.bot = bot
        self.title = CharName + " - "+str(bot.hwnd)
        self.root = GUI('root', self.title)
        self.root.MainWindow('Main', [370, 530], [2, 2.36])
        self.root.deiconify()

        self.root.addMinimalLabel(f'Logged as: {CharName} vocation: {vocation}', [14, 14])

        self.bot.loop = BooleanVar( value= self.bot.loop )
        self.bot.attack = BooleanVar( value= self.bot.attack )
        self.bot.attack_spells = BooleanVar( value= self.bot.attack_spells )
        self.bot.hp_heal = BooleanVar( value= self.bot.hp_heal )
        self.bot.mp_heal = BooleanVar( value= self.bot.mp_heal )
        self.bot.hp_thresh_high = IntVar( value = self.bot.hp_thresh_high )
        self.bot.hp_thresh_low = IntVar( value = self.bot.hp_thresh_low )
        self.bot.mp_thresh = IntVar( value = self.bot.mp_thresh )
        self.bot.party_leader = StringVar(value = self.bot.party_leader)
        self.bot.manual_loot = BooleanVar( value = self.bot.manual_loot)
        self.bot.cavebot = BooleanVar( value = self.bot.cavebot)
        self.bot.res = BooleanVar( value = self.bot.res)
        self.bot.follow_party = BooleanVar( value= self.bot.follow_party )
        self.bot.min_monsters_around_spell = IntVar( value = self.bot.min_monsters_around_spell )
        self.bot.kill_amount = IntVar( value = self.bot.kill_amount )
        self.bot.kill_stop_amount  = IntVar( value = self.bot.kill_stop_amount )
        self.bot.use_area_rune = BooleanVar( value = self.bot.use_area_rune)
        self.bot.manage_equipment = BooleanVar( value = self.bot.manage_equipment)
        self.bot.loot_on_spot = BooleanVar( value = self.bot.loot_on_spot)
        self.bot.amp_res = BooleanVar( value = self.bot.amp_res)
        #self.bot.monsters_around_image = PhotoImage(file = "monsters_around.png")
        
        # region Buttons
        
        self.root.addButton('Update Elements', self.bot.updateAllElements, [120, 20], [20, 50])
        self.root.addButton('test', self.bot.lootAround, [120, 20], [150, 50])
        self.root.addEntry([130, 80], self.bot.hp_thresh_high, width=6, validate_function=digitValidation)
        self.root.addLabel(r'% Light', [175, 80])
        self.root.addEntry([130, 105], self.bot.hp_thresh_low, width=6, validate_function=digitValidation)
        self.root.addLabel(r'% Heavy', [175, 105])
        self.root.addEntry([130, 140], self.bot.mp_thresh, width=6, validate_function=digitValidation)
        self.root.addLabel(r'%', [175, 140])
        self.root.addCheck(self.bot.hp_heal, [20, 80], self.bot.hp_heal.get(), "HP Healing")
        self.root.addCheck(self.bot.mp_heal, [20, 140], self.bot.mp_heal.get(), "MP Healing")
        self.root.addCheck(self.bot.attack, [20, 170], self.bot.attack.get(), "Attack (Battle)")
        self.root.addCheck(self.bot.attack_spells, [20, 200],self.bot.attack_spells.get(), "Attack Spells")
        self.root.addCheck(self.bot.res, [130, 170], self.bot.res.get(), "Exeta res")
        self.root.addCheck(self.bot.amp_res, [250, 170], self.bot.amp_res.get(), "Amp res")
        self.root.addCheck(self.bot.loot_on_spot, [250, 200], self.bot.loot_on_spot.get(), "Loot on spot")
        
        self.root.addCheck(self.bot.manual_loot, [130, 200], self.bot.manual_loot.get(), "Manual Loot")
        self.root.addCheck(self.bot.use_area_rune, [20, 230], self.bot.use_area_rune.get(), "Area rune")
        self.root.addCheck(self.bot.follow_party, [130, 230],self.bot.follow_party.get(), "Follow Party")
        self.root.addCheck(self.bot.manage_equipment, [130, 260],self.bot.manage_equipment.get(), "Manage Equipment")
        self.root.addCheck(self.bot.cavebot, [20, 260], self.bot.cavebot.get(), "Cavebot")
        self.root.addLabel('Party leader:', [20, 295])
        self.root.addEntry([20, 320], self.bot.party_leader, width=20)
        self.root.addLabel('Monster around spell:', [150, 295])
        self.root.addEntry([150, 320], self.bot.min_monsters_around_spell, width=20, validate_function=digitValidation)
        self.root.addLabel('Kill amount:', [20, 345])
        self.root.addEntry([20, 370], self.bot.kill_amount, width=20, validate_function=digitValidation)
        self.root.addLabel('Kill stop amount:', [150, 345])
        self.root.addEntry([150, 370], self.bot.kill_stop_amount, width=20, validate_function=digitValidation)
        #self.root.addLabel('Monster around spell:', [150, 295])
        #self.root.addEntry([150, 345], self.bot.min_monsters_around_spell, width=20, validate_function=digitValidation)
        self.root.addButton('Sell All', self.bot.sellAllNPC, [92, 23], [20, 420])
        
        #self.image = self.root.addImage(self.bot.monsters_around_image, [160, 245])
        
        def Exit():
            
            print("Exiting...")
            self.bot.loop.set(False)
            raise SystemExit

        self.root.addButton('Exit', Exit, [92, 23], [10, 498])
        self.root.Protocol(Exit)
        #self.root.bind('<KeyPress>', self.onKeyPress)

        # endregion
        
    def loop(self):
        self.root.loop()
        #self.image.configure(image = self.bot.monsters_around_image)
    def onKeyPress(self,event): #https://www.pythontutorial.net/tkinter/tkinter-event-binding/
        print('press:' + event.keysym)
        if event.keysym == "Prior":
            self.bot.follow_party.set(value = not self.bot.follow_party.get())
        elif event.keysym == "Next":
            self.bot.hp_heal.set(value = not self.bot.hp_heal.get())
        elif event.keysym == "End":
            self.bot.use_area_rune.set(value = not self.bot.use_area_rune.get())
    
    

def digitValidation(P):
    if str.isdigit(P) or P == "":
        return True
    else:
        return False
def GUIUpdateAllElements():
    print("Updating all elements from GUI")
def Default():
    print("Clicked a button")