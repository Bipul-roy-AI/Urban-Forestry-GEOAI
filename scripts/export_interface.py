"""Export a compact data bundle + heat image for the planner interface (interface/).

  interface/data.json  sites (candidates + sites deferred for review), all optimiser plans (K = 0/30/60),
                       plan metrics (additive estimate + whole-plan simulation where available), species traits,
                       building outlines (simplified, local metres), metadata and caveats
  interface/tmrt.png   current afternoon Tmrt (13:00-17:00 EDT, 24 Jun 2025) over the map extent, no axes
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
num = lambda v, d=1: None if pd.isna(v) else round(float(v), d)  # noqa: E731

run = json.loads((ROOT / "data/processed/solweig/_run.json").read_text()); T = Affine(*run["transform"])
fs = sorted((ROOT / "data/processed/solweig/S0_current/tmrt").glob("*.tif"))
tm = np.mean([rasterio.open(f).read(1) for f in fs if int(f.stem[-4:-2]) in (13, 14, 15, 16)], axis=0)
c0, r0 = int((x0 - T.c) / T.a), int((y1 - T.f) / T.e); c1, r1 = int((x1 - T.c) / T.a), int((y0 - T.f) / T.e)
plt.imsave(OUT / "tmrt.png", tm[max(r0, 0):r1, max(c0, 0):c1], cmap="inferno", vmin=35, vmax=72)

fp = gpd.read_file(next((ROOT / "data/raw/nyc_opendata").glob("*building_footprints*.geojson"))).to_crs(32618)
fp = fp[fp.intersects(box(x0, y0, x1, y1))].copy()
fp["geometry"] = fp.geometry.simplify(0.8).intersection(box(x0, y0, x1, y1))
paths = []
for g in fp.geometry:
    for poly in getattr(g, "geoms", [g]):
        if poly.geom_type == "Polygon" and not poly.is_empty:
            paths.append("M" + "L".join(f"{a},{b}" for a, b in (loc(x, y) for x, y in poly.exterior.coords)) + "Z")
core_pts = [loc(x, y) for x, y in core.geometry.iloc[0].exterior.simplify(2).coords]

sites = gpd.read_file(ROOT / "data/processed/sites_area_a.gpkg").to_crs(32618)
sel = sites[(sites.in_core.astype(str) == "True") & sites.plantable_status.isin(["candidate", "review"])]
ben = pd.read_csv(ROOT / "data/processed/area_a_site_benefits.csv").set_index("ps_id")
risk = pd.read_csv(ROOT / "data/processed/area_a_site_condition_risk.csv").set_index("ps_id")
S = []
for i, r in enumerate(sel.itertuples()):
    b = ben.loc[r.ps_id] if r.ps_id in ben.index else None
    has = r.ps_id in risk.index and bool(risk.loc[r.ps_id, "has_prediction"])
    S.append({"i": i, "id": r.ps_id, "xy": loc(r.geometry.x, r.geometry.y), "status": r.plantable_status,
              "addr": " ".join(str(v) for v in (r.buildingnumber, r.streetname) if pd.notna(v) and str(v) != "nan") or "(no address)",
              "cls": r.site_class, "lu": r.lot_landuse_name if pd.notna(r.lot_landuse_name) else None,
              "sw": num(r.sidewalk_width_m), "juris": r.jurisdiction if pd.notna(r.jurisdiction) else "unknown",
              "tree": (r.tree_species if pd.notna(r.tree_species) else None) if r.plantable_status == "review" else None,
              "tmrt": num(b.tmrt_pm_now_c) if b is not None else None,
              "d5": num(b.dTmrt_mean_crown5m_c) if b is not None else None,
              "d8": num(b.dTmrt_mean_crown8m_c) if b is not None else None,
              "cool8": int(b.cooled_m2_crown8m) if b is not None else None,
              "risk": num(risk.loc[r.ps_id, "site_risk_median"], 3) if has else None,
              "wires": "yes" if (str(r.overheadutilities) == "1.0" or str(r.wo_wire_conflict) == "True") else ("no" if str(r.overheadutilities) == "0.0" else "unknown"),
              "soil": r.soil_substratum if pd.notna(r.soil_substratum) else None})
idx = {s["id"]: s["i"] for s in S}

ev_f = ROOT / "outputs/plan_evaluation.json"
sim = {(p["plan"], p["K"]): p for p in json.loads(ev_f.read_text())["plans"]} if ev_f.exists() else {}
FLAGS = ["flag_verify_wires", "flag_verify_wet_site", "flag_untrained_species", "flag_no_risk_prediction", "flag_trait_unknown", "flag_verify_jurisdiction", "flag_no_sidewalk_benefit"]
plans = {}
for K in (0, 30, 60):
    summ = json.loads((ROOT / f"outputs/optimiser_summary_K{K}.json").read_text())
    for grp in ("plans", "baselines"):
        for name, m in summ[grp].items():
            key = name if grp == "plans" else "baseline_" + name
            p = pd.read_csv(ROOT / f"data/processed/optimiser/plan_{key}_K{K}.csv")
            rows = [[idx[x.ps_id], x.action, x.species if isinstance(x.species, str) else "", x.size_class if isinstance(x.size_class, str) else "",
                     bool(x.expanded_soil) if pd.notna(x.expanded_soil) else False, num(x.condition_risk, 3), num(x.cooling_potential_m2),
                     [f[5:] for f in FLAGS if pd.notna(getattr(x, f)) and bool(getattr(x, f))]]
                    for x in p.itertuples() if x.ps_id in idx]
            s_ = sim.get((key, K))
            plans[f"{key}|{K}"] = {"name": key, "K": K, "kind": grp[:-1], "rows": rows, "max_share": m["max_share_after"], "flags": m["flags"],
                                   "metrics": {"cool_est": m["cooling_potential_m2_additive_estimate"], "cool_sim": s_["simulated_unique_cooled_m2"] if s_ else None,
                                               "core_tmrt_sim": s_["core_sidewalk_tmrt_c"] if s_ else None,
                                               "health": m["allergy_isoprene_index"], "eco": m["ecology_index"], "risk": m["mean_condition_risk"],
                                               "n_planted": m["n_planted"], "n_species": m["n_species"], "n_soil": m["n_expanded_soil"]}}

kb = pd.read_csv(ROOT / "data/species/species_kb.csv"); kb = kb[kb.nyc_approved.astype(str) == "True"]
cols = {"common_name": "common", "size_class": "size", "native_NY_region": "nativeNY", "pollen_allergenicity": "allergy",
        "pollen_allergenicity_conflict": "allergyConflict", "bvoc_isoprene_class": "isoprene", "pollinator_value": "pollinator",
        "climate_suitability_2070_2099": "climate", "root_sidewalk_damage_risk": "roots", "alb_regulated_host": "albHost", "notes": "nycNote"}
SP = {r.taxon: {v: (None if pd.isna(getattr(r, k, None)) else getattr(r, k)) for k, v in cols.items()} for r in kb.itertuples()}
bs = json.loads((ROOT / "outputs/benefits_summary.json").read_text())
cm = json.loads((ROOT / "outputs/condition_risk_cv_metrics.json").read_text())
meta = {"map_m": [round(W, 1), round(H, 1)], "buildings": paths, "core": core_pts,
        "weather": "24 June 2025, 13:00-17:00 EDT; air temperature max ~37.8 C (ERA5 adjusted to Central Park 99 F / LaGuardia 101 F)",
        "now": bs["core_sidewalk_now"], "generic": bs["whole_plan"], "sanity": bs["sanity_existing_canopy"],
        "model": {"auc": cm["auc"]["full"], "auc_equal_age": cm["within_cohort_auc"]["full"], "n": cm["n"]},
        "caveats": [
            "Tmrt is simulated pedestrian radiant heat (SOLWEIG, experimental UMEP port) on one hot day. It is not air temperature and has not been validated in the field.",
            "Crown sizes are assumptions by size class (small 5 m, intermediate 6 m, medium 7 m, large 8 m), not growth predictions. A large species without expanded soil is assumed capped at a medium crown.",
            "Cooled area counts each sidewalk square metre once. Plan totals marked 'simulated' come from re-running the heat model for that whole plan; 'estimate' values are additive approximations used for search.",
            "Condition risk is a relative score from current city inventory records of small trees. It is not survival, its percentages are not calibrated across neighbourhoods, and it should only be used to rank sites.",
            "23 sites have conflicting records (for example an 'empty' space with a living tree on record). They are deferred for verification, not planted.",
            "Overhead wires, pit dimensions, jurisdiction and underground utilities are unknown at most sites. Every recommendation needs a field check.",
            "The allergy + isoprene and ecology values are constructed indices from published categories, not measured health or biodiversity outcomes.",
            "Air quality and stormwater figures are first-order per-canopy rates (Nowak et al. 2018), not changes in the air people breathe."],
        "rates": bs["rates_per_m2_canopy_per_yr"]}
(OUT / "data.json").write_text(json.dumps({"sites": S, "plans": plans, "species": SP, "meta": meta}, separators=(",", ":"), default=str))
print("sites", len(S), "(candidates", sum(s["status"] == "candidate" for s in S), "review", sum(s["status"] == "review" for s in S), ") plans", len(plans),
      "| simulated plans", sum(1 for p in plans.values() if p["metrics"]["cool_sim"] is not None), "| data.json KB", round((OUT / "data.json").stat().st_size / 1024))
