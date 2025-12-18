import numpy as np
class BotConstants:
    # Colors
    HP_COLORS = ((0, 192, 0), (96, 192, 96), (192, 192, 0), (192, 0, 0), (192, 48, 48), (96, 0, 0), (192, 192, 192))
    LOW_HP_COLORS = ((192, 192, 0), (192, 0, 0), (192, 48, 48), (96, 0, 0))
    
    PARTY_COLORS = {
        "cross": {"leader2": (190, 137, 26), "leader": (242, 9, 3), "follower": (255, 4, 1)},
        "check": {"leader2": (255, 149, 16), "leader": (27, 254, 21), "follower": (13, 255, 11)}
    }

    # Relative Offsets (Left, Top, Right, Bottom)
    OFFSETS = {
        "Map":           (-118, -259, -52, -161),
        "Bless":         (-104, -144, -135, -147),
        "Buffs":         (-118, 0, -53, -1),
        "Health":        (-103, +18, -53, +14),
        "Mana":          (-103, +31, -53, +27),
        "Capacity":      (-45, -13, -52, -15),
        "WindowButtons": (-118, 71, -52, 164)
    }

    # 1 = Hit, 0 = Empty
    RUNE_MASK = np.array([
        [0, 0, 1, 1, 1, 0, 0],
        [0, 1, 1, 1, 1, 1, 0],
        [1, 1, 1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1, 1, 1],
        [0, 1, 1, 1, 1, 1, 0],
        [0, 0, 1, 1, 1, 0, 0]
    ])

    # --- 1. DEFINE TERRAIN COLORS ---
    # Obstacles (BGR)
    OBSTACLES = [[0, 51, 255], [0, 0, 0], [102, 102, 102], [0, 51, 153], [153, 102, 51]]
    
    # Walkable (Converted from your Hex to BGR)
    WALKABLE = [
        [153, 204, 255], # FFCC99 -> BGR
        [0, 204, 0],     # 00CC00
        [153, 153, 153], # 999999
        [153, 102, 51],  # 336699
        [0, 102, 0],     # 006600
        [255, 255, 204], # CCFFFF
        [255, 255, 255], # FFFFFF
        [51, 102, 153],  # 996633
        [0, 255, 255]    # FFFF00
    ]