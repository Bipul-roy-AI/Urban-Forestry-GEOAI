"""Export a compact data bundle + heat image for the planner interface (interface/).

  interface/data.json  sites, all optimiser plans (K = 0/30/60), plan metrics, species traits,
                       building outlines (simplified, local metres), metadata and caveats
  interface/tmrt.png   current afternoon Tmrt (13-16 h, 24 Jun 2025) over the map extent, no axes
Local coordinates: metres east/north of the map's lower-left corner (UTM 18N), y flipped for SVG.
"""
import json
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import Affine
from shapely.geometry import box

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "interface"; OUT.mkdir(exist_ok=True)
core = gpd.read_file(ROOT / "data/aoi/area_a_core.geojson").to_crs(32618)
x0, y0, x1, y1 = core.total_bounds + np.array([-60, -60, 60, 60])
W, H = x1 - x0, y1 - y0
loc = lambda x, y: (round(x - x0, 1), round(y1 - y, 1))  # noqa: E731

# heat image cropped to the map extent
run = json.loads((ROOT / "data/processed/solweig/_run.json").read_text()); T = Affine(*run["transform"])
fs = sorted((ROOT / "data/processed/solweig/S0_current/tmrt").glob("*.tif"))
tm = np.mean([rasterio.open(f).read(1) for f in fs if int(f.stem[-4:-2]) in (13, 14, 15, 16)], axis=0)
c0, r0 = int((x0 - T.c) / T.a), int((y1 - T.f) / T.e); c1, r1 = int((x1 - T.c) / T.a), int((y0 - T.f) / T.e)
crop = tm[max(r0, 0):r1, max(c0, 0):c1]
plt.imsave(OUT / "tmrt.png", crop, cmap="inferno", vmin=35, vmax=72)

# buildings
fp = gpd.read_file(next((ROOT / "data/raw/nyc_opendata").glob("*building_footprints*.geojson"))).to_crs(32618)
fp = fp[fp.intersects(box(x0, y0, x1, y1))].copy()
fp["geometry"] = fp.geometry.simplify(0.8).intersection(box(x0, y0, x1, y1))
paths = []
for g in fp.geometry:
    for poly in getattr(g, "geoms", [g]):
        if poly.geom_type != "Polygon" or poly.is_empty:
            continue
        pts = [loc(x, y) for x, y in poly.exterior.coords]
        paths.append("M" + "L".join(f"{a},{b}" for a, b in pts) + "Z")
core_pts = [loc(x, y) for x, y in core.geometry.iloc[0].exterior.simplify(2).coords]

# sites
sites = gpd.read_file(ROOT / "data/processed/sites_area_a.gpkg").to_crs(32618)
cand = sites[(sites.in_core.astype(str) == "True") & (sites.site_class != "living_tree")]
ben = pd.read_csv(ROOT / "data/processed/area_a_site_benefits.csv").set_index("ps_id")
risk = pd.read_csv(ROOT / "data/processed/area_a_site_failure_risk.csv").set_index("ps_id")
S = []
for i, r in enumerate(cand.itertuples()):
    b = ben.loc[r.ps_id]
    S.append({"i": i, "id": r.ps_id, "xy": loc(r.geometry.x, r.geometry.y),
              "addr": " ".join(str(v) for v in (r.buildingnumber, r.streetname) if pd.notna(v) and str(v) != "nan") or "(no address)",
              "cls": r.site_class, "lu": r.lot_landuse_name if pd.notna(r.lot_landuse_name) else None,
              "sw": None if pd.isna(r.sidewalk_width_m) else round(float(r.sidewalk_width_m), 1),
              "tmrt": None if pd.isna(b.tmrt_pm_now_c) else round(float(b.tmrt_pm_now_c), 1),
              "d10": None if pd.isna(b.dTmrt_S1_plant_10yr_mean15m_c) else round(float(b.dTmrt_S1_plant_10yr_mean15m_c), 1),
              "d20": None if pd.isna(b.dTmrt_S2_plant_20yr_mean15m_c) else round(float(b.dTmrt_S2_plant_20yr_mean15m_c), 1),
              "cool20": int(b.cooled_sidewalk_m2_gt10c_S2_plant_20yr),
              "risk": None if r.ps_id not in risk.index else round(float(risk.loc[r.ps_id, "site_risk_median"]), 3),
              "wires": "yes" if (str(r.overheadutilities) == "1.0" or str(r.wo_wire_conflict) == "True") else ("no" if str(r.overheadutilities) == "0.0" else "unknown"),
              "soil": r.soil_substratum if pd.notna(r.soil_substratum) else None,
              "lawn": str(r.pssite) == "Park"})
