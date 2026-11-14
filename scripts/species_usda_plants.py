"""USDA PLANTS traits for the species pool (public API, no key).

Symbol lookup: the PLANTS checklist file and search endpoint are not scriptable (14 Nov 2026), so
candidate symbols are generated (GGSS, GGSS2..9; genus: first 5 letters) and accepted only when the
returned ScientificName matches the requested name.
Output: data/species/usda_plants_traits.csv  (long format: taxon, symbol, trait, value, cultivar)
        data/species/usda_plants_profile.csv (taxon, symbol, accepted name, native L48)
"""
import re
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
SP = ROOT / "data/species"
API = "https://plantsservices.sc.egov.usda.gov/api"
TRAITS = {"Drought Tolerance", "Shade Tolerance", "Salinity Tolerance", "Anaerobic Tolerance", "Moisture Use",
          "Height, Mature (feet)", "Growth Rate", "Lifespan", "Root Depth, Minimum (inches)", "pH, Minimum", "pH, Maximum",
          "Temperature, Minimum (°F)", "Bloom Period", "Fire Tolerance", "CaCO3 Tolerance", "Hedge Tolerance",
          "Adapted to Coarse Textured Soils", "Adapted to Medium Textured Soils", "Adapted to Fine Textured Soils",
          "Toxicity", "Foliage Porosity Summer", "Shape and Orientation", "Fruit/Seed Abundance", "Growth Form"}


def clean(name):
    n = re.sub(r"'.*?'", "", name).replace(" spp.", "").replace(" sp.", "").replace(" x ", " ").strip()
    n = re.sub(r"\s+var\..*", "", n)
    return " ".join(n.split()[:2])


def profile(sym):
    r = requests.get(f"{API}/PlantProfile", params={"symbol": sym}, timeout=60)
    if r.status_code != 200 or not r.text.strip().startswith("{"):
        return None
    return r.json()


def find(name):
    parts = clean(name).split()
    g = parts[0]
    if len(parts) == 1:
        cands = [g[:5].upper()]
    else:
        base = (g[:2] + parts[1][:2]).upper()
        cands = [base] + [f"{base}{i}" for i in range(2, 10)]
    target = clean(name).lower()
    for s in cands:
        p = profile(s)
        if p and re.sub(r"<.*?>", "", p.get("ScientificName") or "").lower().startswith(target):
            return s, p
    return None, None


pool = pd.read_csv(SP / "species_pool.csv")
prof_rows, trait_rows = [], []
for name in pool.scientific:
    sym, p = find(name)
    if not p:
        prof_rows.append({"taxon": name, "symbol": None}); print("not found:", name); continue
    accepted_id = p.get("AcceptedId") or p["Id"]
    nat = {s["Region"]: s["Status"] for s in (p.get("NativeStatuses") or [])}
    prof_rows.append({"taxon": name, "symbol": sym, "plants_name": re.sub(r"<.*?>", "", p.get("ScientificName") or ""),
                      "native_L48": nat.get("L48"), "growth_habits": ";".join(p.get("GrowthHabits") or [])})
    ch = requests.get(f"{API}/PlantCharacteristics/{accepted_id}", timeout=60)
    for c in (ch.json() if ch.status_code == 200 and ch.text.startswith("[") else []):
        if c["PlantCharacteristicName"] in TRAITS:
            trait_rows.append({"taxon": name, "symbol": sym, "trait": c["PlantCharacteristicName"],
                               "value": c["PlantCharacteristicValue"], "cultivar": c.get("CultivarName")})
    print(name, sym, nat.get("L48"), sum(r["taxon"] == name for r in trait_rows), "traits")

pd.DataFrame(prof_rows).to_csv(SP / "usda_plants_profile.csv", index=False)
pd.DataFrame(trait_rows).to_csv(SP / "usda_plants_traits.csv", index=False)
