"""Site characterisation engine (module 1): one row per NYC Forestry planting space in Area A context.

Joins tree records, maintenance history, 2015 census, street geometry, land use, LiDAR shade/canopy,
satellite heat/greenness, soil and heat vulnerability into a feature table.
Output: data/processed/sites_area_a.gpkg (layer 'sites') and .csv. See docs/Site_Features.md.
"""
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.features import rasterize
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"; NOD = RAW / "nyc_opendata"
PROC = ROOT / "data/processed"; PROC.mkdir(exist_ok=True)
UTM = 32618


def rd(name):
    return gpd.read_file(next(NOD.glob(f"*{name}*.geojson"))).to_crs(UTM)


core = gpd.read_file(ROOT / "data/aoi/area_a_core.geojson").to_crs(UTM).geometry.iloc[0]
ctx = gpd.read_file(ROOT / "data/aoi/area_a_context.geojson").to_crs(UTM).geometry.iloc[0]

# ---------------- base: planting spaces ----------------
ps = rd("planting_spaces")
ps = ps[ps.within(ctx)].copy()
keep = ["globalid", "psstatus", "pssite", "plantingspaceonstreet", "jurisdiction", "overheadutilities", "treeguard",
        "width", "length", "zipcode", "bbl", "nta", "streetname", "buildingnumber", "geometry"]
ps = ps[[c for c in keep if c in ps.columns]].rename(columns={"globalid": "ps_id"})
ps["in_core"] = ps.within(core)
for c in ("width", "length", "overheadutilities"):
    ps[c] = pd.to_numeric(ps[c], errors="coerce")

# ---------------- current tree on the space ----------------
tp = rd("tree_points")
tp["updateddate"] = pd.to_datetime(tp.updateddate, errors="coerce")
tp = tp.sort_values("updateddate").drop_duplicates("plantingspaceglobalid", keep="last")
tp = tp[["plantingspaceglobalid", "globalid", "genusspecies", "dbh", "tpcondition", "tpstructure", "createddate"]]
tp.columns = ["ps_id", "tree_id", "tree_species", "tree_dbh_in", "tree_condition", "tree_structure", "tree_created"]
ps = ps.merge(tp, on="ps_id", how="left")
ps["tree_dbh_in"] = pd.to_numeric(ps.tree_dbh_in, errors="coerce")


def site_class(r):
    if r.psstatus == "Empty" or pd.isna(r.tree_structure):
        return "empty"
    if r.tree_structure in ("Retired",) or str(r.tree_structure).startswith("Stump"):
        return "removed_or_stump"
    if r.tree_condition in ("Dead", "Critical"):
        return "dead_tree"
    return "living_tree"


ps["site_class"] = ps.apply(site_class, axis=1)

# ---------------- maintenance history ----------------
wo = rd("work_orders")
wo["wotype"] = wo.wotype.fillna("")
# plantingspaceglobalid is empty in work orders here -> assign each WO to the nearest planting space within 3 m
wo = gpd.sjoin_nearest(wo, ps[["ps_id", "geometry"]], max_distance=3, how="inner").drop(columns="index_right")
wo["plantingspaceglobalid"] = wo.ps_id
wo["sidewalkdamage"] = pd.to_numeric(wo.sidewalkdamage, errors="coerce")
wo["wire"] = wo.wowireconflict.fillna("").str.contains("Pending|Open|Resolved|Clear", case=False)
g = wo.groupby("plantingspaceglobalid")
hist = pd.DataFrame({
    "wo_n": g.size(),
    "wo_planting_n": g.wotype.apply(lambda s: s.str.contains("Plant", case=False).sum()),
    "wo_removal_n": g.wotype.apply(lambda s: s.str.contains("Removal", case=False).sum()),
    "wo_sidewalk_damage": g.sidewalkdamage.max() == 1,
    "wo_wire_conflict": g.wire.any(),
    "wo_recommended_species": g.recommendedspecies.apply(lambda s: s.dropna().iloc[-1] if s.notna().any() else None),
})
ps = ps.merge(hist, left_on="ps_id", right_index=True, how="left")
ins = rd("inspections")
ins["swratingtotal"] = pd.to_numeric(ins.swratingtotal, errors="coerce")
gi = ins.groupby("plantingspaceglobalid").agg(insp_n=("objectid", "size"), insp_sidewalk_rating_max=("swratingtotal", "max"))
ps = ps.merge(gi, left_on="ps_id", right_index=True, how="left")
for c in ("wo_n", "wo_planting_n", "wo_removal_n", "insp_n"):
    ps[c] = ps[c].fillna(0).astype(int)
ps["planting_attempts_failed"] = np.maximum(ps.wo_planting_n - (ps.site_class == "living_tree").astype(int), 0)

# 311/forestry service requests within 15 m
sr = rd("service_requests")
ps["sr_15m_n"] = ps.geometry.buffer(15).apply(lambda b: 0).astype(int)
j = gpd.sjoin(gpd.GeoDataFrame(ps[["ps_id"]], geometry=ps.buffer(15), crs=UTM), sr[["geometry"]], predicate="contains")
ps["sr_15m_n"] = ps.ps_id.map(j.groupby("ps_id").size()).fillna(0).astype(int)