idx = {s["id"]: s["i"] for s in S}

# plans
plans = {}
OD = ROOT / "data/processed/optimiser"
for K in (0, 30, 60):
    summ = json.loads((ROOT / f"outputs/optimiser_summary_K{K}.json").read_text())
    for grp in ("plans", "baselines"):
        for name, m in summ[grp].items():
            key = name if grp == "plans" else "baseline_" + name
            p = pd.read_csv(OD / f"plan_{key}_K{K}.csv")
            rows = [[idx[x.ps_id], x.species, x.size_class, bool(x.expanded_soil), round(float(x.p_fail_5yr), 3),
                     round(float(x.exp_cooled_m2), 1), bool(x.flag_verify_wires), bool(x.flag_verify_wet_site), bool(x.flag_untrained_species)]
                    for x in p.itertuples() if x.ps_id in idx]
            plans[f"{key}|{K}"] = {"name": key, "K": K, "kind": grp[:-1], "metrics": {k: m[k] for k in
                                   ("exp_cooled_m2", "allergy_isoprene_score", "ecology_score", "n_species", "n_expanded_soil", "verify_wires_sites")},
                                   "genus_after": m["top_genus_share_after"], "rows": rows}

# species traits (approved)
kb = pd.read_csv(ROOT / "data/species/species_kb.csv")
kb = kb[kb.nyc_approved.astype(str) == "True"]
cols = {"common_name": "common", "size_class": "size", "native_NY_region": "nativeNY", "pollen_allergenicity": "allergy",
        "bvoc_isoprene_class": "isoprene", "pollinator_value": "pollinator", "climate_suitability_2070_2099": "climate",
        "root_sidewalk_damage_risk": "roots", "bronx_c15y_pct_good": "youngGoodPct", "alb_regulated_host": "albHost",
        "min_soil_volume_m3": "soilM3", "notes": "nycNote"}
SP = {r.taxon: {v: (None if pd.isna(getattr(r, k, None)) else getattr(r, k)) for k, v in cols.items()} for r in kb.itertuples()}

meta = {"map_m": [round(W, 1), round(H, 1)], "buildings": paths, "core": core_pts,
        "weather": "24 June 2025, 13:00-16:00 EDT; air temperature max ~37.8 C (ERA5 adjusted to Central Park 99 F / LaGuardia 101 F)",
        "caveats": [
            "Tmrt is pedestrian radiant heat from SOLWEIG (experimental UMEP port), not air temperature.",
            "Tree crowns at 10/20 years are assumptions (generic medium tree; small 5 m, intermediate 6 m, medium 7 m, large 8 m crowns at 20 yr) pending USFS Urban Tree Database growth curves.",
            "A large species without expanded soil is assumed capped at a medium crown.",
            "Failure risk is a cross-sectional proxy from NYC Forestry records (young trees, Bronx), not measured survival; site conditions explain more than species.",
            "Overhead wires are known at only 11 of 121 sites; large trees at unknown sites are flagged 'verify wires'.",
            "Air quality and stormwater figures are first-order per-canopy rates from Nowak et al. (2018) for NYC; young trees deliver less, and dense crowns in narrow streets can trap pollution.",
            "LiDAR canopy is from 2017; every site still needs a utility markout and soil test before planting."],
        "rates": {"o3_g_m2_yr": 4.05, "no2_g_m2_yr": 1.32, "pm25_g_m2_yr": 0.21, "runoff_L_m2_yr": 11.9},
        "corridor": json.loads((ROOT / "outputs/benefits_summary.json").read_text())["core_sidewalk_tmrt_pm_c"]}
(OUT / "data.json").write_text(json.dumps({"sites": S, "plans": plans, "species": SP, "meta": meta}, separators=(",", ":"), default=str))
print("sites", len(S), "plans", len(plans), "species", len(SP), "buildings", len(paths),
      "| data.json KB", round((OUT / "data.json").stat().st_size / 1024), "| map m", round(W), round(H), "| png", crop.shape)
