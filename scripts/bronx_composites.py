"""Bronx-wide summer composites for model features (Planetary Computer, EPSG:32618).

  data/processed/bronx/landsat_lst_summer_median.tif  30 m, Landsat 8/9, Jun-Aug 2019-2026, scene cloud <= 10 %, QA-masked
  data/processed/bronx/s2_ndvi_summer_median.tif      10 m, Sentinel-2 L2A, Jun-Aug 2019-2026, scene cloud <= 10 %, SCL-masked
"""
from pathlib import Path

import numpy as np
import planetary_computer as pc
import rioxarray  # noqa: F401
from odc.stac import load
from pystac_client import Client

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/processed/bronx"; OUT.mkdir(parents=True, exist_ok=True)
BBOX = (-73.935, 40.784, -73.765, 40.918)
cat = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)


def items(coll, extra):
    out = []
    for y in range(2019, 2027):
        out += list(cat.search(collections=[coll], bbox=BBOX, datetime=f"{y}-06-01/{y}-08-31", query=extra).items())
    return out


li = items("landsat-c2-l2", {"eo:cloud_cover": {"lte": 10}, "platform": {"in": ["landsat-8", "landsat-9"]}})
ds = load(li, bands=["lwir11", "qa_pixel"], bbox=BBOX, crs="EPSG:32618", resolution=30, chunks={"x": 2048, "y": 2048}, groupby="solar_day")
qa = ds.qa_pixel.astype("uint16")
bad = ((qa & (1 << 1 | 1 << 2 | 1 << 3 | 1 << 4)) > 0) | (ds.lwir11 == 0)
lst = (ds.lwir11.astype("float32") * 0.00341802 + 149.0 - 273.15).where(~bad)
med = lst.median("time", skipna=True).compute().rio.write_crs("EPSG:32618")
med.rio.write_nodata(np.nan, inplace=True); med.rio.to_raster(OUT / "landsat_lst_summer_median.tif", compress="deflate")
print("landsat scenes", len(li), "median LST range", float(np.nanmin(med)), float(np.nanmax(med)))

si = items("sentinel-2-l2a", {"eo:cloud_cover": {"lte": 10}})
# Fixes (audit Nov 2026): one product per sensing time; subtract BOA_ADD_OFFSET (1000) for baseline >= 04.00
seen = {}
for it in sorted(si, key=lambda i: float(i.properties.get("s2:processing_baseline", 0))):
    seen[(it.datetime, it.properties.get("s2:mgrs_tile"))] = it
si = list(seen.values())
parts = []
for is_new in (False, True):
    grp = [i for i in si if (float(i.properties.get("s2:processing_baseline", 0)) >= 4.0) == is_new]
    if not grp:
        continue
    ds = load(grp, bands=["B04", "B08", "SCL"], bbox=BBOX, crs="EPSG:32618", resolution=10, chunks={"x": 2048, "y": 2048}, groupby="solar_day")
    off = 1000.0 if is_new else 0.0
    b4 = ds.B04.astype("float32") - off; b8 = ds.B08.astype("float32") - off
    ok = ds.SCL.isin([4, 5, 6, 7]) & (b4 > 0) & (b8 > 0)
    parts.append(((b8 - b4) / (b8 + b4).clip(min=1)).where(ok))
import xarray as xr
nd = xr.concat(parts, dim="time")
med = nd.median("time", skipna=True).compute().rio.write_crs("EPSG:32618")
med.rio.write_nodata(np.nan, inplace=True); med.rio.to_raster(OUT / "s2_ndvi_summer_median.tif", compress="deflate")
print("s2 unique acquisitions", len(si), "ndvi range", float(np.nanmin(med)), float(np.nanmax(med)))