# ---------------- 2015 census nearest (<= 3 m) ----------------
c15 = rd("census2015")[["tree_id", "status", "health", "sidewalk", "root_stone", "root_grate", "root_other",
                         "spc_latin", "tree_dbh", "curb_loc", "geometry"]]
c15.columns = ["c15_" + c if c != "geometry" else c for c in c15.columns]
ps = gpd.sjoin_nearest(ps, c15, how="left", max_distance=3, distance_col="c15_dist_m").drop(columns="index_right")
ps = ps.drop_duplicates("ps_id")
ps["c15_root_problem"] = ps[["c15_root_stone", "c15_root_grate", "c15_root_other"]].eq("Yes").any(axis=1).where(ps.c15_tree_id.notna())

# ---------------- street geometry ----------------
def nearest_dist(name, col):
    other = rd(name)[["geometry"]]
    d = gpd.sjoin_nearest(ps[["ps_id", "geometry"]], other, distance_col=col, max_distance=300)
    return d.groupby("ps_id")[col].min()


for name, col in [("building_footprints", "dist_building_m"), ("curbs", "dist_curb_m"), ("hydrants", "dist_hydrant_m"),
                  ("bus_stop", "dist_bus_shelter_m"), ("green_infra", "dist_green_infra_m")]:
    ps[col] = ps.ps_id.map(nearest_dist(name, col))

# local sidewalk width: 2 x max distance-to-edge of sidewalk polygon within 6 m of the site
sw = rd("sidewalk")
x0, y0, x1, y1 = ctx.bounds
res = 0.5
Wd, Hd = int((x1 - x0) / res) + 1, int((y1 - y0) / res) + 1
Tsw = rasterio.transform.from_origin(x0, y1, res, res)
swr = rasterize(((g, 1) for g in sw.geometry), out_shape=(Hd, Wd), transform=Tsw, dtype="uint8")
edt = ndimage.distance_transform_edt(swr) * res
mx = ndimage.maximum_filter(edt, size=int(12 / res))
rc = [rasterio.transform.rowcol(Tsw, p.x, p.y) for p in ps.geometry]
ps["sidewalk_width_m"] = [2 * mx[r, c] if 0 <= r < Hd and 0 <= c < Wd else np.nan for r, c in rc]

# ---------------- raster sampling ----------------
def sample(path, name, buffer_m=None, stat=np.nanmean):
    with rasterio.open(path) as s:
        pts = ps.geometry.to_crs(s.crs) if s.crs.to_epsg() != UTM else ps.geometry
        if buffer_m is None:
            vals = [v[0] for v in s.sample([(p.x, p.y) for p in pts])]
            ps[name] = np.where(np.asarray(vals, "float64") == (s.nodata if s.nodata is not None else -9e9), np.nan, vals)
        else:
            a = s.read(1).astype("float32"); T = s.transform; out = []
            r = int(np.ceil(buffer_m / abs(T.a)))
            yy, xx = np.mgrid[-r:r + 1, -r:r + 1]; disk = (xx ** 2 + yy ** 2) * abs(T.a) ** 2 <= buffer_m ** 2
            for p in pts:
                row, col = rasterio.transform.rowcol(T, p.x, p.y)
                win = a[max(row - r, 0):row + r + 1, max(col - r, 0):col + r + 1]
                dk = disk[r - (row - max(row - r, 0)):r + (min(row + r + 1, a.shape[0]) - row), r - (col - max(col - r, 0)):r + (min(col + r + 1, a.shape[1]) - col)]
                out.append(stat(win[dk]) if win.size and dk.shape == win.shape else np.nan)
            ps[name] = out


SH = PROC / "shade"; CP = PROC / "composites"; LD = RAW / "lidar"
sample(SH / "sun_hours_bldg.tif", "sun_hours_bldg_jul15")
sample(SH / "shade_bldg_afternoon_hours.tif", "bldg_shade_hours_13_17")
sample(SH / "shade_total_hours.tif", "shade_total_hours_jul15", buffer_m=3)
sample(LD / "canopy_mask_1m.tif", "canopy_frac_10m", buffer_m=10)
sample(LD / "canopy_mask_1m.tif", "canopy_frac_30m", buffer_m=30)
sample(LD / "bldg_1m.tif", "building_frac_30m", buffer_m=30)
sample(LD / "ndvi_naip_1m.tif", "veg_frac_30m", buffer_m=30, stat=lambda v: np.nanmean(v > 0.2))
ps["impervious_frac_30m_proxy"] = 1 - ps.veg_frac_30m
sample(LD / "dsm_1m.tif", "dsm_max_30m", buffer_m=30, stat=np.nanmax)
sample(LD / "dtm_1m.tif", "ground_elev_m")
ps["max_obstacle_height_30m"] = ps.dsm_max_30m - ps.ground_elev_m
ps["canyon_hw_proxy"] = ps.max_obstacle_height_30m / ps.dist_building_m.clip(lower=1).mul(2)
sample(CP / "landsat_lst_summer_median.tif", "lst_landsat_median_c")
sample(CP / "landsat_lst_summer_p90.tif", "lst_landsat_p90_c")
sample(CP / "ecostress_lst_afternoon_median.tif", "lst_ecostress_pm_median_c")
sample(CP / "s2_ndvi_summer_median.tif", "ndvi_s2_median")

