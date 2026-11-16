"""Whole-plan evaluation: compare shortlisted plans using their own SOLWEIG simulation (audit fix, Nov 2026).

Run after:  python solweig_scenarios.py --plans <name>_K<K> ...
For each PLAN_<name> it reports, on sidewalk pixels counted ONCE:
  simulated_unique_cooled_m2   sidewalk area with afternoon Tmrt change < -10 C
  degree_m2                    sum of max(0, -dTmrt) over sidewalk pixels [C x m2]
  warmed_gt1c_m2               sidewalk area that gets > 1 C warmer (adverse changes are reported, not hidden)
  core mean Tmrt and share > 60 C
and compares the optimiser's additive estimate with the simulated value.
Output: outputs/plan_evaluation.json, outputs/plan_evaluation.csv
"""
import glob
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import Affine

ROOT = Path(__file__).resolve().parents[1]
SW = ROOT / "data/processed/solweig"
run = json.loads((SW / "_run.json").read_text()); T = Affine(*run["transform"])
PM_EST = [13, 14, 15, 16]


def tmrt_pm(s):
    fs = [f for f in sorted(glob.glob(str(SW / s / "tmrt" / "*.tif"))) if int(f[-8:-6]) in PM_EST]
    assert len(fs) == len(PM_EST), s
    return np.mean([rasterio.open(f).read(1) for f in fs], axis=0)


base = tmrt_pm("S0_current"); H, W = base.shape
sw = gpd.read_file(next((ROOT / "data/raw/nyc_opendata").glob("*sidewalk*.geojson"))).to_crs(32618)
fp = gpd.read_file(next((ROOT / "data/raw/nyc_opendata").glob("*building_footprints*.geojson"))).to_crs(32618)
ped = rasterize(((g, 1) for g in sw.geometry), out_shape=(H, W), transform=T, dtype="uint8").astype(bool)
ped &= ~rasterize(((g, 1) for g in fp.geometry), out_shape=(H, W), transform=T, dtype="uint8").astype(bool)
core = gpd.read_file(ROOT / "data/aoi/area_a_core.geojson").to_crs(32618)
pc = ped & rasterize([(core.geometry.iloc[0], 1)], out_shape=(H, W), transform=T, dtype="uint8").astype(bool)

names = sys.argv[1:] or [p.name[5:] for p in sorted(SW.glob("PLAN_*"))]
rows = []
for n in names:
    d = tmrt_pm("PLAN_" + n) - base
    plan, k = n.rsplit("_K", 1)
    summ = json.loads((ROOT / f"outputs/optimiser_summary_K{k}.json").read_text())
    m = {**summ["plans"], **{"baseline_" + b: v for b, v in summ["baselines"].items()}}[plan]
    rows.append({"plan": plan, "K": int(k), "n_planted": m["n_planted"], "n_expanded_soil": m["n_expanded_soil"],
                 "simulated_unique_cooled_m2": int((ped & (d < -10)).sum()),
                 "additive_estimate_m2": m["cooling_potential_m2_additive_estimate"],
                 "degree_m2": round(float(np.clip(-d[ped], 0, None).sum())),
                 "warmed_gt1c_m2": int((ped & (d > 1)).sum()),
                 "core_sidewalk_tmrt_c": round(float((base + d)[pc].mean()), 2),
                 "core_share_gt60c": round(float(((base + d)[pc] > 60).mean()), 3),
                 "new_canopy_m2": run["PLAN_" + n]["added_canopy_m2"],
                 "allergy_isoprene_index": m["allergy_isoprene_index"], "ecology_index": m["ecology_index"],
                 "mean_condition_risk": m["mean_condition_risk"]})
df = pd.DataFrame(rows)
df["additive_over_simulated"] = (df.additive_estimate_m2 / df.simulated_unique_cooled_m2).round(2)
df.to_csv(ROOT / "outputs/plan_evaluation.csv", index=False)
out = {"baseline_now": {"core_sidewalk_tmrt_c": round(float(base[pc].mean()), 2), "core_share_gt60c": round(float((base[pc] > 60).mean()), 3)},
       "plans": df.to_dict("records")}
(ROOT / "outputs/plan_evaluation.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out["baseline_now"])); print(df.to_string(index=False))
