# FO76 Reference Data — legendary mod effects and mutations
# Used to populate <datalist> autocomplete on weapon, armor, and mutation forms.
# Verified against nukaknights.com and fallout.wiki (2026-03).

# ── Weapon Legendary Effects ──────────────────────────────────────────────────

WEAPON_STAR1 = sorted([
    "Adrenal", "Anti-Armor", "Aristocrat's", "Assassin's", "Berserker's",
    "Bloodied", "Executioner's", "Exterminator's", "Feral's", "Furious",
    "Ghoul Slayer's", "Gourmand's", "Hunter's", "Instigating", "Juggernaut's",
    "Junkie's", "Medic's", "Mutant Slayer's", "Mutant's", "Nocturnal",
    "Quad", "Sniper's", "Stalker's", "Suppressor's", "Troubleshooter's",
    "Two Shot", "Vampire's", "Zealot's",
])

WEAPON_STAR2 = sorted([
    "Basher's", "Crippling", "Explosive", "Heavy Hitter's", "Hitman's",
    "Inertial", "Last Shot", "Rapid", "Steady", "V.A.T.S. Enhanced", "Vital",
])

WEAPON_STAR3 = sorted([
    "Arms Keeper's", "Barbarian", "Belted", "Durability", "Lightweight",
    "Lucky", "Nimble", "Swift", "V.A.T.S. Optimized",
])

WEAPON_STAR4 = sorted([
    "Battle-Loader's", "Bruiser's", "Bully's", "Charged", "Choo-Choo's",
    "Combo-Breaker's", "Conductor's", "Electrician's", "Encircler's",
    "Fencer's", "Fracturer's", "Icemen's", "Pin-Pointer's", "Polished",
    "Pounder's", "Pyromaniac's", "Ranger's", "Stabilizer's", "Thrill-Seeker's",
    "Viper's",
])

# ── Armor Legendary Effects ───────────────────────────────────────────────────

ARMOR_STAR1 = sorted([
    "Adrenal", "Assassin's", "Auto Stim", "Bolstering", "Chameleon",
    "Cloaking", "Exterminator's", "Ghoul Slayer's", "Gourmand's", "Heavyweight",
    "Hunter's", "Juggernaut's", "Life Saving", "Lucid", "Mutant Slayer's",
    "Mutant's", "Nocturnal", "Overeater's", "Regenerating", "Troubleshooter's",
    "Unyielding", "Vanguard's", "Zealot's",
])

ARMOR_STAR2 = sorted([
    "Agility", "Antiseptic", "Charisma", "Elementalist", "Endurance",
    "Fierce", "Fireproof", "Glutton", "Hardy", "HazMat", "Intelligence",
    "Luck", "Pain Killer", "Perception", "Pick Pocketer's", "Poisoner's",
    "Powered", "Riposting", "Rushing", "Strength", "Warming",
])

ARMOR_STAR3 = sorted([
    "Acrobat's", "Active", "Adamantium", "Agility", "Barbarian", "Belted",
    "Blocker", "Burning", "Cavalier's", "Charisma", "Defender's", "Dissipating",
    "Diver's", "Doctor's", "Durability", "Electrified", "Endurance", "Frozen",
    "Ghost's", "Glowing", "Healthy", "Intelligence", "Luck", "Nimble",
    "Pack Rat's", "Perception", "Reflex", "Resilient", "Safecracker's",
    "Secret Agent's", "Sentinel's", "Steadfast", "Strength", "Thru-hiker's",
    "Toxic",
])

ARMOR_STAR4 = sorted([
    "Aegis", "Limit-Breaking", "Miasma's", "Propelling", "Radioactive-Powered",
    "Reflective", "Rejuvenator's", "Runner's", "Sawbones's", "Scanner's",
    "Stalwart's", "Tanky's",
])

# ── Mutations ─────────────────────────────────────────────────────────────────
# (name, positive effect, negative effect)

