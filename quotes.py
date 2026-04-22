import random

QUOTES = [
    # ── Mr. Gutsy ──────────────────────────────────────────────────────────────
    ("Does someone's ass need to be kicked?",                            "Mr. Gutsy"),
    ("Communism is a blight on the buttocks of democracy!",              "Mr. Gutsy"),
    ("Nothing like the sight of a few dead communists to brighten the day!", "Mr. Gutsy"),
    ("I am fully combat-operational and ready to kill communists!",      "Mr. Gutsy"),
    ("Shoot 'em in the head! Or the legs! Anywhere, really!",           "Mr. Gutsy"),
    ("Ah, the sweet smell of a functioning democracy!",                  "Mr. Gutsy"),
    ("Move it, soldier! I've got a war to win!",                        "Mr. Gutsy"),

    # ── Codsworth ──────────────────────────────────────────────────────────────
    ("Pip pip, cheerio! Another fine day in the wasteland!",            "Codsworth"),
    ("I've been polishing the silver for 210 years. It is VERY shiny.", "Codsworth"),
    ("I do hope you haven't been using the good china as a shield again.", "Codsworth"),
    ("Technically I'm still on the clock. Two hundred years of overtime.", "Codsworth"),

    # ── Super Mutants ──────────────────────────────────────────────────────────
    ("SUPER MUTANTS STRONGEST!",                                         "Super Mutant"),
    ("Me no stupid. Me just... big-brained.",                           "Super Mutant"),
    ("Tiny human talk too much. Super Mutant smash.",                   "Super Mutant"),
    ("Why smoothskin always running? Super Mutant just want hug.",      "Super Mutant"),

    # ── Vault-Tec ─────────────────────────────────────────────────────────────
    ("Vault-Tec: because the end of the world doesn't have to be unpleasant!", "Vault-Tec"),
    ("Remember: a well-tracked inventory is a well-surviving vault dweller.", "Vault-Tec"),
    ("Vault-Tec Tip: RadAway is not a cocktail mixer. Results were... mixed.", "Vault-Tec"),
    ("Vault-Tec Tip: If you can read this, you survived. Congratulations!", "Vault-Tec"),
    ("Vault-Tec does not recommend trading with strangers. Unless they have good loot.", "Vault-Tec"),
    ("Please rate your apocalypse experience 5 stars.",                 "Vault-Tec Survey Bot"),
    ("Overseer not responsible for any existential dread caused by outside world.", "Vault-Tec Disclaimer"),
    ("Have you tried turning the nuclear reactor off and on again?",    "Vault-Tec Tech Support"),
    ("Nuka-Cola: it's the REAL thing. Radiation and all.",             "Nuka-Cola Corp"),
    ("Vault-Tec: keeping families safe since before we knew this would happen.", "Vault-Tec"),

    # ── Three Dog (Fallout 3) ──────────────────────────────────────────────────
    ("Good fight the good fight, baby!",                                "Three Dog, GNR"),
    ("This is Galaxy News Radio, and I am your host, Three Dog. Awoooooo!", "Three Dog, GNR"),

    # ── Ron Perlman ────────────────────────────────────────────────────────────
    ("War. War never changes.",                                          "Ron Perlman"),
    ("War. War never changes... but the loot certainly does.",          "Ron Perlman (probably)"),

    # ── Wasteland Wisdom ───────────────────────────────────────────────────────
    ("The giant scorpions were NOT in the brochure.",                   "Every Vault Dweller, ever"),
    ("I don't want to set the world on fire. Too late.",               "Every Vault Dweller, ever"),
    ("This is fine.",                                                    "Every Appalachian Resident"),
    ("Note to self: 'glowing' is not a good sign.",                    "Wasteland Survival Guide"),
    ("Turns out, the real treasure was the caps we looted along the way.", "Wasteland Proverb"),
    ("If it's irradiated and still moving, it probably wants to eat you.", "Wasteland Survival Guide"),
    ("A locked door is just a suggestion.",                             "The Sole Survivor"),
    ("Never go full scorchbeast.",                                      "Appalachian Survival Tip"),
    ("Vendor says 40,000 cap limit. Vendor has trust issues.",         "Every FO76 Trader"),
    ("I have 47 units of pre-war money. I feel incredibly poor.",      "Every FO76 Player"),
    ("The Brotherhood wants my junk. Story of my life.",               "Every FO76 Player"),

    # ── Fallout TV Show ────────────────────────────────────────────────────────
    ("It's a good day to be alive. Mostly because yesterday really wasn't.", "Lucy MacLean"),
    ("The wasteland is full of surprises. None of them good.",         "Cooper Howard / The Ghoul"),
    ("Optimism is a pre-war luxury.",                                   "Cooper Howard / The Ghoul"),
]


def get_random():
    quote, speaker = random.choice(QUOTES)
    return {'quote': quote, 'speaker': speaker}
