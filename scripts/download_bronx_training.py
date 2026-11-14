"""Download Bronx-wide layers for the survival/health model (Area B). Saves GeoParquet in data/raw/bronx/.

  planting_spaces (boroughcode='Bronx'), tree_points (Bronx bbox, later inner-joined to Bronx spaces),
  building footprints, curbs, PLUTO (borough='BX'), sidewalks.
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely import wkt as shp_wkt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/bronx"; OUT.mkdir(parents=True, exist_ok=True)
API = "https://data.cityofnewyork.us/resource"
BBOX = (-73.935, 40.784, -73.765, 40.918)  # Bronx extent (W, S, E, N)


def pull(ds, where, select=None, page=50000):
    rows, off = [], 0
    while True:
        p = {"$where": where, "$limit": page, "$offset": off, "$order": ":id"}
        if select:
            p["$select"] = select
        r = requests.get(f"{API}/{ds}.json", params=p, timeout=600); r.raise_for_status()
        d = r.json(); rows += d; off += len(d)
        print(ds, off, flush=True)
        if len(d) < page:
            return pd.DataFrame(rows)


def to_gdf(df, geom_col):
    g = df[geom_col]
    if isinstance(g.dropna().iloc[0], dict):
        geom = gpd.GeoSeries([shp_from_geojson(x) for x in g], crs=4326)
    else:
        geom = gpd.GeoSeries([shp_wkt.loads(x) if isinstance(x, str) else None for x in g], crs=4326)
    return gpd.GeoDataFrame(df.drop(columns=[geom_col]), geometry=geom, crs=4326)


def shp_from_geojson(x):
    from shapely.geometry import shape
    return shape(x) if isinstance(x, dict) else None


box = f"within_box({{}}, {BBOX[3]}, {BBOX[0]}, {BBOX[1]}, {BBOX[2]})"

ps = pull("82zj-84is", "boroughcode='Bronx'")
to_gdf(ps, "location").drop(columns=[c for c in ps.columns if c.startswith(":@")], errors="ignore").to_parquet(OUT / "planting_spaces.parquet")

tp = pull("hn5i-inap", box.format("location"))
tp = tp[tp.plantingspaceglobalid.isin(set(ps.globalid))]
print("Bronx tree points after join:", len(tp))
to_gdf(tp.drop(columns=["geometry"], errors="ignore"), "location").drop(
    columns=[c for c in tp.columns if c.startswith(":@")], errors="ignore").to_parquet(OUT / "tree_points.parquet")

bf = pull("5zhs-2jue", box.format("the_geom"), select="the_geom, bin, height_roof, ground_elevation, construction_year")
to_gdf(bf, "the_geom").to_parquet(OUT / "building_footprints.parquet")

cu = pull("5xvt-8cbk", box.format("the_geom"), select="the_geom")
to_gdf(cu, "the_geom").to_parquet(OUT / "curbs.parquet")

pl = pull("64uk-42ks", "borough='BX'", select="bbl, landuse, bldgclass, zonedist1, numfloors, yearbuilt, unitsres, lotarea, latitude, longitude, zipcode")
pl.to_parquet(OUT / "pluto.parquet")
print("done")