MUTATIONS = [
    ("Adrenal Reaction",   "+5% weapon damage per kill streak",                        "-50 max HP"),
    ("Bird Bones",         "+4 AGI, +40 AP, softer landings",                          "-4 STR, +20% incoming limb damage"),
    ("Carnivore",          "Meat gives double benefit, no disease from meat",           "Vegetables give no benefit"),
    ("Chameleon",          "Invisible when crouched, still, and unarmored",             "Must be stationary and not attacking"),
    ("Eagle Eyes",         "+25% critical damage, +4 PER",                             "-4 STR"),
    ("Egg Head",           "+6 INT",                                                   "-3 STR, -3 END"),
    ("Electrically Charged","Chance to shock melee attackers on hit",                  "Shock deals small energy damage to player"),
    ("Empath",             "Teammates take 25% less damage",                           "Player takes 33% more damage"),
    ("Grounded",           "+100 Energy Resistance",                                   "-50% Energy weapon damage"),
    ("Healing Factor",     "+300% natural HP regen",                                   "-55% Chem effectiveness"),
    ("Herbivore",          "Vegetables give double benefit, no disease from vegetables","Meat gives no benefit"),
    ("Herd Mentality",     "+2 all SPECIAL when grouped with other players",           "-2 all SPECIAL when playing solo"),
    ("Marsupial",          "+20 Carry Weight, jump much higher",                       "-4 INT"),
    ("Plague Walker",      "Poison aura that scales with number of active diseases",   "None (requires being diseased)"),
    ("Scaly Skin",         "+50 DR and ER",                                            "-50 AP"),
    ("Speed Demon",        "+20% move speed and reload speed",                         "+50% Hunger and Thirst accumulation while moving"),
    ("Talons",             "+25% unarmed damage, attacks cause bleeding",              "-4 AGI"),
    ("Twisted Muscles",    "+25% melee damage, chance to cripple on hit",              "-50% gun accuracy"),
    ("Unstable Isotope",   "10% chance to release radiation blast when struck",        "Radiation blast also irradiates the player"),
]

MUTATION_NAMES = sorted([m[0] for m in MUTATIONS])

# ── Weapon Shorthand Decoder ───────────────────────────────────────────────────
# Maps community trading abbreviations to (full_name, description) tuples.
# Positional: STAR1 = prefix/damage, STAR2 = secondary effect, STAR3 = perk/utility

SHORTHAND_STAR1 = {
    # Bloodied
    'B': ('Bloodied', 'Damage scales up as your health drops — max +95% at 1 HP'),
    'BL': ('Bloodied', 'Damage scales up as your health drops — max +95% at 1 HP'),
    'BLD': ('Bloodied', 'Damage scales up as your health drops — max +95% at 1 HP'),
    # Anti-Armor
    'AA': ("Anti-Armor", "Ignores 50% of the target's armor"),
    'AAR': ("Anti-Armor", "Ignores 50% of the target's armor"),
    # Quad
    'Q': ('Quad', '+300% magazine capacity'),
    'QD': ('Quad', '+300% magazine capacity'),
    # Two Shot
    'TS': ('Two Shot', 'Fires an extra projectile per shot'),
    '2S': ('Two Shot', 'Fires an extra projectile per shot'),
    # Vampire's
    'V': ("Vampire's", 'Heals you on every hit'),
    'VMP': ("Vampire's", 'Heals you on every hit'),
    'VAMP': ("Vampire's", 'Heals you on every hit'),
    # Junkie's
    'J': ("Junkie's", '+Damage for each active addiction'),
    'JNK': ("Junkie's", '+Damage for each active addiction'),
    'JUNK': ("Junkie's", '+Damage for each active addiction'),
    # Furious
    'F': ('Furious', '+Damage per consecutive hit on the same target'),
    'FUR': ('Furious', '+Damage per consecutive hit on the same target'),
    # Executioner's
    'E': ("Executioner's", '+50% damage when target is below 40% health'),
    'EXE': ("Executioner's", '+50% damage when target is below 40% health'),
    'EXEC': ("Executioner's", '+50% damage when target is below 40% health'),
    # Aristocrat's
    'ARI': ("Aristocrat's", '+Damage when at max caps (30,000)'),
    'ARIS': ("Aristocrat's", '+Damage when at max caps (30,000)'),
    'ARS': ("Aristocrat's", '+Damage when at max caps (30,000)'),
    # Instigating
    'INS': ('Instigating', 'Double damage if target is at full health'),
    'INST': ('Instigating', 'Double damage if target is at full health'),
    # Berserker's
    'BER': ("Berserker's", '+Damage the less armor you wear'),
    'BERS': ("Berserker's", '+Damage the less armor you wear'),
    # Assassin's
    'AS': ("Assassin's", '+10% damage vs players'),
    'ASS': ("Assassin's", '+10% damage vs players'),
    'ASN': ("Assassin's", '+10% damage vs players'),
    # Suppressor's
    'SUP': ("Suppressor's", 'Reduces target damage output by 20% for 3 seconds'),
    # Exterminator's
    'EXT': ("Exterminator's", '+50% damage vs bugs, bots, and mirelurks'),
    # Mutant Slayer's
    'MS': ("Mutant Slayer's", '+50% damage vs super mutants'),
    'MTS': ("Mutant Slayer's", '+50% damage vs super mutants'),
    'MUTS': ("Mutant Slayer's", '+50% damage vs super mutants'),
    # Mutant's
    'MUT': ("Mutant's", '+Damage for each active mutation you have'),
    # Nocturnal
    'NOC': ('Nocturnal', '+Damage at night, -Damage during the day'),
    'NOCT': ('Nocturnal', '+Damage at night, -Damage during the day'),
    # Hunter's
    'HUNT': ("Hunter's", '+50% damage vs animals'),
    'HNT': ("Hunter's", '+50% damage vs animals'),
    # Medic's
    'MED': ("Medic's", 'Stimpaks restore more health when used'),
    # Juggernaut's
    'JUG': ("Juggernaut's", '+Damage the more items you have in your inventory'),
    'JUGG': ("Juggernaut's", '+Damage the more items you have in your inventory'),
    # Troubleshooter's
    'TRO': ("Troubleshooter's", '+50% damage vs robots'),
    'TRB': ("Troubleshooter's", '+50% damage vs robots'),
    # Stalker's
    'STK': ("Stalker's", '+50% VATS accuracy when not in combat'),
    'STALK': ("Stalker's", '+50% VATS accuracy when not in combat'),
    # Sniper's
    'SNP': ("Sniper's", '+10% critical damage, better stability'),
    'SNIP': ("Sniper's", '+10% critical damage, better stability'),
    # Adrenal
    'ADR': ('Adrenal', 'Increases fire rate when health drops below 50%'),
    'ADREN': ('Adrenal', 'Increases fire rate when health drops below 50%'),
    # Gourmand's
    'GOR': ("Gourmand's", '+Damage when well-fed and hydrated'),
    'GOUR': ("Gourmand's", '+Damage when well-fed and hydrated'),
    # Feral's
    'FRL': ("Feral's", '+Damage vs feral ghouls'),
    'FER': ("Feral's", '+Damage vs feral ghouls'),
    # Zealot's
    'Z': ("Zealot's", '+50% damage vs scorched'),
    'ZLT': ("Zealot's", '+50% damage vs scorched'),
    'ZEAL': ("Zealot's", '+50% damage vs scorched'),
    # Ghoul Slayer's
    'GS': ("Ghoul Slayer's", '+50% damage vs ghouls'),
    'GSS': ("Ghoul Slayer's", '+50% damage vs ghouls'),
    'GHS': ("Ghoul Slayer's", '+50% damage vs ghouls'),
}

