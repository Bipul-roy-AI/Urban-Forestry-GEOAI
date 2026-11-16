"""Module 4b: benefits of planting scenarios, counted without overlap (audit fix, Nov 2026).

Heat: SOLWEIG Tmrt (data/processed/solweig), afternoon window 13:00-17:00 EDT (hour-ending labels 13-16 EST in the run clock) on
      24 Jun 2025; pedestrian pixels = NYC planimetric sidewalk polygons minus buildings.
  WHOLE-PLAN metrics use each sidewalk pixel once:
      cooled_m2      unique sidewalk area with Tmrt change < -10 C
      degree_m2      sum over sidewalk pixels of max(0, -dTmrt)  [C x m2]  (how much, not only where)
  PER-SITE attribution: every sidewalk pixel is assigned to its NEAREST candidate site (within 15 m), so the
      per-site values add up exactly to the whole-plan total (no double counting of overlapping shade).
Canopy: new canopy comes from the simulated mask (new_canopy_mask.tif: buildings excluded, crowns unioned),
      and each new-canopy pixel is assigned to its nearest site, so per-site canopy sums to the simulated total.
Air quality & stormwater: first-order per-canopy rates from Nowak et al. (2018) RB NRS-117 (21% tree cover;
      O3 735, NO2 240, PM2.5 38 tons/yr; avoided runoff 69 million ft3/yr; NYC land 783.8 km2; short tons).
      Removal estimates for mature citywide canopy, not street-level concentration changes.
Outputs: data/processed/area_a_site_benefits.csv, outputs/benefits_summary.json, outputs/benefits_map.png
"""
import glob
import json
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import Affine
from scipy import ndimage

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SW = ROOT / "data/processed/solweig"
run = json.loads((SW / "_run.json").read_text())
T = Affine(*run["transform"])
PM_EST = [13, 14, 15, 16]            # hour-ENDING labels in EST: the four hourly intervals 13:00-17:00 EDT


def tmrt_pm(s):
    fs = [f for f in sorted(glob.glob(str(SW / s / "tmrt" / "*.tif"))) if int(f[-8:-6]) in PM_EST]
    assert len(fs) == len(PM_EST), f"{s}: expected {len(PM_EST)} afternoon rasters, found {len(fs)}"
    return np.mean([rasterio.open(f).read(1) for f in fs], axis=0)


base = tmrt_pm("S0_current")
H, W = base.shape
prof = dict(driver="GTiff", height=H, width=W, count=1, dtype="float32", crs="EPSG:32618", transform=T, compress="deflate")
sw = gpd.read_file(next((ROOT / "data/raw/nyc_opendata").glob("*sidewalk*.geojson"))).to_crs(32618)
fp = gpd.read_file(next((ROOT / "data/raw/nyc_opendata").glob("*building_footprints*.geojson"))).to_crs(32618)
bld = rasterize(((g, 1) for g in fp.geometry), out_shape=(H, W), transform=T, dtype="uint8").astype(bool)
ped = rasterize(((g, 1) for g in sw.geometry), out_shape=(H, W), transform=T, dtype="uint8").astype(bool) & ~bld
core = gpd.read_file(ROOT / "data/aoi/area_a_core.geojson").to_crs(32618)
coremask = rasterize([(core.geometry.iloc[0], 1)], out_shape=(H, W), transform=T, dtype="uint8").astype(bool)
with rasterio.open(ROOT / "data/raw/lidar/chm_1m.tif") as s:
    win = rasterio.windows.from_bounds(T.c, T.f + T.e * H, T.c + T.a * W, T.f, s.transform)
    chm = s.read(1, window=win, boundless=True, fill_value=0)[:H, :W]

sites = gpd.read_file(ROOT / "data/processed/sites_area_a.gpkg").to_crs(32618)
cand = sites[(sites.in_core.astype(str) == "True") & (sites.plantable_status == "candidate")].reset_index(drop=True)

# nearest-candidate allocation grid (Voronoi), limited to 15 m
seed = np.zeros((H, W), bool); idx_at = {}
for i, p in enumerate(cand.geometry):
    r, c = int((p.y - T.f) / T.e), int((p.x - T.c) / T.a)
    if 0 <= r < H and 0 <= c < W:
        seed[r, c] = True; idx_at[(r, c)] = i
dist, (ir, ic) = ndimage.distance_transform_edt(~seed, return_indices=True)
owner = np.full((H, W), -1, int)
lut = np.full((H, W), -1, int)
for (r, c), i in idx_at.items():
    lut[r, c] = i
owner = lut[ir, ic]
owner[dist > 15] = -1

cover_m2 = 0.21 * 783.8e6; ton = 907_184.74
RATES = {"o3_g": 735 * ton / cover_m2, "no2_g": 240 * ton / cover_m2, "pm25_g": 38 * ton / cover_m2,
         "runoff_L": 69e6 * 0.0283168 * 1000 / cover_m2}

