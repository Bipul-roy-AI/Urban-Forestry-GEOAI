"""Count usable satellite scenes over Area A (search only, no downloads).

- Landsat C2 L2, Sentinel-2 L2A, NAIP via Microsoft Planetary Computer STAC (free, no key).
- ECOSTRESS LST (L2 LSTE v2) via NASA CMR search (free; downloading needs an Earthdata login).
Summer = June-August. Writes data/raw/_audit_satellite.json.
"""
import json
from collections import Counter
from pathlib import Path

import geopandas as gpd
import requests
from pystac_client import Client

ROOT = Path(__file__).resolve().parents[1]
core = gpd.read_file(ROOT / "data/aoi/area_a_core.geojson").geometry.iloc[0]
geom = core.__geo_interface__
bbox = list(core.bounds)
out = {}

pc = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")


def summer_scenes(collection, years, cloud_key="eo:cloud_cover", max_cloud=20, extra=None):
    per_year = Counter()
    clear = Counter()
    for y in years:
        q = {cloud_key: {"lt": 100}} if cloud_key else None
        items = pc.search(collections=[collection], intersects=geom, datetime=f"{y}-06-01/{y}-08-31",
                          query={**(q or {}), **(extra or {})} or None).item_collection()
        for it in items:
            per_year[y] += 1
            if cloud_key and it.properties.get(cloud_key, 100) <= max_cloud:
                clear[y] += 1
    return {"summer_scenes": dict(per_year), f"cloud<={max_cloud}%": dict(clear)}


years = list(range(2019, 2026 + 1))
out["landsat-c2-l2 (L8/L9, LST 100 m -> 30 m)"] = summer_scenes("landsat-c2-l2", years)
out["sentinel-2-l2a (10 m)"] = summer_scenes("sentinel-2-l2a", years)

naip = pc.search(collections=["naip"], intersects=geom).item_collection()
out["naip (0.6 m, RGB+NIR)"] = sorted({(i.properties.get("naip:year"), i.properties.get("gsd")) for i in naip})

# ECOSTRESS via NASA CMR
cmr = "https://cmr.earthdata.nasa.gov/search/granules.json"
eco = {}
for short in ["ECO_L2T_LSTE", "ECO2LSTE"]:
    yearly = {}
    hours = Counter()
    for y in years:
        params = {"short_name": short, "bounding_box": ",".join(map(str, bbox)),
                  "temporal": f"{y}-06-01T00:00:00Z,{y}-08-31T23:59:59Z", "page_size": 2000}
        r = requests.get(cmr, params=params, timeout=120)
        entries = r.json().get("feed", {}).get("entry", [])
        yearly[y] = len(entries)
        for e in entries:
            t = e.get("time_start", "")
            if len(t) > 13:
                # local EDT = UTC-4
                hours[(int(t[11:13]) - 4) % 24] += 1
    eco[short] = {"summer_granules": yearly, "local_hour_EDT_histogram": dict(sorted(hours.items()))}
out["ECOSTRESS LST (~70 m)"] = eco

p = ROOT / "data/raw/_audit_satellite.json"
p.write_text(json.dumps(out, indent=2, default=str))
print(json.dumps(out, indent=2, default=str))
