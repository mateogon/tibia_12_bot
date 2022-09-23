from GUI import *
from tkinter import BooleanVar
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
        
        # regions Buttons

        self.root.addButton('Update Elements', self.bot.updateAllElements, [92, 23], [23, 56]).configure()
        self.root.addButton('Color Change', Default, [92, 23], [23, 108]).configure(state='disabled')
        self.root.addButton('Ammo Restack', Default, [92, 23], [23, 135]).configure(state='disabled')
        self.root.addButton('Auto Looter', Default, [92, 23], [23, 160]).configure(state='disabled')
    
        self.root.addButton('Food Eater', Default, [92, 23], [23, 210])
        self.root.addButton('Auto Grouping', Default, [92, 23], [23, 236]).configure(state='disabled')
        self.root.addButton('Sort Loot', Default, [92, 23], [23, 262]).configure(state='disabled')
        self.root.addButton('Auto Banker', Default, [92, 23], [23, 288]).configure(state='disabled')
        self.root.addButton('Auto Seller', Default, [92, 23], [23, 340]).configure(state='disabled')
        self.root.addButton('FPS Changer', Default, [92, 23], [23, 366]).configure(state='disabled')

        self.root.addButton('Auto Life', Default, [92, 23], [147, 56])
        #h = BooleanVar(value = True)
        #m = BooleanVar(value = True)
        
        healHP = self.root.addCheck(self.bot.hp_heal, [245, 56], BooleanVar(value = True), "HP Healing")
        healMana = self.root.addCheck(self.bot.mp_heal, [245, 83], BooleanVar(value = True), "MP Healing")
        attack = self.root.addCheck(self.bot.attack, [245, 110], BooleanVar(value = True), "Attack (Battle)")
        attackSpells = self.root.addCheck(self.bot.attack_spells, [245, 137], BooleanVar(value = True), "Attack Spells")
        #self.root.addButton('Auto Hur', Default, [92, 23], [245, 56])
        self.root.addButton('Auto Mana', Default, [92, 23], [147, 83])
        
        self.root.addButton('Auto Amulet', Default, [92, 23], [147, 108])
        self.root.addButton('Timed Spells', Default, [92, 23], [147, 135])

        self.root.addButton('Creature Info', Default, [92, 23], [147, 188]).configure(state='disabled')
        self.root.addButton('Monsters', Default, [92, 23], [245, 188]).configure(state='disabled')

        self.root.addButton('Show Map', Default, [92, 23], [147, 290]).configure(state='disabled')
        self.root.addButton('Cave Bot', Default, [92, 23], [245, 290])

        self.root.addButton('Load Config', Default, [92, 23], [147, 340]).configure(state='disabled')
        self.root.addButton('Save Config', Default, [92, 23], [245, 340]).configure(state='disabled')
        self.root.addButton('Adjust Config', Default, [92, 23], [147, 366]).configure(state='disabled')
        self.root.addButton('Modules', Default, [92, 23], [245, 366]).configure(state='disabled')
        self.root.addButton('Python Scripts', Default, [92, 23], [245, 392]).configure(state='disabled')

        self.root.addButton('General Options', Default, [213, 23], [134, 426]).configure(state='disabled')

        def Exit():
            
            print("Exiting...")
            self.bot.loop.set(False)
            raise SystemExit

        self.root.addButton('Exit', Exit, [92, 23], [10, 498])
        self.root.Protocol(Exit)
        
        # endregion
    def loop(self):
        self.root.loop()
def GUIUpdateAllElements():
    print("Updating all elements from GUI")
def Default():
    print("Clicked a button")