"""Assemble the species knowledge base (module 2) with provenance.

Rule: every value has a source; unknown = empty (null), never guessed.
Inputs (data/species/): species_pool.csv, nyc_parks_approved_species.csv, bronx_census2015_by_species.csv,
        usda_plants_profile.csv, usda_plants_traits.csv
Outputs:
  data/species/species_kb.csv          wide table, one row per taxon
  data/species/species_kb_evidence.csv long table: taxon, field, value, source_id
  data/species/sources.csv             source registry
"""
import hashlib
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SP = ROOT / "data/species"
ACC = "2026-11-14"

SOURCES = pd.DataFrame([
    ("NYCP_LIST", "NYC Parks. Street Tree Planting Approved Species List.", "https://www.nycgovparks.org/trees/street-tree-planting/species-list"),
    ("NYC_CENSUS15", "NYC Parks & Recreation. 2015 Street Tree Census - Tree Data (NYC Open Data uvpi-gqnh), Bronx aggregates.", "https://data.cityofnewyork.us/d/uvpi-gqnh"),
    ("NYC_TREEPTS", "NYC Parks. Forestry Tree Points (NYC Open Data hn5i-inap), Area A core.", "https://data.cityofnewyork.us/d/hn5i-inap"),
    ("USDA_PLANTS", "USDA NRCS. The PLANTS Database (PlantProfile / PlantCharacteristics API).", "https://plants.usda.gov"),
    ("APHIS_ALB", "USDA APHIS (2015, April 27). DA-2015-22: Updated list of regulated articles for Asian longhorned beetle.", "https://www.aphis.usda.gov/sites/default/files/DA-2015-22.pdf"),
    ("APHIS_EAB", "USDA APHIS. Emerald ash borer (ash trees, Fraxinus).", "https://www.aphis.usda.gov/plant-pests-diseases/eab"),
], columns=["source_id", "citation", "url"]).assign(accessed=ACC)

ALB = {"Fraxinus", "Betula", "Ulmus", "Koelreuteria", "Aesculus", "Cercidiphyllum", "Acer", "Albizia", "Sorbus", "Populus", "Platanus", "Salix"}

pool = pd.read_csv(SP / "species_pool.csv")
nyc = pd.read_csv(SP / "nyc_parks_approved_species.csv")
cen = pd.read_csv(SP / "bronx_census2015_by_species.csv")
prof = pd.read_csv(SP / "usda_plants_profile.csv")
tr = pd.read_csv(SP / "usda_plants_traits.csv")


def base(n):
    n = re.sub(r"'.*?'", "", str(n)).replace(" spp.", "").replace(" sp.", "").strip()
    return " ".join(n.split())


def genus(n):
    return base(n).split()[0]


ev = []


def put(taxon, field, value, src):
    if pd.notna(value) and value != "":
        ev.append({"taxon": taxon, "field": field, "value": value, "source_id": src})


# core composition for diversity checks (living trees in Area A core)
s = gpd.read_file(ROOT / "data/processed/sites_area_a.gpkg")
core = s[(s.in_core.astype(str) == "True") & (s.site_class == "living_tree")].copy()
core["sci"] = core.tree_species.str.split(" - ").str[0]
core["genus"] = core.sci.str.split().str[0]
n_core = len(core)
sp_share = core.sci.value_counts() / n_core * 100
gen_share = core.genus.value_counts() / n_core * 100

cen["key"] = cen.census_name.map(base)
NYC_FIELDS = ["common", "size_class", "mature_height_class_ft", "form", "growth_rate", "tol_salt", "tol_drought", "tol_wet",
              "tol_wind", "tol_pollution", "tol_high_ph", "tol_shade", "loc_median", "loc_narrow_space", "loc_small_pit_lt3ft", "notes"]
