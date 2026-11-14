"""Mosaic newest-first across NAIP years to fill coverage gaps. Download all 4 NAIP bands (R,G,B,NIR) for Area A context via rasterio (odc.stac kept only band 1).
Output: data/raw/naip/naip_<year>_context.tif, EPSG:32618, 0.6 m, uint8."""
from pathlib import Path
import geopandas as gpd, numpy as np, planetary_computer as pc, rasterio
from rasterio.merge import merge
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from pystac_client import Client

ROOT = Path(__file__).resolve().parents[1]
ctx = gpd.read_file(ROOT / "data/aoi/area_a_context.geojson")
b = ctx.to_crs(32618).total_bounds
cat = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
items = list(cat.search(collections=["naip"], intersects=ctx.geometry.iloc[0].__geo_interface__, datetime="2021-01-01/2024-12-31").items())
years = sorted({int(i.properties["naip:year"]) for i in items}, reverse=True)
yr = years[0]
res = 0.6
W, H = int(np.ceil((b[2]-b[0])/res)), int(np.ceil((b[3]-b[1])/res))
T = from_origin(b[0], b[3], res, res)
out = np.zeros((4, H, W), "uint8")
filled = np.zeros((H, W), bool); used = []
for y in years:
  for it in [i for i in items if int(i.properties["naip:year"]) == y]:
    with rasterio.open(it.assets["image"].href) as src, WarpedVRT(src, crs="EPSG:32618", transform=T, width=W, height=H, resampling=Resampling.bilinear) as v:
        a = v.read()
        m = a.any(axis=0) & ~filled
        if m.any():
            out[:, m] = a[:, m]; filled |= m; used.append((y, str(it.datetime.date()), round(float(m.mean()), 3)))
  if filled.all(): break
f = ROOT / f"data/raw/naip/naip_{yr}_context.tif"
with rasterio.open(f, "w", driver="GTiff", height=H, width=W, count=4, dtype="uint8", crs="EPSG:32618", transform=T, compress="deflate", tiled=True) as d:
    d.write(out); d.descriptions = ("red", "green", "blue", "nir")
print(yr, used, out.shape, "nodata frac", float((~out.any(axis=0)).mean()))
