"""Download ECOSTRESS L2T LSTE v002 (70 m tiled LST) summer granules for Area A context.

Auth: reads a NASA Earthdata *user token* from the file %USERPROFILE%\\.earthdata_token
(created by the user at https://urs.earthdata.nasa.gov -> Generate Token). The token is
never printed or stored elsewhere.

For each granule: downloads the LST and cloud layers (the QC and LST-error layers are NOT yet used: known gap), clips to the context bbox,
converts LST to deg C, masks cloud, writes data/raw/ecostress/<granule>_lst_c.tif and
an inventory CSV with the local (EDT) acquisition hour.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.io import MemoryFile
from rasterio.mask import mask

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/ecostress"; OUT.mkdir(parents=True, exist_ok=True)
tok_file = Path.home() / ".earthdata_token"
if not tok_file.exists():
    sys.exit(f"Token file not found: {tok_file}. Create it first (see docs).")
S = requests.Session()
S.headers["Authorization"] = f"Bearer {tok_file.read_text().strip()}"

ctx = gpd.read_file(ROOT / "data/aoi/area_a_context.geojson")
bbox = ",".join(map(str, ctx.total_bounds))
years = [int(a) for a in sys.argv[1:]] or list(range(2019, 2027))


def granules(y):
    page, out = 1, []
    while True:
        r = requests.get("https://cmr.earthdata.nasa.gov/search/granules.json", params={
            "short_name": "ECO_L2T_LSTE", "version": "002", "bounding_box": bbox,
            "temporal": f"{y}-06-01T00:00:00Z,{y}-08-31T23:59:59Z", "page_size": 200, "page_num": page}, timeout=120)
        e = r.json()["feed"]["entry"]
        out += e
        if len(e) < 200:
            return out
        page += 1


def read_clip(url):
    r = S.get(url, timeout=300); r.raise_for_status()
    with MemoryFile(r.content) as mf, mf.open() as src:
        geom = ctx.to_crs(src.crs).geometry
        arr, tr = mask(src, geom, crop=True, filled=False)
        return arr[0], tr, src.crs, src.profile


rows = []
for y in years:
    for g in granules(y):
        links = [l["href"] for l in g.get("links", []) if l["href"].endswith(".tif") and l["href"].startswith("https")]
        lst_u = next((u for u in links if u.endswith("_LST.tif")), None)
        cld_u = next((u for u in links if u.endswith("_cloud.tif")), None)
        if not lst_u:
            continue
        name = Path(lst_u).stem
        f = OUT / f"{name}_c.tif"
        t = datetime.fromisoformat(g["time_start"].replace("Z", "+00:00"))
        rec = {"granule": g["title"], "utc": t.isoformat(), "local_hour_edt": (t - timedelta(hours=4)).hour}
        try:
            if not f.exists():
                lst, tr, crs, prof = read_clip(lst_u)
                lst = np.where(lst.mask, np.nan, lst.astype("float32") - 273.15)
                if cld_u:
                    cld, *_ = read_clip(cld_u)
                    lst[np.asarray(cld.filled(1)) > 0] = np.nan
                prof.update(height=lst.shape[0], width=lst.shape[1], transform=tr, dtype="float32", nodata=np.nan, count=1, compress="deflate")
                with rasterio.open(f, "w", **prof) as d:
                    d.write(lst, 1)
            with rasterio.open(f) as d:
                a = d.read(1)
            rec["valid_frac"] = float(np.isfinite(a).mean())
            rec["status"] = "ok"
        except Exception as e:
            rec["status"] = f"error {e.__class__.__name__}: {str(e)[:120]}"
        rows.append(rec)
        print(rec)

pd.DataFrame(rows).to_csv(ROOT / "data/raw/ecostress_scenes.csv", index=False)