USDA_FIELDS = {"Drought Tolerance": "usda_drought_tol", "Shade Tolerance": "usda_shade_tol", "Salinity Tolerance": "usda_salinity_tol",
               "Anaerobic Tolerance": "usda_anaerobic_tol", "Moisture Use": "usda_moisture_use", "Height, Mature (feet)": "usda_mature_height_ft",
               "Growth Rate": "usda_growth_rate", "Lifespan": "usda_lifespan", "Root Depth, Minimum (inches)": "usda_root_depth_min_in",
               "pH, Minimum": "usda_ph_min", "pH, Maximum": "usda_ph_max", "Temperature, Minimum (°F)": "usda_temp_min_f",
               "Bloom Period": "usda_bloom_period", "CaCO3 Tolerance": "usda_caco3_tol", "Foliage Porosity Summer": "usda_foliage_porosity_summer",
               "Toxicity": "usda_toxicity"}

for _, r in pool.iterrows():
    t = r.scientific; b = base(t); g = genus(t)
    species_level = len(b.split()) >= 2
    put(t, "nyc_approved", bool(r.nyc_approved), "NYCP_LIST")
    m = nyc[nyc.scientific == t]
    for f in NYC_FIELDS:
        if len(m):
            put(t, f if f != "common" else "common_name", m.iloc[0][f], "NYCP_LIST")
    # local performance: exact base name, else genus-level census name
    c = cen[cen.key == b]
    if c.empty and not species_level:
        c = cen[cen.key == g]
    if c.empty and b == "Platanus x acerifolia":
        c = cen[cen.key == "Platanus x acerifolia"]
    if len(c):
        put(t, "bronx_match_level", "species" if species_level else "genus (census records genus only)", "NYC_CENSUS15")
        for f in ["c15_n", "c15_pct_good", "c15_pct_poor", "c15_pct_sidewalk_damage", "c15_pct_root_problem",
                  "c15y_n", "c15y_pct_good", "c15y_pct_poor", "c15_mean_dbh_in"]:
            put(t, "bronx_" + f, c.iloc[0][f], "NYC_CENSUS15")
    # USDA: native status only if matched at species level
    p = prof[prof.taxon == t]
    if len(p) and pd.notna(p.iloc[0].symbol):
        put(t, "usda_symbol", p.iloc[0].symbol, "USDA_PLANTS")
        if species_level and pd.notna(p.iloc[0].native_L48):
            put(t, "native_L48", {"N": True, "I": False}.get(p.iloc[0].native_L48), "USDA_PLANTS")
    tt = tr[(tr.taxon == t) & tr.cultivar.isna()]
    if species_level:
        for k, f in USDA_FIELDS.items():
            v = tt[tt.trait == k]
            if len(v):
                put(t, f, v.iloc[0].value, "USDA_PLANTS")
    # pests
    put(t, "alb_regulated_host", g in ALB, "APHIS_ALB")
    put(t, "eab_host", g == "Fraxinus", "APHIS_EAB")
    # current share in core (diversity 10-20-30 check)
    sh = sum(v for k, v in sp_share.items() if base(k) == b) if species_level else None
    put(t, "core_species_share_pct", round(sh, 1) if sh else 0.0 if species_level else None, "NYC_TREEPTS")
    put(t, "core_genus_share_pct", round(gen_share.get(g, 0.0), 1), "NYC_TREEPTS")

# ---------------- research-agent evidence (data/species/raw/agent_*.csv) ----------------
# Accept a row only if: taxon is in the pool, value non-empty, citation and URL present.
# Each distinct citation becomes a source_id; conflicting values are kept in the evidence table and
# flagged in the wide table (<field>_conflict). Species-level rows win over genus/size-class rows.
rejected = []
src_rows = []
agent_rows = []
for f in sorted((SP / "raw").glob("agent_*.csv")):
    a = pd.read_csv(f, dtype=str).fillna("")
    for _, r in a.iterrows():
        ok = r.taxon in set(pool.scientific) and r.value.strip() and r.source_citation.strip() and r.url.strip().startswith("http")
        if not ok:
            rejected.append({"file": f.name, **r.to_dict()}); continue
        sid = "AG_" + f.stem.split("_")[1] + "_" + hashlib.md5(r.source_citation.strip().encode()).hexdigest()[:6]
        src_rows.append((sid, r.source_citation.strip(), r.url.strip()))
        fld = {"climate_suitability_2050": "climate_suitability_2070_2099"}.get(r.field.strip(), r.field.strip())  # sources project 2070-2099
        agent_rows.append({"taxon": r.taxon, "field": fld, "value": r.value.strip(), "source_id": sid,
                           "match_level": r.match_level, "locator": r.locator, "notes": r.notes})
