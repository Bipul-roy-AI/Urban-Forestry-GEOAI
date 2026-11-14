"""Audit NYC Open Data (Socrata) layers for the pilot area and download AOI subsets.

For each dataset: metadata (rows, columns, last update), geometry column, record count
inside Area A core and the Bronx (where meaningful), then saves the Area A *context*
subset to data/raw/nyc_opendata/<id>_<slug>.geojson. Writes a JSON audit table.
"""
import json
import re
import time
from pathlib import Path

import geopandas as gpd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "nyc_opendata"
RAW.mkdir(parents=True, exist_ok=True)
BASE = "https://data.cityofnewyork.us"

core = gpd.read_file(ROOT / "data/aoi/area_a_core.geojson").geometry.iloc[0]
ctx = gpd.read_file(ROOT / "data/aoi/area_a_context.geojson").geometry.iloc[0]

# id, short slug, Bronx filter clause (SoQL) or None
DATASETS = [
    ("hn5i-inap", "forestry_tree_points", None),
    ("82zj-84is", "forestry_planting_spaces", None),
    ("4pt5-3vv4", "forestry_inspections", None),
    ("bdjm-n7q4", "forestry_work_orders", None),
    ("mu46-p9is", "forestry_service_requests", None),
    ("259a-b6s7", "forestry_risk_assessments", None),
    ("uvpi-gqnh", "census2015_trees", "boroname='Bronx'"),
    ("29bw-z7pj", "census2005_trees", None),
    ("ju3b-rwpy", "census2015_blockface", None),
    ("5zhs-2jue", "building_footprints", None),
    ("52n9-sdep", "planimetric_sidewalk", None),
    ("5xvt-8cbk", "planimetric_curbs", None),
    ("5bgh-vtsn", "hydrants", None),
    ("t4f2-8md7", "bus_stop_shelters", None),
    ("df32-vzax", "dep_green_infra_points", None),
    ("64uk-42ks", "pluto", "borough='BX'"),
]


def meta(ds):
    m = requests.get(f"{BASE}/api/views/{ds}.json", timeout=60).json()
    cols = [(c["fieldName"], c["dataTypeName"]) for c in m.get("columns", [])]
    return m, cols


def geom_col(cols):
    for name, t in cols:
        if t in ("point", "multipolygon", "polygon", "multiline", "line", "location", "multipoint"):
            return name, t
    return None, None


def soql(ds, params):
    r = requests.get(f"{BASE}/resource/{ds}.json", params=params, timeout=300)
    r.raise_for_status()
    return r.json()


def wkt(poly):
    return poly.wkt.replace("POLYGON ((", "MULTIPOLYGON (((").replace("))", ")))")


results = []
for ds, slug, bx in DATASETS:
    rec = {"id": ds, "slug": slug}
    try:
        m, cols = meta(ds)
        rec["name"] = m.get("name")
        rec["updated"] = time.strftime("%Y-%m-%d", time.gmtime(m.get("rowsUpdatedAt") or 0))
        rec["n_columns"] = len(cols)
        rec["columns"] = [c for c, _ in cols][:80]
        g, gt = geom_col(cols)
        rec["geom_col"], rec["geom_type"] = g, gt
        total = soql(ds, {"$select": "count(*) as n"})
        rec["rows_total"] = int(total[0]["n"])
        if bx:
            rec["rows_bronx"] = int(soql(ds, {"$select": "count(*) as n", "$where": bx})[0]["n"])
        if not g and {"latitude", "longitude"} <= {c for c, _ in cols}:
            x0, y0, x1, y1 = core.bounds
            X0, Y0, X1, Y1 = ctx.bounds
            box = "latitude between {} and {} and longitude between {} and {}"
            rec["geom_col"] = "latitude/longitude (bbox)"
            rec["rows_core_bbox"] = int(soql(ds, {"$select": "count(*) as n", "$where": box.format(y0, y1, x0, x1)})[0]["n"])
            rows = soql(ds, {"$where": box.format(Y0, Y1, X0, X1), "$limit": 200000})
            rec["rows_context_bbox"] = len(rows)
            df = gpd.pd.DataFrame(rows)
            gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.longitude.astype(float), df.latitude.astype(float)), crs=4326)
            gdf = gdf[gdf.within(ctx)]
            out = RAW / f"{ds}_{slug}.geojson"; gdf.to_file(out, driver="GeoJSON"); rec["saved"] = str(out.relative_to(ROOT))
        if g:
            fn = "within_polygon" if gt != "location" else "within_polygon"
            where_core = f"{fn}({g}, '{wkt(core)}')" if gt in ("point", "location") else f"intersects({g}, '{wkt(core)}')"
            where_ctx = f"{fn}({g}, '{wkt(ctx)}')" if gt in ("point", "location") else f"intersects({g}, '{wkt(ctx)}')"
            rec["rows_core"] = int(soql(ds, {"$select": "count(*) as n", "$where": where_core})[0]["n"])
            rows = soql(ds, {"$where": where_ctx, "$limit": 200000})
            rec["rows_context"] = len(rows)
            if rows:
                gdf = gpd.GeoDataFrame.from_features(
                    [{"type": "Feature", "geometry": r.pop(g), "properties": {("geometry_wkt" if k == "geometry" else k): (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in r.items()}}
                     for r in rows if r.get(g)], crs=4326)
                out = RAW / f"{ds}_{slug}.geojson"
                gdf.to_file(out, driver="GeoJSON")
                rec["saved"] = str(out.relative_to(ROOT))
        rec["status"] = "ok"
    except Exception as e:  # keep auditing other layers
        rec["status"] = f"error: {e.__class__.__name__}: {str(e)[:200]}"
    print(json.dumps({k: v for k, v in rec.items() if k != "columns"}))
    results.append(rec)

(RAW / "_audit_nyc_opendata.json").write_text(json.dumps(results, indent=2))
