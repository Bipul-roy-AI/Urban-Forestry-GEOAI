"""Fix the LiDAR products: the USGS NYC cloud has no building class (6), so buildings and
trees are both in classes 1/17. Rebuild building mask and canopy height from:
  - NYC building footprints (5zhs-2jue), rasterised to the 1 m LiDAR grid (+1 m buffer)
  - thin-object removal (morphological opening) to drop poles, wires, signs
  - NAIP NDVI > 0.2 (leaf-on 2022) to keep only vegetated cells, when NAIP exists
Writes data/raw/lidar/{bldg_1m,chm_1m,canopy_mask_1m}.tif and updates _lidar_summary.json.
Caveat: LiDAR 2017 vs NAIP 2022 vs footprints 2026, so trees removed or planted in between disagree.
"""
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.warp import Resampling, reproject
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
L = ROOT / "data/raw/lidar"
with rasterio.open(L / "dsm_1m.tif") as s:
    dsm = s.read(1); prof = s.profile; T = s.transform; crs = s.crs
dtm = rasterio.open(L / "dtm_1m.tif").read(1)

fp = gpd.read_file(ROOT / "data/raw/nyc_opendata/5zhs-2jue_building_footprints.geojson").to_crs(crs)
bldg = rasterize(((g, 1) for g in fp.buffer(1.0).geometry), out_shape=dsm.shape, transform=T, dtype="uint8")

ndsm = np.clip(dsm - dtm, 0, None)
cand = (ndsm > 2.0) & (bldg == 0)
cand = ndimage.binary_opening(cand, structure=np.ones((3, 3)))  # remove poles/wires/sign posts

naip_f = next((ROOT / "data/raw/naip").glob("naip_*_context.tif"), None) if (ROOT / "data/raw/naip").exists() else None
used_ndvi = False
if naip_f:
    with rasterio.open(naip_f) as n:
        red = np.zeros(dsm.shape, "float32"); nir = np.zeros(dsm.shape, "float32")
        reproject(n.read(1).astype("float32"), red, src_transform=n.transform, src_crs=n.crs, dst_transform=T, dst_crs=crs, resampling=Resampling.average)
        reproject(n.read(4).astype("float32"), nir, src_transform=n.transform, src_crs=n.crs, dst_transform=T, dst_crs=crs, resampling=Resampling.average)
    ndvi = (nir - red) / np.maximum(nir + red, 1)
    cand &= ndvi > 0.2
    used_ndvi = True
    p = prof.copy(); p.update(dtype="float32")
    with rasterio.open(L / "ndvi_naip_1m.tif", "w", **p) as d: d.write(ndvi.astype("float32"), 1)

chm = np.where(cand, ndsm, 0).astype("float32")
for name, arr, dt in [("bldg_1m", bldg, "uint8"), ("chm_1m", chm, "float32"), ("canopy_mask_1m", cand.astype("uint8"), "uint8")]:
    p = prof.copy(); p.update(dtype=dt)
    with rasterio.open(L / f"{name}.tif", "w", **p) as d: d.write(arr.astype(dt), 1)

core = gpd.read_file(ROOT / "data/aoi/area_a_core.geojson").to_crs(crs)
core_m = rasterize([(core.geometry.iloc[0], 1)], out_shape=dsm.shape, transform=T, dtype="uint8").astype(bool)
s = json.loads((L / "_lidar_summary.json").read_text())
s.update({"refined": True, "ndvi_filter": used_ndvi,
          "building_frac_context": float(bldg.mean()), "canopy_gt2m_frac_context": float(cand.mean()),
          "canopy_gt2m_frac_core": float(cand[core_m].mean()),
          "canopy_height_p50_p95_core": [float(np.percentile(chm[core_m & cand], q)) for q in (50, 95)] if (core_m & cand).any() else None,
          "note": "No building class in USGS cloud; buildings from NYC footprints. Classes 1 and 17 both mix roofs and trees."})
(L / "_lidar_summary.json").write_text(json.dumps(s, indent=2))
print(json.dumps(s, indent=2))
