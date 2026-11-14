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
ds = load(si, bands=["B04", "B08", "SCL"], bbox=BBOX, crs="EPSG:32618", resolution=10, chunks={"x": 2048, "y": 2048}, groupby="solar_day")
ok = ds.SCL.isin([4, 5, 6, 7])
nd = ((ds.B08.astype("float32") - ds.B04) / (ds.B08.astype("float32") + ds.B04).clip(min=1)).where(ok)
med = nd.median("time", skipna=True).compute().rio.write_crs("EPSG:32618")
med.rio.write_nodata(np.nan, inplace=True); med.rio.to_raster(OUT / "s2_ndvi_summer_median.tif", compress="deflate")
print("s2 scenes", len(si), "ndvi range", float(np.nanmin(med)), float(np.nanmax(med)))
