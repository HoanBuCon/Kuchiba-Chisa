"""
Clean and whitelist raw_wiki data to ensure zero noise / zero event stall garbage.
Keeps:
- 100% of Characters (Resonators, Backstory, Forte Reports)
- 100% of Factions
- 100% of Lore
- Whitelisted major macro-regions in Locations (and purges 330+ minor stalls/minigames)
"""

import os
import shutil
import sys
from pathlib import Path

# Major macro-regions to keep in Locations
MAJOR_LOCATION_WHITELIST = {
    "huanglong",
    "jinzhou",
    "mt_firmament",
    "black_shores",
    "black_shores_archipelago",
    "norfall_barrens",
    "port_city_of_guixu",
    "guixu",
    "tigers_maw_mine",
    "tigers_maw",
    "desorock_highland",
    "gorges_of_spirits",
    "central_plains",
    "dim_forest",
    "whining_aixs_mire",
    "waving_glade",
    "mt_pingting",
    "solaris_3",
    "rinascita",
    "raguna",
    "court_of_savantae_ruins",
    "taoyuan_vale",
    "bell_borne_ravine",
}

def clean_raw_wiki():
    loc_dir = Path("data/raw_wiki/Locations")
    if not loc_dir.exists():
        print("Locations folder does not exist.")
        return

    removed_count = 0
    kept_count = 0

    for item in list(loc_dir.iterdir()):
        if item.is_dir():
            folder_slug = item.name.lower()
            if folder_slug not in MAJOR_LOCATION_WHITELIST:
                shutil.rmtree(item)
                removed_count += 1
            else:
                kept_count += 1

    print(f"[+] Cleaned data/raw_wiki/Locations: Removed {removed_count} noisy stalls/sub-areas, Kept {kept_count} major regions.")

if __name__ == "__main__":
    clean_raw_wiki()