SHORTHAND_STAR2 = {
    '25': ('Rapid', '25% faster fire rate'),
    'FFR': ('Rapid', '25% faster fire rate'),
    'RAPID': ('Rapid', '25% faster fire rate'),
    '50C': ('Vital', '50% more critical hit damage'),
    'CRIT': ('Vital', '50% more critical hit damage'),
    'VIT': ('Vital', '50% more critical hit damage'),
    'E': ('Explosive', 'Bullets explode on impact for area damage'),
    'EXP': ('Explosive', 'Bullets explode on impact for area damage'),
    'EXPL': ('Explosive', 'Bullets explode on impact for area damage'),
    'LS': ('Last Shot', 'Last round in magazine deals 25% more damage'),
    'LAST': ('Last Shot', 'Last round in magazine deals 25% more damage'),
    'VE': ('V.A.T.S. Enhanced', '+33% hit chance in VATS'),
    'BASH': ("Basher's", '+40% bash damage'),
    'BSH': ("Basher's", '+40% bash damage'),
    'CRIP': ('Crippling', '+50% limb damage'),
    'CRP': ('Crippling', '+50% limb damage'),
    'HH': ("Heavy Hitter's", '+40% damage but -20% attack speed (melee)'),
    'HHT': ("Heavy Hitter's", '+40% damage but -20% attack speed (melee)'),
    'HIT': ("Hitman's", '+10% damage while aiming down sights'),
    'HTM': ("Hitman's", '+10% damage while aiming down sights'),
    'HITMAN': ("Hitman's", '+10% damage while aiming down sights'),
    'INERT': ('Inertial', '+30% VATS AP refill on kill'),
    'IRT': ('Inertial', '+30% VATS AP refill on kill'),
    'STEADY': ('Steady', '+25% aim stability while targeting'),
    'STD': ('Steady', '+25% aim stability while targeting'),
}

