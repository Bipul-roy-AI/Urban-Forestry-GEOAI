"""Download NYC 2017 LiDAR (USGS 3DEP EPT 'NY_NewYorkCity', public AWS) for the Area A
context bbox and grid it to 1 m rasters without PDAL.

EPT is EPSG:3857 (z in metres). We read every octree node that intersects the AOI,
filter points to the AOI, reproject to EPSG:32618, and accumulate per-cell statistics:
  dsm_1m.tif   max z of all non-noise points (first surface)
  dtm_1m.tif   min z of ground points (class 2), gaps filled by nearest neighbour
  chm_1m.tif   dsm - dtm where cell is not building and has non-ground, non-building points
  bldg_1m.tif  1 where any class-6 (building) point falls in the cell
  density_1m.tif  points per cell
Outputs -> data/raw/lidar/ ; node cache -> data/raw/lidar/_ept_cache/
"""
import io
import json
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
import laspy
import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.transform import from_origin
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/lidar"; OUT.mkdir(parents=True, exist_ok=True)
CACHE = OUT / "_ept_cache"; CACHE.mkdir(exist_ok=True)
EPT = "https://s3-us-west-2.amazonaws.com/usgs-lidar-public/NY_NewYorkCity"

ctx = gpd.read_file(ROOT / "data/aoi/area_a_context.geojson")
utm = ctx.to_crs(32618).total_bounds
x0, y0 = math.floor(utm[0]), math.floor(utm[1])
x1, y1 = math.ceil(utm[2]), math.ceil(utm[3])
W, H = x1 - x0, y1 - y0
# AOI bbox in 3857 for node selection (pad 50 m)
mb = ctx.to_crs(3857).total_bounds + np.array([-70, -70, 70, 70])

meta = requests.get(f"{EPT}/ept.json", timeout=60).json()
B = meta["bounds"]  # cube: xmin,ymin,zmin,xmax,ymax,zmax


def node_bounds(key):
    d, x, y, z = map(int, key.split("-"))
    s = (B[3] - B[0]) / 2 ** d
    return B[0] + x * s, B[1] + y * s, B[0] + (x + 1) * s, B[1] + (y + 1) * s


def hits(key):
    a = node_bounds(key)
    return not (a[2] < mb[0] or a[0] > mb[2] or a[3] < mb[1] or a[1] > mb[3])


def walk(hier_key, out):
    h = requests.get(f"{EPT}/ept-hierarchy/{hier_key}.json", timeout=60).json()
    for k, n in h.items():
        if not hits(k):
            continue
        if n == -1:
            walk(k, out)
        elif n > 0:
            out.append(k)


keys = []
walk("0-0-0-0", keys)
print("nodes intersecting AOI:", len(keys))


def fetch(k):
    f = CACHE / f"{k}.laz"
    if not f.exists():
        r = requests.get(f"{EPT}/ept-data/{k}.laz", timeout=300); r.raise_for_status()
        f.write_bytes(r.content)
    return f


with ThreadPoolExecutor(8) as ex:
    files = list(ex.map(fetch, keys))
print("downloaded", sum(f.stat().st_size for f in files) / 1e6, "MB")

tr = Transformer.from_crs(3857, 32618, always_xy=True)
dsm = np.full((H, W), -np.inf, "float32")
dtm = np.full((H, W), np.inf, "float32")
veg_top = np.full((H, W), -np.inf, "float32")
bldg = np.zeros((H, W), "uint8")
dens = np.zeros((H, W), "uint32")
classes = {}

for f in files:
    las = laspy.read(f)
    m = (las.x >= mb[0]) & (las.x <= mb[2]) & (las.y >= mb[1]) & (las.y <= mb[3])
    if not m.any():
        continue
    x, y = tr.transform(np.asarray(las.x[m]), np.asarray(las.y[m]))
    z = np.asarray(las.z[m], dtype="float32")
    c = np.asarray(las.classification[m])
    col = np.floor(x - x0).astype(int); row = np.floor(y1 - y).astype(int)
    ok = (col >= 0) & (col < W) & (row >= 0) & (row < H) & ~np.isin(c, [7, 18])
    col, row, z, c = col[ok], row[ok], z[ok], c[ok]
    for v, n in zip(*np.unique(c, return_counts=True)):
        classes[int(v)] = classes.get(int(v), 0) + int(n)
    np.maximum.at(dsm, (row, col), z)
    np.add.at(dens, (row, col), 1)
    g = c == 2
    np.minimum.at(dtm, (row[g], col[g]), z[g])
    b = c == 6
    bldg[row[b], col[b]] = 1
    v = ~np.isin(c, [2, 6, 9])  # not ground, building, water
    np.maximum.at(veg_top, (row[v], col[v]), z[v])

print("class counts:", classes)


def fill(a, bad):
    idx = ndimage.distance_transform_edt(bad, return_distances=False, return_indices=True)
    return a[tuple(idx)]


dtm_f = fill(dtm, ~np.isfinite(dtm))
dsm_f = fill(dsm, ~np.isfinite(dsm))
chm = np.where(np.isfinite(veg_top) & (bldg == 0), veg_top - dtm_f, 0).astype("float32")
chm = np.clip(chm, 0, 60)
bldg = ndimage.binary_closing(bldg, iterations=1).astype("uint8")

prof = dict(driver="GTiff", height=H, width=W, count=1, crs="EPSG:32618",
            transform=from_origin(x0, y1, 1, 1), compress="deflate", tiled=True)
for name, arr, dt in [("dsm_1m", dsm_f, "float32"), ("dtm_1m", dtm_f, "float32"), ("chm_1m", chm, "float32"),
                      ("bldg_1m", bldg, "uint8"), ("density_1m", dens, "uint32")]:
    with rasterio.open(OUT / f"{name}.tif", "w", dtype=dt, **prof) as dst:
        dst.write(arr.astype(dt), 1)

summary = {"nodes": len(keys), "grid": [W, H], "origin_utm18n": [x0, y1], "class_counts": classes,
           "mean_pts_per_m2": float(dens.mean()), "empty_cell_frac": float((dens == 0).mean()),
           "building_frac": float(bldg.mean()), "canopy_gt2m_frac": float(((chm > 2)).mean())}
(OUT / "_lidar_summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