b = cand[["ps_id", "site_class", "streetname", "lot_landuse_name"]].rename(columns={"streetname": "street", "lot_landuse_name": "landuse"}).copy()
near = owner >= 0
b["tmrt_pm_now_c"] = [float(base[ped & (owner == i)].mean()) if (ped & (owner == i)).any() else np.nan for i in range(len(cand))]
b["sidewalk_m2_owned"] = np.bincount(owner[ped & near], minlength=len(cand))
b["no_sidewalk_benefit"] = b.sidewalk_m2_owned == 0   # no sidewalk within 15 m that a nearer site does not claim
whole = {}
for s, tag in (("S1_crown5m", "crown5m"), ("S2_crown8m", "crown8m")):
    d = (tmrt_pm(s) - base).astype("float32")
    with rasterio.open(SW / f"delta_tmrt_pm_{s}.tif", "w", **prof) as o:
        o.write(d, 1)
    cooled = ped & (d < -10)
    b[f"cooled_m2_{tag}"] = np.bincount(owner[cooled & near], minlength=len(cand))
    # guard against double counting: per-site values + pixels beyond 15 m must equal the unique total
    assert int(b[f"cooled_m2_{tag}"].sum()) + int((cooled & ~near).sum()) == int(cooled.sum()), "cooling attribution does not add up"
    b[f"degree_m2_{tag}"] = np.bincount(owner[ped & near], weights=np.clip(-d[ped & near], 0, None), minlength=len(cand)).round(1)
    b[f"dTmrt_mean_{tag}_c"] = [float(d[ped & (owner == i)].mean()) if (ped & (owner == i)).any() else np.nan for i in range(len(cand))]
    newc = rasterio.open(SW / s / "new_canopy_mask.tif").read(1).astype(bool)
    b[f"new_canopy_m2_{tag}"] = np.bincount(owner[newc & near], minlength=len(cand))
    for k, v in RATES.items():
        b[f"{k}_per_yr_{tag}"] = (b[f"new_canopy_m2_{tag}"] * v).round(2)
    whole[tag] = {"unique_cooled_sidewalk_m2": int(cooled.sum()),
                  "attributed_to_sites_m2": int(b[f"cooled_m2_{tag}"].sum()),
                  "cooled_beyond_15m_of_any_site_m2": int((cooled & ~near).sum()),
                  "degree_m2_all_sidewalk": round(float(np.clip(-d[ped], 0, None).sum()), 0),
                  "sidewalk_warmed_gt1c_m2": int((ped & (d > 1)).sum()),
                  "simulated_new_canopy_m2": int(newc.sum()), "canopy_attributed_m2": int(b[f"new_canopy_m2_{tag}"].sum()),
                  "core_sidewalk_tmrt_pm_c": round(float((base + d)[ped & coremask].mean()), 2),
                  "core_sidewalk_share_gt60c": round(float(((base + d)[ped & coremask] > 60).mean()), 3)}

risk = pd.read_csv(ROOT / "data/processed/area_a_site_condition_risk.csv") if (ROOT / "data/processed/area_a_site_condition_risk.csv").exists() else None
if risk is not None:
    b = b.merge(risk[["ps_id", "site_risk_median", "has_prediction"]], on="ps_id", how="left")
b.to_csv(ROOT / "data/processed/area_a_site_benefits.csv", index=False)

pc = ped & coremask
summary = {"weather": f"{run['day']} 13:00-17:00 EDT (hour-ending 13-16 EST run clock), Ta max ~37.8 C (bias-corrected ERA5)",
           "n_candidate_sites": int(len(cand)),
           "sanity_existing_canopy": {"tmrt_pm_sidewalk_under_canopy_c": round(float(base[ped & (chm > 2)].mean()), 1),
                                      "tmrt_pm_sidewalk_open_c": round(float(base[ped & (chm <= 0.5)].mean()), 1)},
           "core_sidewalk_now": {"tmrt_pm_c": round(float(base[pc].mean()), 2), "share_gt60c": round(float((base[pc] > 60).mean()), 3)},
           "whole_plan": whole,
           "per_site_median": {c: round(float(b[c].median()), 2) for c in b.columns if c.startswith(("dTmrt", "cooled", "degree", "new_canopy"))},
           "rates_per_m2_canopy_per_yr": {k: round(v, 3) for k, v in RATES.items()},
           "totals_per_yr_crown8m": {k: round(float(b[f"{k}_per_yr_crown8m"].sum()), 1) for k in RATES}}
(ROOT / "outputs/benefits_summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))

d8 = rasterio.open(SW / "delta_tmrt_pm_S2_crown8m.tif").read(1)
fig, ax = plt.subplots(1, 2, figsize=(15, 7)); ext = (T.c, T.c + W, T.f - H, T.f)
im0 = ax[0].imshow(base, extent=ext, cmap="inferno", vmin=35, vmax=72); plt.colorbar(im0, ax=ax[0], fraction=0.04, label="Tmrt 13-17 h EDT, current (deg C)")
im1 = ax[1].imshow(np.where(np.abs(d8) > 0.3, d8, np.nan), extent=ext, cmap="Blues_r", vmin=-25, vmax=0); plt.colorbar(im1, ax=ax[1], fraction=0.04, label="Tmrt change, 8 m crowns (deg C)")
for a in ax:
    core.boundary.plot(ax=a, color="cyan", lw=1, ls="--"); fp.boundary.plot(ax=a, color="grey", lw=0.2)
    a.set_xlim(ext[0], ext[1]); a.set_ylim(ext[2], ext[3]); a.set_xticks([]); a.set_yticks([])
cand.plot(ax=ax[1], color="red", markersize=4)
ax[0].set_title("Pedestrian radiant heat now (24 Jun 2025, afternoon)"); ax[1].set_title(f"Cooling from {len(cand)} new trees with 8 m crowns")
plt.tight_layout(); plt.savefig(ROOT / "outputs/benefits_map.png", dpi=120)