SHORTHAND_STAR3 = {
    '25': ('V.A.T.S. Optimized', '-25% VATS AP cost per shot'),
    'VAP': ('V.A.T.S. Optimized', '-25% VATS AP cost per shot'),
    'AP': ('V.A.T.S. Optimized', '-25% VATS AP cost per shot'),
    'VATS': ('V.A.T.S. Optimized', '-25% VATS AP cost per shot'),
    '90': ('Lightweight', '-90% weapon weight'),
    'LWT': ('Lightweight', '-90% weapon weight'),
    'LIGHT': ('Lightweight', '-90% weapon weight'),
    'WT': ('Lightweight', '-90% weapon weight'),
    '15R': ('Swift', '+15% faster reload speed'),
    'RLD': ('Swift', '+15% faster reload speed'),
    'RELOAD': ('Swift', '+15% faster reload speed'),
    'SWIFT': ('Swift', '+15% faster reload speed'),
    'DUR': ('Durability', 'Weapon breaks 50% slower'),
    'LUCKY': ('Lucky', '+50% chance of legendary items from enemies'),
    'LCK': ('Lucky', '+50% chance of legendary items from enemies'),
    'NIMBLE': ('Nimble', '+75% movement speed while in VATS'),
    'NMB': ('Nimble', '+75% movement speed while in VATS'),
    'BARB': ('Barbarian', '+40 Damage Resistance when not wearing armor'),
    'BRB': ('Barbarian', '+40 Damage Resistance when not wearing armor'),
    'BELTED': ('Belted', 'Chance to gain bonus ammo from enemies'),
    'BLT': ('Belted', 'Chance to gain bonus ammo from enemies'),
    'ARK': ("Arms Keeper's", '-20% ammo weight'),
    'AK': ("Arms Keeper's", '-20% ammo weight'),
    'ARMS': ("Arms Keeper's", '-20% ammo weight'),
}

# Common weapon name aliases (uppercase key → display name)
WEAPON_ALIASES = {
    # Rifles
    'RAIL': 'Railway Rifle', 'RAILWAY': 'Railway Rifle',
    'HM': 'Handmade Rifle', 'HANDMADE': 'Handmade Rifle',
    'FIXER': 'The Fixer', 'FIX': 'The Fixer',
    'CR': 'Combat Rifle', 'COMBAT RIFLE': 'Combat Rifle',
    'LEVER': 'Lever Action Rifle', 'LAR': 'Lever Action Rifle',
    'HR': 'Hunting Rifle', 'HUNTING': 'Hunting Rifle',
    'AR': 'Assault Rifle', 'ASSLT': 'Assault Rifle',
    'GAUSS': 'Gauss Rifle', 'GR': 'Gauss Rifle',
    'TESLA': 'Tesla Rifle',
    # Pistols
    '10MM': '10mm Pistol',
    '44': '.44 Pistol', 'REVOLVER': '.44 Pistol',
    'PIPE': 'Pipe Pistol',
    'GPP': 'Gauss Plasma Pistol',
    'ENCL': 'Enclave Plasma Gun', 'EPG': 'Enclave Plasma Gun',
    # Heavy
    'MINI': 'Minigun', 'MINIGUN': 'Minigun',
    'LMG': 'Light Machine Gun',
    '50CAL': '.50 Cal Machine Gun',
    'GAT': 'Gatling Gun', 'GATLING': 'Gatling Gun',
    'GP': 'Gatling Plasma', 'GATPLASMA': 'Gatling Plasma',
    'GL': 'Gatling Laser', 'GLP': 'Gatling Laser', 'GATLASER': 'Gatling Laser',
    'FAT': 'Fat Man', 'FATMAN': 'Fat Man',
    'ML': 'Missile Launcher', 'MISSILE': 'Missile Launcher',
    'PC': 'Plasma Caster',
    'GMINI': 'Gauss Minigun',
    # Bows
    'BOW': 'Compound Bow', 'CBOW': 'Compound Bow',
    'XBOW': 'Crossbow', 'CROSSBOW': 'Crossbow',
    # Shotguns
    'SHOTGUN': 'Combat Shotgun',
    'DB': 'Double-Barrel Shotgun',
    'PUMP': 'Pump Shotgun',
    'GSHOT': 'Gauss Shotgun', 'GSHOTGUN': 'Gauss Shotgun',
    # Energy
    'PLASMA': 'Plasma Rifle',
    'FLAMER': 'Flamer',
    'CRYO': 'Cryolator',
    # Melee
    'SS': 'Super Sledge', 'SLEDGE': 'Super Sledge',
    'PF': 'Power Fist',
    'BEAR': 'Bear Arm',
    'MMG': 'Mole Miner Gauntlet',
    'DCG': 'Deathclaw Gauntlet',
    'RIPPER': 'Ripper',
    'CHAINSAW': 'Chainsaw',
}