if src_rows:
    SOURCES = pd.concat([SOURCES, pd.DataFrame(src_rows, columns=["source_id", "citation", "url"])
                         .drop_duplicates("source_id").assign(accessed="2026-11-15")], ignore_index=True)
ag = pd.DataFrame(agent_rows)
conflict_fields = {}
if len(ag):
    # specificity: species / cultivar (incl. proxies, synonyms) = 0, genus / size class = 1, other = 2
    ag["rank"] = ag.match_level.str.lower().map(
        lambda m: 0 if m.startswith(("species", "cultivar", "synonym", "infraspecific")) else 1 if m.startswith(("genus", "size")) else 2)
    # risk fields: among the most specific rows, keep the HIGHEST risk (conservative); others: first row
    RISK = {"pollen_allergenicity", "bvoc_isoprene_class", "bvoc_monoterpene_class", "root_sidewalk_damage_risk"}
    ORD = {"none": 0, "none_reported": 0, "low": 1, "low-moderate": 1.5, "moderate": 2, "medium": 2, "high": 3, "very high": 4}
    for (t, fld), g in ag.sort_values("rank").groupby(["taxon", "field"]):
        best = g[g["rank"] == g["rank"].min()]
        if fld in RISK:
            best = best.assign(o=best.value.str.lower().map(ORD).fillna(-1)).sort_values("o", ascending=False)
        put(t, fld, best.iloc[0].value, best.iloc[0].source_id)
        put(t, fld + "_match_level", best.iloc[0].match_level, best.iloc[0].source_id)
        if g.value.str.lower().nunique() > 1:
            conflict_fields.setdefault(t, []).append(fld)
            put(t, fld + "_conflict", " | ".join(f"{v} [{s}]" for v, s in zip(g.value, g.source_id)), "MULTI")
pd.DataFrame(rejected).to_csv(SP / "agent_rows_rejected.csv", index=False)
print("agent rows accepted", len(ag), "| rejected", len(rejected), "| taxa with conflicts", len(conflict_fields))

evd = pd.DataFrame(ev)
kb = evd.pivot_table(index="taxon", columns="field", values="value", aggfunc="first").reindex(pool.scientific)
kb.index.name = "taxon"
PENDING = ["crown_spread_allometry_UTD", "nursery_availability_NY"]
for f in PENDING:
    if f not in kb.columns:
        kb[f] = pd.NA
def dflag(a, b_):
    out = []
    if pd.notna(a) and float(a) > 10: out.append("species>10%")
    if pd.notna(b_) and float(b_) > 20: out.append("genus>20%")
    elif pd.notna(b_) and float(b_) > 15: out.append("genus near 20% limit")
    return "; ".join(out)


kb["diversity_flag"] = [dflag(a, b_) for a, b_ in zip(kb.get("core_species_share_pct"), kb.get("core_genus_share_pct"))]
kb.to_csv(SP / "species_kb.csv")
evd.to_csv(SP / "species_kb_evidence.csv", index=False)
SOURCES.to_csv(SP / "sources.csv", index=False)

filled = kb.drop(columns=PENDING).notna().mean(axis=1)
print(f"{len(kb)} taxa, {len(evd)} sourced values, mean field coverage {filled.mean():.0%}")
print("core: n living trees", n_core, "| top genera %", gen_share.round(1).head(5).to_dict())
cols = ["nyc_approved", "size_class", "native_L48", "alb_regulated_host", "bronx_c15y_pct_good", "bronx_c15_pct_sidewalk_damage",
        "core_species_share_pct", "diversity_flag"]
print(kb[[c for c in cols if c in kb]].to_string())