# ---------------- land use (PLUTO via BBL) ----------------
pl = gpd.read_file(next(NOD.glob("*pluto*.geojson")))
LU = {"01": "1-2 family res", "02": "multi-family walk-up", "03": "multi-family elevator", "04": "mixed res/commercial",
      "05": "commercial/office", "06": "industrial/manufacturing", "07": "transport/utility", "08": "public facility/institution",
      "09": "open space/recreation", "10": "parking", "11": "vacant land"}
pl["bbl"] = pd.to_numeric(pl.bbl, errors="coerce").astype("Int64").astype(str)
pl["landuse_name"] = pl.landuse.astype(str).str.zfill(2).map(LU)
plk = pl[["bbl", "landuse", "landuse_name", "bldgclass", "zonedist1", "numfloors", "yearbuilt", "unitsres"]].drop_duplicates("bbl")
ps["bbl"] = pd.to_numeric(ps.bbl, errors="coerce").astype("Int64").astype(str)
ps = ps.merge(plk.add_prefix("lot_").rename(columns={"lot_bbl": "bbl"}), on="bbl", how="left")
# fallback for sites without a BBL: nearest PLUTO lot centroid within 40 m
miss = ps.lot_landuse.isna()
plg = gpd.GeoDataFrame(plk.add_prefix("lot_"), crs=4326, geometry=gpd.points_from_xy(
    pl.loc[plk.index, "longitude"].astype(float), pl.loc[plk.index, "latitude"].astype(float))).to_crs(UTM)
nn = gpd.sjoin_nearest(ps.loc[miss, ["ps_id", "geometry"]], plg, max_distance=40, how="left").drop_duplicates("ps_id").set_index("ps_id")
for c in [c for c in plg.columns if c.startswith("lot_") and c != "lot_bbl"]:
    ps.loc[miss, c] = ps.loc[miss, "ps_id"].map(nn[c])
ps["lot_join"] = np.where(miss, np.where(ps.lot_landuse.notna(), "nearest_40m", "none"), "bbl")

# ---------------- heat vulnerability ----------------
hvi = pd.read_csv(RAW / "hvi_rankings.csv", dtype=str)
ps["hvi"] = pd.to_numeric(ps.zipcode.astype(str).str[:5].map(dict(zip(hvi.zcta20, hvi.hvi))), errors="coerce")

# ---------------- soil (SSURGO map units) ----------------
try:
    wkt = gpd.GeoSeries([ctx], crs=UTM).to_crs(4326).iloc[0].envelope.wkt
    q = f"""SELECT mp.mukey, mu.musym, mu.muname, mp.mupolygongeo.STAsText() AS wkt FROM mupolygon mp
            JOIN mapunit mu ON mu.mukey = mp.mukey
            WHERE mp.mupolygongeo.STIntersects(geometry::STGeomFromText('{wkt}', 4326)) = 1"""
    r = requests.post("https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest", data={"query": q, "format": "JSON+COLUMNNAME"}, timeout=180).json()["Table"]
    soil = gpd.GeoDataFrame(pd.DataFrame(r[1:], columns=r[0]), geometry=gpd.GeoSeries.from_wkt(pd.DataFrame(r[1:], columns=r[0]).wkt), crs=4326).to_crs(UTM)
    soil.drop(columns="wkt").to_file(RAW / "ssurgo_mapunits_context.gpkg")
    ps = gpd.sjoin(ps, soil[["musym", "muname", "geometry"]], how="left", predicate="within").drop(columns="index_right").drop_duplicates("ps_id")
    ps["soil_substratum"] = ps.muname.str.extract(r"(tidal marsh|outwash|reclaimed|till|Greenbelt|Flatbush)", expand=False)
    ps = ps.rename(columns={"musym": "soil_musym", "muname": "soil_muname"})
except Exception as e:
    print("soil join skipped:", e)

ps = gpd.GeoDataFrame(ps, geometry="geometry", crs=UTM)
ps.to_file(PROC / "sites_area_a.gpkg", layer="sites", driver="GPKG")
ps.drop(columns="geometry").assign(x=ps.geometry.x, y=ps.geometry.y).to_csv(PROC / "sites_area_a.csv", index=False)

num = ps.select_dtypes("number")
summary = {"n_sites": len(ps), "n_core": int(ps.in_core.sum()), "site_class": ps.site_class.value_counts().to_dict(),
           "site_class_core": ps[ps.in_core].site_class.value_counts().to_dict(),
           "missing_frac": {c: round(float(ps[c].isna().mean()), 3) for c in ps.columns if c != "geometry" and ps[c].isna().mean() > 0.2},
           "medians": {c: round(float(num[c].median()), 2) for c in num.columns if num[c].notna().any()}}
(PROC / "sites_summary.json").write_text(json.dumps(summary, indent=2, default=str))
print(json.dumps(summary, indent=2, default=str))
