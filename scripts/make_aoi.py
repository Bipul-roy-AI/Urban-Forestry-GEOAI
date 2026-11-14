"""Build pilot-area boundaries (Area A core + context buffer) as GeoJSON.

Corridor: Third Avenue, Bronx, ~E 135th St to ~E 139th St, incl. Graham Triangle.
Endpoints geocoded with NYC Planning GeoSearch on 2026-11-14:
  2500 3 Ave  -> (-73.928088, 40.810138)  ~E 135th St
  2600 3 Ave  -> (-73.925070, 40.811890)  ~E 138th/139th St
  Graham Triangle -> (-73.92763, 40.81054)
"""
import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString

OUT = Path(__file__).resolve().parents[1] / "data" / "aoi"
OUT.mkdir(parents=True, exist_ok=True)

# Extend slightly past the geocoded ends so the corridor covers E 135th-E 139th.
corridor = LineString([(-73.9290, 40.8096), (-73.9238, 40.8128)])
line = gpd.GeoSeries([corridor], crs=4326).to_crs(2263)  # NY State Plane Long Island, US ft

layers = {
    "area_a_core": line.buffer(250 * 3.28084),      # 250 m each side
    "area_a_context": line.buffer(1000 * 3.28084),  # 1 km for rasters / shading context
}
summary = {}
for name, geom in layers.items():
    g = gpd.GeoDataFrame({"name": [name]}, geometry=geom, crs=2263)
    summary[name] = {
        "area_km2": round(float(g.to_crs(32618).area.iloc[0]) / 1e6, 3),
        "bbox_wgs84": [round(v, 5) for v in g.to_crs(4326).total_bounds],
    }
    g.to_crs(4326).to_file(OUT / f"{name}.geojson", driver="GeoJSON")

(OUT / "aoi_summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
