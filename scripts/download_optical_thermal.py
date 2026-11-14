"""Download NAIP 2022, Landsat 8/9 summer LST and Sentinel-2 summer scenes for Area A context.

Source: Microsoft Planetary Computer STAC (free, anonymous signed URLs).
Outputs (EPSG:32618, UTM 18N) under data/raw/:
  naip/naip_<year>_context.tif               4 bands R,G,B,NIR, 0.6 m
  landsat_lst/<scene>_lst_c.tif              land surface temperature (deg C), cloud-masked, 30 m grid
  sentinel2/<scene>_s2.tif                   B02,B03,B04,B08,B11 reflectance x1e4, SCL, 10 m
  *_scenes.csv                               scene inventories
Summer = Jun-Aug, scene cloud cover <= 20 %.
"""
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import planetary_computer as pc
import rasterio
import rioxarray  # noqa: F401  (registers .rio)
from odc.stac import load
from pystac_client import Client

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CRS = "EPSG:32618"
ctx = gpd.read_file(ROOT / "data/aoi/area_a_context.geojson")
bbox = tuple(ctx.total_bounds)
geom = ctx.geometry.iloc[0].__geo_interface__
cat = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
YEARS = range(2019, 2027)
what = set(sys.argv[1:]) or {"naip", "landsat", "s2"}


def search(coll, dt, query=None):
    return list(cat.search(collections=[coll], intersects=geom, datetime=dt, query=query).items())


# ---------------- NAIP (latest leaf-on year) ----------------
if "naip" in what:
    out = RAW / "naip"; out.mkdir(parents=True, exist_ok=True)
    items = search("naip", "2021-01-01/2023-12-31")
    yr = max(int(i.properties["naip:year"]) for i in items)
    items = [i for i in items if int(i.properties["naip:year"]) == yr]
    ds = load(items, bands=["image"], bbox=bbox, crs=CRS, resolution=0.6, groupby="solar_day", chunks={})
    da = ds["image"].isel(time=0) if "time" in ds["image"].dims else ds["image"]
    da = da.compute()
    da.rio.write_crs(CRS, inplace=True)
    f = out / f"naip_{yr}_context.tif"
    da.rio.to_raster(f, compress="deflate", tiled=True)
    print("NAIP", yr, [i.datetime.date() for i in items], da.shape, f)

# ---------------- Landsat LST ----------------
if "landsat" in what:
    out = RAW / "landsat_lst"; out.mkdir(parents=True, exist_ok=True)
    rows = []
    for y in YEARS:
        items = search("landsat-c2-l2", f"{y}-06-01/{y}-08-31",
                       {"eo:cloud_cover": {"lte": 20}, "platform": {"in": ["landsat-8", "landsat-9"]}})
        for it in items:
            f = out / f"{it.id}_lst_c.tif"
            if not f.exists():
                ds = load([it], bands=["lwir11", "qa_pixel"], bbox=bbox, crs=CRS, resolution=30).isel(time=0)
                qa = ds.qa_pixel.values.astype(np.uint16)
                bad = (qa & (1 << 1 | 1 << 2 | 1 << 3 | 1 << 4)) > 0  # dilated cloud, cirrus, cloud, shadow
                lst = ds.lwir11.values.astype("float32") * 0.00341802 + 149.0 - 273.15
                lst[(ds.lwir11.values == 0) | bad] = np.nan
                da = ds.lwir11.copy(data=lst).rio.write_crs(CRS)
                da.rio.write_nodata(np.nan, inplace=True)
                da.rio.to_raster(f, compress="deflate")
                valid = float(np.isfinite(lst).mean())
            else:
                valid = None
            rows.append({"id": it.id, "datetime": it.datetime, "platform": it.properties["platform"],
                         "scene_cloud": it.properties["eo:cloud_cover"], "valid_frac_context": valid})
            print("LST", it.id, valid)
    pd.DataFrame(rows).to_csv(RAW / "landsat_lst_scenes.csv", index=False)

# ---------------- Sentinel-2 ----------------
if "s2" in what:
    out = RAW / "sentinel2"; out.mkdir(parents=True, exist_ok=True)
    rows = []
    bands = ["B02", "B03", "B04", "B08", "B11", "SCL"]
    for y in YEARS:
        items = search("sentinel-2-l2a", f"{y}-06-01/{y}-08-31", {"eo:cloud_cover": {"lte": 20}})
        for it in items:
            f = out / f"{it.id}_s2.tif"
            if not f.exists():
                try:
                    ds = load([it], bands=bands, bbox=bbox, crs=CRS, resolution=10).isel(time=0)
                except Exception:  # signed URL expired -> re-sign once and retry
                    it = pc.sign(it)
                    ds = load([it], bands=bands, bbox=bbox, crs=CRS, resolution=10).isel(time=0)
                arr = ds.to_array("band").astype("uint16").rio.write_crs(CRS)
                arr.attrs["long_name"] = tuple(bands)
                arr.rio.to_raster(f, compress="deflate")
                scl = ds.SCL.values
                clear = float(np.isin(scl, [4, 5, 6, 7]).mean())  # veg, bare, water, unclassified
            else:
                with rasterio.open(f) as r:
                    clear = float(np.isin(r.read(6), [4, 5, 6, 7]).mean())
            rows.append({"id": it.id, "datetime": it.datetime, "scene_cloud": it.properties["eo:cloud_cover"],
                         "clear_frac_context": clear,
                         "baseline": it.properties.get("s2:processing_baseline")})
            print("S2", it.id, clear)
    pd.DataFrame(rows).to_csv(RAW / "sentinel2_scenes.csv", index=False)
