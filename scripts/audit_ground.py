"""Audit ground-truth sources for Area A: soils (SSURGO), 311 tree complaints,
Heat Vulnerability Index, NYCCAS, and nearby weather stations. Saves small subsets."""
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
core = gpd.read_file(ROOT / "data/aoi/area_a_core.geojson").geometry.iloc[0]
ctx = gpd.read_file(ROOT / "data/aoi/area_a_context.geojson").geometry.iloc[0]
out = {}

# --- SSURGO via USDA Soil Data Access (public) ---
try:
    q = f"""SELECT mu.mukey, mu.musym, mu.muname, c.compname, c.comppct_r, c.drainagecl, c.hydgrp
            FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('{core.wkt}') k
            JOIN mapunit mu ON mu.mukey = k.mukey
            LEFT JOIN component c ON c.mukey = mu.mukey AND c.majcompflag = 'Yes'"""
    r = requests.post("https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest",
                      data={"query": q, "format": "JSON+COLUMNNAME"}, timeout=120)
    rows = r.json().get("Table", [])
    df = pd.DataFrame(rows[1:], columns=rows[0]) if rows else pd.DataFrame()
    df.to_csv(RAW / "ssurgo_area_a_core.csv", index=False)
    out["ssurgo"] = df.to_dict("records")
except Exception as e:
    out["ssurgo"] = f"error {e}"

# --- 311: tree-related complaints in core, 2020-present ---
try:
    poly = core.wkt.replace("POLYGON ((", "MULTIPOLYGON (((").replace("))", ")))")
    base = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
    rows = requests.get(base, params={
        "$select": "complaint_type, descriptor, count(*) as n",
        "$where": f"within_polygon(location, '{poly}') AND (complaint_type like '%Tree%' OR descriptor like '%Root%' OR complaint_type like '%Sidewalk%')",
        "$group": "complaint_type, descriptor", "$order": "n DESC", "$limit": 50}, timeout=300).json()
    out["311_tree_sidewalk_core_2020plus"] = rows
except Exception as e:
    out["311_tree_sidewalk_core_2020plus"] = f"error {e}"

# --- Heat Vulnerability Index (by NTA / ZCTA) ---
try:
    hvi = requests.get("https://data.cityofnewyork.us/resource/4mhf-duep.json", params={"$limit": 5000}, timeout=120).json()
    pd.DataFrame(hvi).to_csv(RAW / "hvi_rankings.csv", index=False)
    out["hvi"] = {"rows": len(hvi), "columns": list(hvi[0].keys()) if hvi else [],
                  "bronx_10454_10451": [h for h in hvi if str(h.get("zcta20", h.get("zip", ""))) in ("10454", "10451")]}
except Exception as e:
    out["hvi"] = f"error {e}"

# --- NYCCAS / Air quality indicators for Mott Haven (UHF / CD) ---
try:
    aq = requests.get("https://data.cityofnewyork.us/resource/c3uy-2p5r.json", params={
        "$where": "geo_place_name like '%Mott Haven%' OR geo_place_name like '%Hunts Point%'", "$limit": 5000}, timeout=120).json()
    pd.DataFrame(aq).to_csv(RAW / "nyccas_air_quality_mott_haven.csv", index=False)
    out["nyccas_air_quality"] = {"rows": len(aq), "indicators": sorted({a.get("name") for a in aq}),
                                 "periods": sorted({a.get("time_period") for a in aq})[-6:]}
except Exception as e:
    out["nyccas_air_quality"] = f"error {e}"

# --- Weather stations near Area A (NWS observation stations + NYS Mesonet page) ---
try:
    c = core.centroid
    st = requests.get(f"https://api.weather.gov/points/{c.y:.4f},{c.x:.4f}/stations",
                      headers={"User-Agent": "urban-tree-geoai-research"}, timeout=60).json()
    out["nws_stations_nearest"] = [(f["properties"]["stationIdentifier"], f["properties"]["name"]) for f in st.get("features", [])[:6]]
except Exception as e:
    out["nws_stations_nearest"] = f"error {e}"

(RAW / "_audit_ground.json").write_text(json.dumps(out, indent=2, default=str))
print(json.dumps(out, indent=2, default=str)[:6000])
