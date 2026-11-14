"""Module 4a: pedestrian heat (mean radiant temperature, Tmrt) for planting scenarios with SOLWEIG.

Engine: `solweig` 0.1.0b103 (UMEP-dev; experimental Rust/Python port, parity-tested vs reference UMEP).
Domain: Area A core bbox + 150 m buffer, 1 m grid (EPSG:32618).
Surfaces (from data/raw/lidar, LiDAR 2017):
  DSM  = ground (DTM) + buildings only (building mask from NYC footprints); trees go in CDSM
  CDSM = canopy height above ground (refined CHM)
  DEM  = DTM
Scenarios (CDSM edits only):
  S0_current        existing 2017 canopy
  S1_plant_10yr     + one tree at each Area A core candidate site (empty / removed / dead): height 7 m, crown diameter 5 m
  S2_plant_20yr     same sites: height 11 m, crown diameter 8 m
  Crown sizes are SCENARIO ASSUMPTIONS for a generic medium street tree, pending USFS Urban Tree
  Database growth curves (RDS-2016-0005). Crowns are clipped where they would overlap buildings.
Shadow reach capped at 150 m (machine tile limit); tallest buildings ~60 m, so only hours with sun < ~22 deg are affected.
Weather: 24 Jun 2025 (hottest clear summer day 2019-2025 in ERA5, Open-Meteo archive), hours 07-20 EDT.
  ERA5 air temperature shifted by -2.4 C so the daily max equals the mean of observed maxima at
  Central Park (37.2 C) and LaGuardia (38.3 C) (NOAA ACIS). RH, radiation, wind: ERA5 as is.
Outputs: data/processed/solweig/<scenario>/ (SOLWEIG GeoTIFFs) + tmrt_<scenario>_<HH>.tif copies.
"""
import json
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import solweig
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]
L = ROOT / "data/raw/lidar"
OUT = ROOT / "data/processed/solweig"; OUT.mkdir(parents=True, exist_ok=True)
TA_OFFSET = -2.4
DAY = "2025-06-24"
HOURS = list(range(7, 21))

core = gpd.read_file(ROOT / "data/aoi/area_a_core.geojson").to_crs(32618)
x0, y0, x1, y1 = core.total_bounds + np.array([-150, -150, 150, 150])


def clip(name):
    with rasterio.open(L / name) as s:
        w = from_bounds(x0, y0, x1, y1, s.transform).round_offsets().round_lengths()
        return s.read(1, window=w).astype("float32"), s.window_transform(w), s.profile


dtm, T, prof = clip("dtm_1m.tif")
dsm, _, _ = clip("dsm_1m.tif")
bldg, _, _ = clip("bldg_1m.tif")
chm, _, _ = clip("chm_1m.tif")
bldg = bldg > 0
dsm_b = np.where(bldg, np.maximum(dsm, dtm + 2.5), dtm).astype("float32")  # buildings only
H, W = dtm.shape

sites = gpd.read_file(ROOT / "data/processed/sites_area_a.gpkg")
cand = sites[(sites.in_core.astype(str) == "True") & (sites.site_class != "living_tree")].to_crs(32618)
yy, xx = np.mgrid[0:H, 0:W]
cx = T.c + (xx + 0.5) * T.a; cy = T.f + (yy + 0.5) * T.e


def add_trees(base, height, diam):
    c = base.copy()
    r = diam / 2
    for p in cand.geometry:
        col = int((p.x - T.c) / T.a); row = int((p.y - T.f) / T.e)
        k = int(np.ceil(r)) + 1
        r0, r1, c0, c1 = max(row - k, 0), min(row + k + 1, H), max(col - k, 0), min(col + k + 1, W)
        d = np.hypot(cx[r0:r1, c0:c1] - p.x, cy[r0:r1, c0:c1] - p.y)
        crown = (d <= r) & ~bldg[r0:r1, c0:c1]
        # rounded crown top: full height at centre, 80% at edge
        h = height * (1 - 0.2 * (d / r) ** 2)
        c[r0:r1, c0:c1] = np.where(crown, np.maximum(c[r0:r1, c0:c1], h), c[r0:r1, c0:c1])
    return c.astype("float32")


SCEN = {"S0_current": chm, "S1_plant_10yr": add_trees(chm, 7.0, 5.0), "S2_plant_20yr": add_trees(chm, 11.0, 8.0)}

# weather
w = json.load(open(ROOT / "data/raw/weather/era5_openmeteo_mott_haven_2019_2025.json"))["hourly"]
h = pd.DataFrame(w); h["time"] = pd.to_datetime(h.time)
h = h[(h.time.dt.strftime("%Y-%m-%d") == DAY) & h.time.dt.hour.isin(HOURS)]
weather = [solweig.Weather(datetime=t.to_pydatetime(), ta=float(ta) + TA_OFFSET, rh=float(rh), global_rad=float(sw),
                           ws=float(ws), pressure=float(ps))
           for t, ta, rh, sw, ws, ps in zip(h.time, h.temperature_2m, h.relative_humidity_2m, h.shortwave_radiation,
                                             h.wind_speed_10m, h.surface_pressure)]
loc = solweig.Location(latitude=40.811, longitude=-73.926, altitude=10, utc_offset=-4)
print(f"domain {W}x{H} m | candidates {len(cand)} | weather hours {len(weather)} | Ta max {h.temperature_2m.max() + TA_OFFSET:.1f} C")

summary = {}
for name, cdsm in SCEN.items():
    sd = OUT / name; sd.mkdir(exist_ok=True)
    surf = solweig.SurfaceData.prepare(dsm=dsm_b, cdsm=cdsm, dem=dtm, pixel_size=1.0, cdsm_relative=True)
    res = solweig.calculate(surface=surf, weather=weather, location=loc, output_dir=str(sd), outputs=["tmrt"], max_shadow_distance_m=150.0)
    summary[name] = {"added_canopy_m2": int(((cdsm > 0.5) & ~(chm > 0.5)).sum())}
    print(name, "done", summary[name], flush=True)
(OUT / "_run.json").write_text(json.dumps({"domain_bounds_utm": [x0, y0, x1, y1], "transform": list(T)[:6],
                                            "day": DAY, "hours": HOURS, "ta_offset": TA_OFFSET, **summary}, indent=2))
np.save(OUT / "grid_transform.npy", np.array(list(T)[:6]))