# Our readable shorthand codes (full name → our code)
OUR_CODE_STAR1 = {
    'Bloodied': 'BLD', "Anti-Armor": 'AAR', 'Quad': 'QD',
    'Two Shot': 'TS', "Vampire's": 'VMP', "Junkie's": 'JNK',
    'Furious': 'FUR', "Executioner's": 'EXE', "Aristocrat's": 'ARS',
    'Instigating': 'INS', "Berserker's": 'BER', "Assassin's": 'ASN',
    "Suppressor's": 'SUP', "Exterminator's": 'EXT', "Mutant Slayer's": 'MTS',
    "Mutant's": 'MUT', 'Nocturnal': 'NOC', "Hunter's": 'HNT',
    "Medic's": 'MED', "Juggernaut's": 'JUG', "Troubleshooter's": 'TRB',
    "Stalker's": 'STK', "Sniper's": 'SNP', 'Adrenal': 'ADR',
    "Gourmand's": 'GOR', "Feral's": 'FRL', "Zealot's": 'ZLT',
    "Ghoul Slayer's": 'GHS',
}

OUR_CODE_STAR2 = {
    'Rapid': 'FFR', 'Vital': 'CRT', 'Explosive': 'EXP',
    'Last Shot': 'LST', 'V.A.T.S. Enhanced': 'VEH',
    "Basher's": 'BSH', 'Crippling': 'CRP', "Heavy Hitter's": 'HHT',
    "Hitman's": 'HTM', 'Inertial': 'IRT', 'Steady': 'STD',
}

OUR_CODE_STAR3 = {
    'V.A.T.S. Optimized': 'VAP', 'Lightweight': 'LWT', 'Swift': 'RLD',
    'Durability': 'DUR', 'Lucky': 'LCK', 'Nimble': 'NMB',
    'Barbarian': 'BRB', 'Belted': 'BLT', "Arms Keeper's": 'ARK',
}

SHORTHAND_STAR4 = {
    'BTL': ("Battle-Loader's", 'Reloading refills AP'),
    'BRS': ("Bruiser's", '+Damage scaling with STR for melee'),
    'BLY': ("Bully's", '+Damage vs humans'),
    'CHG': ('Charged', 'Shots have a chance to shock nearby enemies'),
    'CCH': ("Choo-Choo's", 'Shots ricochet to nearby enemies'),
    'CMB': ("Combo-Breaker's", 'Chance to stagger on consecutive hits'),
    'CND': ("Conductor's", 'Kills build a damage aura'),
    'ELC': ("Electrician's", '+Energy damage on hits'),
    'ENC': ("Encircler's", '+Damage when surrounded by enemies'),
    'FNC': ("Fencer's", 'Melee attacks have a chance to disarm'),
    'FRC': ("Fracturer's", '+Damage vs armored targets'),
    'ICE': ("Icemen's", 'Slows targets on hit'),
    'PIN': ("Pin-Pointer's", '+Limb damage in VATS'),
    'POL': ('Polished', '+Charisma when weapon is drawn'),
    'PND': ("Pounder's", 'Melee attacks deal bonus concussive damage'),
    'PYR': ("Pyromaniac's", 'Shots have a chance to ignite targets'),
    'RNG': ("Ranger's", '+Damage when moving'),
    'STB': ("Stabilizer's", '+Accuracy and less recoil while aiming'),
    'THL': ("Thrill-Seeker's", '+Damage when on a kill streak'),
    'VPR': ("Viper's", 'Attacks cause bleeding damage over time'),
}

OUR_CODE_STAR4 = {
    "Battle-Loader's": 'BTL', "Bruiser's": 'BRS', "Bully's": 'BLY',
    'Charged': 'CHG', "Choo-Choo's": 'CCH', "Combo-Breaker's": 'CMB',
    "Conductor's": 'CND', "Electrician's": 'ELC', "Encircler's": 'ENC',
    "Fencer's": 'FNC', "Fracturer's": 'FRC', "Icemen's": 'ICE',
    "Pin-Pointer's": 'PIN', 'Polished': 'POL', "Pounder's": 'PND',
    "Pyromaniac's": 'PYR', "Ranger's": 'RNG', "Stabilizer's": 'STB',
    "Thrill-Seeker's": 'THL', "Viper's": 'VPR',
}
