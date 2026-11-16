"""Module 4a: pedestrian heat (mean radiant temperature, Tmrt) for planting scenarios with SOLWEIG.

Usage:
  python solweig_scenarios.py                     -> S0_current, S1_crown5m, S2_crown8m (generic crowns)
  python solweig_scenarios.py --plans balanced_K30 max_cooling_K30 ...
                                                  -> PLAN_<name>: each tree at its plan's size class

Engine: `solweig` 0.1.0b103 (UMEP-dev; experimental Rust/Python port, parity-tested vs reference UMEP).
Domain: Area A core bbox + 150 m buffer, 1 m grid (EPSG:32618).
Surfaces (LiDAR 2017): DSM = ground + buildings; CDSM = canopy height above ground; DEM = DTM.
Ground materials (audit fix): UMEP land-cover grid: 2 buildings (NYC footprints), 7 water (NAIP NDWI > 0.2),
  5 grass where NAIP NDVI > 0.2 and no building, otherwise 1 dark asphalt. Sidewalk polygons are always paved
  (imagery sees the crown, not the pavement under it); water only where ground elevation < 1.5 m (shadows
  otherwise look like water). Sidewalk concrete has no class in the default table, so it is approximated as asphalt.
  Road pavement under tree crowns outside sidewalk polygons can still be labelled grass (known limit).
Scenarios (CDSM edits only), trees only at sites whose records are consistent (plantable_status == candidate):
  S0_current   existing canopy
  S1_crown5m   one tree per candidate: height 7 m, crown diameter 5 m
  S2_crown8m   one tree per candidate: height 11 m, crown diameter 8 m
  These are ASSUMED CROWN SIZES, not age predictions (no growth model yet).
  PLAN_*       crown by NYC size class: small 5 m/6 m tall, intermediate 6/8, medium 7/9.5, large 8/11;
               a large species without expanded soil is capped at the medium crown.
Time (audit fix): the Open-Meteo archive file is in fixed UTC-5 (its `utc_offset_seconds` = -18000), so
  timestamps are local standard time. Location uses utc_offset = -5 so sun position and weather share one clock.
  Hours 06-19 EST = 07-20 EDT. Open-Meteo radiation is the mean of the preceding hour; SOLWEIG treats the
  timestamp as the end of the interval, so the conventions match.
Weather: 24 Jun 2025; ERA5 air temperature shifted by -2.4 C to match the mean of observed maxima at
  Central Park (37.2 C) and LaGuardia (38.3 C) (NOAA ACIS). RH, radiation, wind: ERA5 as is.
Shadow reach capped at 150 m (machine tile limit).
Outputs: data/processed/solweig/<scenario>/tmrt/*.tif, georeferenced (EPSG:32618) after the run.
"""
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import solweig
from rasterio.features import rasterize
from rasterio.warp import Resampling, reproject
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]
L = ROOT / "data/raw/lidar"
OUT = ROOT / "data/processed/solweig"; OUT.mkdir(parents=True, exist_ok=True)
TA_OFFSET = -2.4
DAY = "2025-06-24"
HOURS_EST = list(range(6, 20))          # 07-20 EDT
CROWN = {"small": (5.0, 6.0), "intermediate": (6.0, 8.0), "medium": (7.0, 9.5), "large": (8.0, 11.0)}  # (diameter, height) m

core = gpd.read_file(ROOT / "data/aoi/area_a_core.geojson").to_crs(32618)
x0, y0, x1, y1 = core.total_bounds + np.array([-150, -150, 150, 150])


def clip(name):
    with rasterio.open(L / name) as s:
        w = from_bounds(x0, y0, x1, y1, s.transform).round_offsets().round_lengths()
        return s.read(1, window=w).astype("float32"), s.window_transform(w)


dtm, T = clip("dtm_1m.tif")
dsm, _ = clip("dsm_1m.tif")
bldg = clip("bldg_1m.tif")[0] > 0
chm, _ = clip("chm_1m.tif")
dsm_b = np.where(bldg, np.maximum(dsm, dtm + 2.5), dtm).astype("float32")
H, W = dtm.shape

# ---- ground materials from NAIP ----
with rasterio.open(next((ROOT / "data/raw/naip").glob("naip_*_context.tif"))) as n:
    band = {}
    for i, k in ((1, "r"), (2, "g"), (4, "nir")):
        a = np.zeros((H, W), "float32")
        reproject(n.read(i).astype("float32"), a, src_transform=n.transform, src_crs=n.crs, dst_transform=T, dst_crs="EPSG:32618", resampling=Resampling.average)
        band[k] = a
ndvi = (band["nir"] - band["r"]) / np.maximum(band["nir"] + band["r"], 1)
ndwi = (band["g"] - band["nir"]) / np.maximum(band["g"] + band["nir"], 1)
# Review fix: aerial imagery sees the tree crown, not the pavement under it, and dark shadows look like water.
# So sidewalk polygons are always paved, and water is only allowed on low ground (river level).
sw_poly = gpd.read_file(next((ROOT / "data/raw/nyc_opendata").glob("*sidewalk*.geojson"))).to_crs(32618)
sidewalk = rasterize(((g, 1) for g in sw_poly.geometry), out_shape=(H, W), transform=T, dtype="uint8").astype(bool)
lc = np.full((H, W), 1, "uint8")
lc[(ndvi > 0.2) & ~sidewalk] = 5
lc[(ndwi > 0.2) & (ndvi < 0) & (dtm < 1.5) & ~sidewalk] = 7
lc[bldg] = 2
assert not np.isin(lc[sidewalk & ~bldg], [5, 7]).any(), "sidewalk pixels must be paved"
print("land cover share:", {k: round(float((lc == v).mean()), 3) for k, v in {"asphalt": 1, "building": 2, "grass": 5, "water": 7}.items()})

