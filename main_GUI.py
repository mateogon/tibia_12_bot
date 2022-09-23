from wsgiref import validate
from GUI import *
from tkinter import BooleanVar,StringVar,IntVar
class root:
    def __init__(self,bot, CharName):
        self.bot = bot
        self.root = GUI('root', 'Tibia 12 Bot')
        self.root.MainWindow('Main', [357, 530], [2, 2.36])
        self.root.deiconify()

        self.root.addMinimalLabel(f'Logged as: {CharName}', [14, 14])

        self.bot.loop = BooleanVar( value= True )
        self.bot.attack = BooleanVar( value= True )
        self.bot.attack_spells = BooleanVar( value= True )
        self.bot.hp_heal = BooleanVar( value= True )
        self.bot.mp_heal = BooleanVar( value= True )
        self.bot.hp_thresh_high = IntVar( value = 90)
        self.bot.hp_thresh_low = IntVar( value = 70)
        self.bot.mp_thresh = IntVar( value = 40)
        self.bot.waypoint_folder = StringVar(value = "")
        self.bot.cavebot = BooleanVar( value = False)
        # regions Buttons

        self.root.addButton('Update Elements', self.bot.updateAllElements, [120, 20], [20, 50]).configure()
        
        self.root.addEntry([130, 80], self.bot.hp_thresh_high, width=6, validate_function=digitValidation)
        self.root.addLabel(r'% Light', [175, 80])
        self.root.addEntry([130, 105], self.bot.hp_thresh_low, width=6, validate_function=digitValidation)
        self.root.addLabel(r'% Heavy', [175, 105])
        self.root.addEntry([130, 140], self.bot.mp_thresh, width=6, validate_function=digitValidation)
        self.root.addLabel(r'%', [175, 140])
        self.root.addCheck(self.bot.hp_heal, [20, 80], BooleanVar(value = True), "HP Healing")
        self.root.addCheck(self.bot.mp_heal, [20, 140], BooleanVar(value = True), "MP Healing")
        self.root.addCheck(self.bot.attack, [20, 170], BooleanVar(value = True), "Attack (Battle)")
        self.root.addCheck(self.bot.attack_spells, [20, 200], BooleanVar(value = True), "Attack Spells")
        
        self.root.addLabel('Waypoint folder:', [20, 245])
        self.root.addEntry([20, 270], self.bot.waypoint_folder, width=20)
        self.root.addButton('Add Waypoint', Default, [92, 23], [20, 300])
        self.root.addCheck(self.bot.cavebot, [20, 330], BooleanVar(value = False), "Cavebot")

        def Exit():
            
            print("Exiting...")
            self.bot.loop.set(False)
            raise SystemExit

        self.root.addButton('Exit', Exit, [92, 23], [10, 498])
        self.root.Protocol(Exit)
        
        # endregion
    def loop(self):
        self.root.loop()
        
def digitValidation(P):
    if str.isdigit(P) or P == "":
        return True
    else:
        return False
def GUIUpdateAllElements():
    print("Updating all elements from GUI")
def Default():
    print("Clicked a button")