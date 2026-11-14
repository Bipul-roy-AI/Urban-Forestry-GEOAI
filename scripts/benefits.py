"""Module 4b: per-site and corridor benefits of planting scenarios.

Heat: SOLWEIG Tmrt (data/processed/solweig), afternoon window 13-16 EDT on 24 Jun 2025, pedestrian pixels
      = NYC planimetric sidewalk polygons minus buildings.
Air quality & stormwater: first-order per-canopy-area rates from the NYC i-Tree Eco assessment
      Nowak et al. (2018) RB NRS-117: 21% tree cover; removal O3 735, NO2 240, PM2.5 38 tons/yr (Table 11, p.19);
      avoided runoff 69 million ft3/yr (p.22). NYC land area 783.8 km2 (US Census). "tons" read as US short tons.
      Rates are citywide averages for an existing (mostly mature) canopy; young trees with low leaf area deliver less.
Risk adjustment: expected benefit = benefit x (1 - p_fail_5yr) using the calibrated survival model site risk.
Outputs: data/processed/area_a_site_benefits.csv, data/processed/solweig/delta_tmrt_pm_<S>.tif, outputs/benefits_map.png,
         outputs/benefits_summary.json
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

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SW = ROOT / "data/processed/solweig"
run = json.loads((SW / "_run.json").read_text())
T = Affine(*run["transform"])
PM = [13, 14, 15, 16]


def tmrt_pm(s):
    fs = [f for f in sorted(glob.glob(str(SW / s / "tmrt" / "*.tif"))) if int(f[-8:-6]) in PM]
    return np.mean([rasterio.open(f).read(1) for f in fs], axis=0), len(fs)


S = {s: tmrt_pm(s) for s in ("S0_current", "S1_plant_10yr", "S2_plant_20yr")}
base, nh = S["S0_current"]
H, W = base.shape
prof = dict(driver="GTiff", height=H, width=W, count=1, dtype="float32", crs="EPSG:32618", transform=T, compress="deflate")

# pedestrian mask
sw = gpd.read_file(next((ROOT / "data/raw/nyc_opendata").glob("*sidewalk*.geojson"))).to_crs(32618)
fp = gpd.read_file(next((ROOT / "data/raw/nyc_opendata").glob("*building_footprints*.geojson"))).to_crs(32618)
ped = rasterize(((g, 1) for g in sw.geometry), out_shape=(H, W), transform=T, dtype="uint8").astype(bool)
ped &= ~rasterize(((g, 1) for g in fp.geometry), out_shape=(H, W), transform=T, dtype="uint8").astype(bool)
core = gpd.read_file(ROOT / "data/aoi/area_a_core.geojson").to_crs(32618)
coremask = rasterize([(core.geometry.iloc[0], 1)], out_shape=(H, W), transform=T, dtype="uint8").astype(bool)

# canopy layers (same clip as SOLWEIG run)
with rasterio.open(ROOT / "data/raw/lidar/chm_1m.tif") as s:
    win = rasterio.windows.from_bounds(T.c, T.f + T.e * H, T.c + T.a * W, T.f, s.transform)
    chm = s.read(1, window=win, boundless=True, fill_value=0)[:H, :W]

deltas = {}
for s in ("S1_plant_10yr", "S2_plant_20yr"):
    d = (S[s][0] - base).astype("float32"); deltas[s] = d
    with rasterio.open(SW / f"delta_tmrt_pm_{s}.tif", "w", **prof) as o:
        o.write(d, 1)

# sanity: shade vs sun under existing canopy on sidewalks
sanity = {"tmrt_pm_sidewalk_under_canopy_c": float(base[ped & (chm > 2)].mean()),
          "tmrt_pm_sidewalk_open_c": float(base[ped & (chm <= 0.5)].mean())}

# per-site benefits
sites = gpd.read_file(ROOT / "data/processed/sites_area_a.gpkg").to_crs(32618)
cand = sites[(sites.in_core.astype(str) == "True") & (sites.site_class != "living_tree")].copy()
yy, xx = np.mgrid[0:H, 0:W]
cx = T.c + (xx + 0.5) * T.a; cy = T.f + (yy + 0.5) * T.e
CROWN = {"S1_plant_10yr": 2.5, "S2_plant_20yr": 4.0}  # crown radius (m) used in SOLWEIG scenarios
rows = []
for _, r in cand.iterrows():
    p = r.geometry; col = int((p.x - T.c) / T.a); row = int((p.y - T.f) / T.e); k = 16
    r0, r1, c0, c1 = max(row - k, 0), min(row + k + 1, H), max(col - k, 0), min(col + k + 1, W)
    dist = np.hypot(cx[r0:r1, c0:c1] - p.x, cy[r0:r1, c0:c1] - p.y)
    m15 = (dist <= 15) & ped[r0:r1, c0:c1]
    rec = {"ps_id": r.ps_id, "site_class": r.site_class, "street": r.streetname, "landuse": r.lot_landuse_name,
           "tmrt_pm_now_c": float(base[r0:r1, c0:c1][m15].mean()) if m15.any() else np.nan,
           "sidewalk_px_15m": int(m15.sum())}
    for s, rad in CROWN.items():
        d = deltas[s][r0:r1, c0:c1]
        rec[f"dTmrt_{s}_mean15m_c"] = float(d[m15].mean()) if m15.any() else np.nan
        rec[f"cooled_sidewalk_m2_gt10c_{s}"] = int((m15 & (d < -10)).sum())
        new_canopy = (dist <= rad) & (chm[r0:r1, c0:c1] <= 0.5)
        rec[f"new_canopy_m2_{s}"] = int(new_canopy.sum())
    rows.append(rec)
b = pd.DataFrame(rows)

# air quality & stormwater rates per m2 canopy per year (Nowak et al. 2018)
cover_m2 = 0.21 * 783.8e6
ton = 907_184.74  # g per US short ton
RATES = {"o3_g": 735 * ton / cover_m2, "no2_g": 240 * ton / cover_m2, "pm25_g": 38 * ton / cover_m2,
         "runoff_L": 69e6 * 0.0283168 * 1000 / cover_m2}
for s in CROWN:
    for k, v in RATES.items():
        b[f"{k}_per_yr_{s}"] = (b[f"new_canopy_m2_{s}"] * v).round(2)

risk = pd.read_csv(ROOT / "data/processed/area_a_site_failure_risk.csv")
b = b.merge(risk[["ps_id", "site_risk_median"]], on="ps_id", how="left")
b["survival_5yr"] = 1 - b.site_risk_median
b["exp_cooled_m2_20yr"] = (b["cooled_sidewalk_m2_gt10c_S2_plant_20yr"] * b.survival_5yr).round(1)
b.to_csv(ROOT / "data/processed/area_a_site_benefits.csv", index=False)

pc = ped & coremask
summary = {
    "weather": f"{run['day']} 13-16 EDT, Ta max ~37.8 C (bias-corrected ERA5)", "hours_averaged": nh,
    "sanity_existing_canopy": {k: round(v, 1) for k, v in sanity.items()},
    "core_sidewalk_tmrt_pm_c": {s: round(float(S[s][0][pc].mean()), 2) for s in S},
    "core_sidewalk_share_tmrt_gt_60c": {s: round(float((S[s][0][pc] > 60).mean()), 3) for s in S},
    "per_site_median": {c: round(float(b[c].median()), 2) for c in b.columns if c.startswith(("dTmrt", "cooled", "new_canopy", "o3", "no2", "pm25", "runoff"))},
    "all_candidates_total_per_yr_20yr": {k: round(float(b[f"{k}_per_yr_S2_plant_20yr"].sum()), 1) for k in RATES},
    "rates_per_m2_canopy_per_yr": {k: round(v, 3) for k, v in RATES.items()},
    "n_sites": len(b),
}
(ROOT / "outputs/benefits_summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))

# map
fig, ax = plt.subplots(1, 2, figsize=(15, 7))
ext = (T.c, T.c + W, T.f - H, T.f)
im0 = ax[0].imshow(base, extent=ext, cmap="inferno", vmin=35, vmax=72)
plt.colorbar(im0, ax=ax[0], fraction=0.04, label="Tmrt 13-16 h, current (deg C)")
im1 = ax[1].imshow(np.where(np.abs(deltas["S2_plant_20yr"]) > 0.3, deltas["S2_plant_20yr"], np.nan), extent=ext, cmap="Blues_r", vmin=-25, vmax=0)
plt.colorbar(im1, ax=ax[1], fraction=0.04, label="Tmrt change 13-16 h, 20-yr planting (deg C)")
for a in ax:
    core.boundary.plot(ax=a, color="cyan", lw=1, ls="--"); fp.boundary.plot(ax=a, color="grey", lw=0.2)
    a.set_xlim(ext[0], ext[1]); a.set_ylim(ext[2], ext[3]); a.set_xticks([]); a.set_yticks([])
cand.plot(ax=ax[1], color="red", markersize=4)
ax[0].set_title("Pedestrian radiant heat now (24 Jun 2025, afternoon)"); ax[1].set_title("Cooling from 121 new trees at 20 years")
plt.tight_layout(); plt.savefig(ROOT / "outputs/benefits_map.png", dpi=120)
