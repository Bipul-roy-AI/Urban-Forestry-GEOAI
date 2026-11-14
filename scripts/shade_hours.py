"""Hourly shadow casting on the 1 m LiDAR surface for a representative hot-summer day.

Day: 15 July (mid-summer), hours 08:00-19:00 EDT. Sun position from NOAA solar equations.
Two surfaces:
  total    = DSM (buildings + 2017 trees)          -> shade that exists today (approx.)
  bldg     = DTM + building heights only           -> shade from buildings alone
Outputs (data/processed/shade/):
  shade_total_hours.tif, shade_bldg_hours.tif      hours in shade, 08-19 EDT (12 time steps)
  shade_bldg_afternoon_hours.tif                   hours in building shade, 13-17 EDT (peak heat)
  sun_hours_bldg.tif                               12 - shade_bldg_hours (sun available to a new tree)
Ray-march to 200 m; sun altitude < 5 deg = all shade. Edges (within 200 m of the grid border) are
less reliable for low sun angles because outside obstacles are unknown.
"""
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
L = ROOT / "data/raw/lidar"
OUT = ROOT / "data/processed/shade"; OUT.mkdir(parents=True, exist_ok=True)

with rasterio.open(L / "dsm_1m.tif") as s:
    dsm = s.read(1).astype("float32"); prof = s.profile; T = s.transform
dtm = rasterio.open(L / "dtm_1m.tif").read(1).astype("float32")
bldg = rasterio.open(L / "bldg_1m.tif").read(1).astype(bool)
bsurf = np.where(bldg, np.maximum(dsm, dtm), dtm).astype("float32")

H, W = dsm.shape
cx, cy = T * (W / 2, H / 2)
lon, lat = Transformer.from_crs(32618, 4326, always_xy=True).transform(cx, cy)


def sun_position(dt_utc, lat, lon):
    """NOAA algorithm. Returns (altitude_deg, azimuth_deg clockwise from north)."""
    jd = dt_utc.timestamp() / 86400.0 + 2440587.5
    t = (jd - 2451545.0) / 36525.0
    L0 = (280.46646 + t * (36000.76983 + 0.0003032 * t)) % 360
    M = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    C = (math.sin(math.radians(M)) * (1.914602 - t * (0.004817 + 0.000014 * t))
         + math.sin(math.radians(2 * M)) * (0.019993 - 0.000101 * t) + math.sin(math.radians(3 * M)) * 0.000289)
    lam = L0 + C - 0.00569 - 0.00478 * math.sin(math.radians(125.04 - 1934.136 * t))
    eps = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
    eps += 0.00256 * math.cos(math.radians(125.04 - 1934.136 * t))
    dec = math.degrees(math.asin(math.sin(math.radians(eps)) * math.sin(math.radians(lam))))
    y = math.tan(math.radians(eps / 2)) ** 2
    eot = 4 * math.degrees(y * math.sin(2 * math.radians(L0)) - 2 * e * math.sin(math.radians(M))
                           + 4 * e * y * math.sin(math.radians(M)) * math.cos(2 * math.radians(L0))
                           - 0.5 * y * y * math.sin(4 * math.radians(L0)) - 1.25 * e * e * math.sin(2 * math.radians(M)))
    minutes = dt_utc.hour * 60 + dt_utc.minute + dt_utc.second / 60
    tst = (minutes + eot + 4 * lon) % 1440
    ha = tst / 4 - 180
    zen = math.degrees(math.acos(math.sin(math.radians(lat)) * math.sin(math.radians(dec))
                                 + math.cos(math.radians(lat)) * math.cos(math.radians(dec)) * math.cos(math.radians(ha))))
    az = math.degrees(math.atan2(math.sin(math.radians(ha)),
                                 math.cos(math.radians(ha)) * math.sin(math.radians(lat)) - math.tan(math.radians(dec)) * math.cos(math.radians(lat))))
    return 90 - zen, (az + 180) % 360


def shadow(surf, alt, az, maxdist=200):
    if alt < 5:
        return np.ones(surf.shape, bool)
    tan_a = math.tan(math.radians(alt))
    dx, dy = math.sin(math.radians(az)), -math.cos(math.radians(az))  # toward sun; rows grow southward
    sh = np.zeros(surf.shape, bool)
    zmax = float(np.nanmax(surf))
    seen = set()
    for d in range(1, maxdist + 1):
        ox, oy = int(round(d * dx)), int(round(d * dy))
        if (ox, oy) in seen:
            continue
        seen.add((ox, oy))
        need = d * tan_a
        if need > zmax - float(np.nanmin(surf)):
            break
        src = np.full(surf.shape, -np.inf, "float32")
        ys, ye = max(0, -oy), min(H, H - oy)
        xs, xe = max(0, -ox), min(W, W - ox)
        src[ys:ye, xs:xe] = surf[ys + oy:ye + oy, xs + ox:xe + ox]
        sh |= (src - surf) > need
    return sh


edt = timezone(timedelta(hours=-4))
hours = list(range(8, 20))
tot = np.zeros((H, W), "uint8"); bl = np.zeros((H, W), "uint8"); bl_aft = np.zeros((H, W), "uint8")
for h in hours:
    t = datetime(2026, 7, 15, h, 0, tzinfo=edt).astimezone(timezone.utc)
    alt, az = sun_position(t, lat, lon)
    s_tot = shadow(dsm, alt, az); s_bl = shadow(bsurf, alt, az)
    tot += s_tot; bl += s_bl
    if 13 <= h <= 17:
        bl_aft += s_bl
    print(f"{h:02d}:00 EDT alt={alt:5.1f} az={az:5.1f} shade_total={s_tot.mean():.2f} shade_bldg={s_bl.mean():.2f}", flush=True)

p = prof.copy(); p.update(dtype="uint8", nodata=None)
for name, arr in [("shade_total_hours", tot), ("shade_bldg_hours", bl), ("shade_bldg_afternoon_hours", bl_aft),
                  ("sun_hours_bldg", (len(hours) - bl).astype("uint8"))]:
    with rasterio.open(OUT / f"{name}.tif", "w", **p) as d:
        d.write(arr, 1)
print("done")
