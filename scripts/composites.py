"""Summer composites on a common 30 m (Landsat) / 70 m (ECOSTRESS) / 10 m (S2) grid.

  landsat_lst_summer_median.tif   median LST (deg C) of clear summer pixels 2019-2026 (~10:30 EDT)
  landsat_lst_summer_p90.tif      90th percentile (hot-day signal)
  ecostress_lst_afternoon_median.tif  median of clear 12-16 EDT pixels (on the most common tile grid)
  s2_ndvi_summer_median.tif       median NDVI of SCL-clear pixels
Each pixel uses only scenes where it is valid; *_nobs.tif gives the count.
"""
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import Resampling, reproject

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
OUT = ROOT / "data/processed/composites"; OUT.mkdir(parents=True, exist_ok=True)


def write(name, arr, prof, dtype="float32"):
    p = prof.copy(); p.update(dtype=dtype, count=1, nodata=np.nan if dtype.startswith("float") else None, compress="deflate")
    with rasterio.open(OUT / name, "w", **p) as d:
        d.write(arr.astype(dtype), 1)


def stack(files, read):
    ref = rasterio.open(files[0]); prof = ref.profile
    arrs = []
    for f in files:
        with rasterio.open(f) as s:
            a = read(s)
            if s.shape != ref.shape or s.transform != ref.transform:
                b = np.full(ref.shape, np.nan, "float32")
                reproject(a, b, src_transform=s.transform, src_crs=s.crs, dst_transform=ref.transform, dst_crs=ref.crs,
                          src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.bilinear)
                a = b
            arrs.append(a)
    return np.stack(arrs), prof


# Landsat
lf = sorted((RAW / "landsat_lst").glob("*_lst_c.tif"))
st, prof = stack(lf, lambda s: s.read(1).astype("float32"))
write("landsat_lst_summer_median.tif", np.nanmedian(st, 0), prof)
write("landsat_lst_summer_p90.tif", np.nanpercentile(st, 90, axis=0), prof)
write("landsat_lst_nobs.tif", np.isfinite(st).sum(0), prof, "uint16")
print("landsat scenes", len(lf))

# ECOSTRESS afternoon
inv = pd.read_csv(RAW / "ecostress_scenes.csv")
aft = inv[(inv.status == "ok") & inv.local_hour_edt.between(12, 16)]
files = [f for f in (RAW / "ecostress").glob("*_c.tif") if any(g in f.name for g in aft.granule)]
shapes = Counter(rasterio.open(f).shape for f in files)
common = shapes.most_common(1)[0][0]
files = sorted(f for f in files if rasterio.open(f).shape == common)
st, prof = stack(files, lambda s: s.read(1).astype("float32"))
st[st < 0] = np.nan  # residual bad values
write("ecostress_lst_afternoon_median.tif", np.nanmedian(st, 0), prof)
write("ecostress_lst_afternoon_nobs.tif", np.isfinite(st).sum(0), prof, "uint16")
print("ecostress afternoon granules", len(files))

# Sentinel-2 NDVI
sf = sorted((RAW / "sentinel2").glob("*_s2.tif"))


def ndvi(s):
    b4, b8, scl = s.read(3).astype("float32"), s.read(4).astype("float32"), s.read(6)
    v = (b8 - b4) / np.maximum(b8 + b4, 1)
    v[~np.isin(scl, [4, 5, 6, 7])] = np.nan
    return v


st, prof = stack(sf, ndvi)
write("s2_ndvi_summer_median.tif", np.nanmedian(st, 0), prof)
write("s2_ndvi_nobs.tif", np.isfinite(st).sum(0), prof, "uint16")
print("s2 scenes", len(sf))