sites = gpd.read_file(ROOT / "data/processed/sites_area_a.gpkg").to_crs(32618)
cand = sites[(sites.in_core.astype(str) == "True") & (sites.plantable_status == "candidate")]
yy, xx = np.mgrid[0:H, 0:W]
cx = T.c + (xx + 0.5) * T.a; cy = T.f + (yy + 0.5) * T.e


def add_trees(points, dims):
    """points: iterable of shapely Points; dims: iterable of (diameter, height) per point."""
    c = chm.copy()
    for p, (diam, height) in zip(points, dims):
        r = diam / 2
        col = int((p.x - T.c) / T.a); row = int((p.y - T.f) / T.e); k = int(np.ceil(r)) + 1
        r0, r1, c0, c1 = max(row - k, 0), min(row + k + 1, H), max(col - k, 0), min(col + k + 1, W)
        d = np.hypot(cx[r0:r1, c0:c1] - p.x, cy[r0:r1, c0:c1] - p.y)
        crown = (d <= r) & ~bldg[r0:r1, c0:c1]
        h = height * (1 - 0.2 * (d / r) ** 2)   # rounded top: 80% of height at the crown edge
        c[r0:r1, c0:c1] = np.where(crown, np.maximum(c[r0:r1, c0:c1], h), c[r0:r1, c0:c1])
    return c.astype("float32")


SCEN = {}
args = sys.argv[1:]
if args and args[0] == "--plans":
    geom = sites.set_index("ps_id").geometry
    for name in args[1:]:
        p = pd.read_csv(ROOT / f"data/processed/optimiser/plan_{name}.csv")
        p = p[p.species.fillna("") != ""]
        dims = [CROWN["medium"] if (r.size_class == "large" and not r.expanded_soil) else CROWN[r.size_class] for r in p.itertuples()]
        SCEN["PLAN_" + name] = add_trees([geom[i] for i in p.ps_id], dims)
else:
    SCEN = {"S0_current": chm,
            "S1_crown5m": add_trees(cand.geometry, [(5.0, 7.0)] * len(cand)),
            "S2_crown8m": add_trees(cand.geometry, [(8.0, 11.0)] * len(cand))}

# ---- weather (file is fixed UTC-5; keep that clock) ----
wj = json.load(open(ROOT / "data/raw/weather/era5_openmeteo_mott_haven_2019_2025.json"))
assert wj["utc_offset_seconds"] == -18000, "weather file is expected in fixed UTC-5"
h = pd.DataFrame(wj["hourly"]); h["time"] = pd.to_datetime(h.time)
h = h[(h.time.dt.strftime("%Y-%m-%d") == DAY) & h.time.dt.hour.isin(HOURS_EST)]
weather = [solweig.Weather(datetime=t.to_pydatetime(), ta=float(ta) + TA_OFFSET, rh=float(rh), global_rad=float(sw), ws=float(ws), pressure=float(ps))
           for t, ta, rh, sw, ws, ps in zip(h.time, h.temperature_2m, h.relative_humidity_2m, h.shortwave_radiation, h.wind_speed_10m, h.surface_pressure)]
loc = solweig.Location(latitude=40.811, longitude=-73.926, altitude=10, utc_offset=-5)
# known-time check: solar noon at this longitude on 24 Jun is ~11:58 EST; radiation should peak in the hour ending 12:00 or 13:00 EST
peak = int(h.loc[h.shortwave_radiation.idxmax(), "time"].hour)
assert peak in (12, 13), f"radiation peak at {peak}:00 EST does not match solar noon"
print(f"domain {W}x{H} | candidates {len(cand)} | hours {len(weather)} (EST) | radiation peak hour ending {peak}:00 EST | Ta max {h.temperature_2m.max() + TA_OFFSET:.1f} C")

run_f = OUT / "_run.json"
run = json.loads(run_f.read_text()) if run_f.exists() else {}
run.update({"domain_bounds_utm": [x0, y0, x1, y1], "transform": list(T)[:6], "day": DAY, "hours_est": HOURS_EST,
            "clock": "UTC-5 (EST); add 1 h for EDT", "ta_offset": TA_OFFSET, "n_candidates": int(len(cand))})
prof = dict(driver="GTiff", height=H, width=W, count=1, dtype="float32", crs="EPSG:32618", transform=T, compress="deflate")
for name, cdsm in SCEN.items():
    sd = OUT / name; sd.mkdir(exist_ok=True)
    for f in (sd / "tmrt").glob("*.tif") if (sd / "tmrt").exists() else []:
        f.unlink()
    surf = solweig.SurfaceData.prepare(dsm=dsm_b, cdsm=cdsm, dem=dtm, land_cover=lc, pixel_size=1.0, cdsm_relative=True)
    solweig.calculate(surface=surf, weather=weather, location=loc, output_dir=str(sd), outputs=["tmrt"], max_shadow_distance_m=150.0)
    for f in sd.rglob("*.tif"):                       # audit fix: write CRS + transform into every raster
        with rasterio.open(f) as s:
            a = s.read(1)
        with rasterio.open(f, "w", **{**prof, "dtype": str(a.dtype)}) as d:
            d.write(a, 1)
    new = (cdsm > 0.5) & ~(chm > 0.5)
    run[name] = {"added_canopy_m2": int(new.sum())}
    with rasterio.open(sd / "new_canopy_mask.tif", "w", **{**prof, "dtype": "uint8"}) as d:
        d.write(new.astype("uint8"), 1)
    print(name, "done", run[name], flush=True)
run_f.write_text(json.dumps(run, indent=2))
