"""Module 3: young-tree failure model (Bronx, Area B) and species x site scoring for Area A.

LABEL (young trees, last recorded DBH <= 4 in; NYC Forestry Tree Points):
  failed  = condition Dead/Critical, OR structure Stump/Stump - Uprooted/Shaft,
            OR Retired with condition Dead/Critical/Poor, OR standing in Poor condition
  healthy = standing (Full) in Good/Excellent condition
  dropped = Fair / Unknown, and Retired records with Good/Excellent/Fair/Unknown (likely administrative)
This is a cross-sectional establishment-failure proxy, not measured survival (see docs/Species_KB.md).

FEATURES: species & genus (categorical), species-KB traits, planting-space attributes, PLUTO land use,
distance to building/curb, nearest building height, Landsat summer LST, Sentinel-2 NDVI (point & 100 m),
heat vulnerability (ZIP), and exposure = years since the tree record was created (fixed at 5 for scoring).

VALIDATION: 5-fold spatial GroupKFold on 1 km grid cells. Nested models (exposure only -> + species -> full)
and WITHIN-COHORT AUC (record-year strata): failure rate falls from 64% (2015 records) to 2% (2025), so a
raw species rate is confounded by planting cohort. Probabilities are isotonic-calibrated on out-of-fold preds.
"""
import json
from pathlib import Path

import geopandas as gpd
import lightgbm as lgb
import numpy as np
import pandas as pd
import rasterio
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

ROOT = Path(__file__).resolve().parents[1]
B = ROOT / "data/raw/bronx"; PB = ROOT / "data/processed/bronx"
OUTM = ROOT / "models"; OUTM.mkdir(exist_ok=True)
OUTP = ROOT / "outputs"; OUTP.mkdir(exist_ok=True)
UTM = 32618
NOW = pd.Timestamp("2026-11-15")

# ---------------- load ----------------
tp = gpd.read_parquet(B / "tree_points.parquet").to_crs(UTM)
ps = gpd.read_parquet(B / "planting_spaces.parquet").to_crs(UTM)
for c in ("dbh",):
    tp[c] = pd.to_numeric(tp[c], errors="coerce")
tp["createddate"] = pd.to_datetime(tp.createddate, errors="coerce")

# ---------------- label ----------------
cond, struc = tp.tpcondition.fillna("Unknown"), tp.tpstructure.fillna("Unknown")
failed = (cond.isin(["Dead", "Critical"]) | struc.isin(["Stump", "Stump - Uprooted", "Shaft"])
          | ((struc == "Retired") & cond.isin(["Dead", "Critical", "Poor"])) | ((struc == "Full") & (cond == "Poor")))
healthy = (struc == "Full") & cond.isin(["Good", "Excellent"])
tp["y"] = np.where(failed, 1, np.where(healthy, 0, np.nan))
d = tp[(tp.dbh <= 4) & tp.y.notna() & tp.genusspecies.notna() & ~tp.genusspecies.str.startswith("Unknown")].copy()
d["sci"] = d.genusspecies.str.split(" - ").str[0].str.strip()
d["genus"] = d.sci.str.split().str[0]
d["exposure_yr"] = ((NOW - d.createddate).dt.days / 365.25).clip(0, 30)

# ---------------- site features (shared with scoring) ----------------
pl = pd.read_parquet(B / "pluto.parquet")
pl["bbl"] = pd.to_numeric(pl.bbl, errors="coerce").astype("Int64").astype(str)
bf = gpd.read_parquet(B / "building_footprints.parquet").to_crs(UTM)
bf["height_roof"] = pd.to_numeric(bf.height_roof, errors="coerce") * 0.3048
cu = gpd.read_parquet(B / "curbs.parquet").to_crs(UTM)
hvi = pd.read_csv(ROOT / "data/raw/hvi_rankings.csv", dtype=str)


def raster_sample(pts, path, buf=None):
    with rasterio.open(path) as s:
        if buf is None:
            return np.array([v[0] for v in s.sample([(p.x, p.y) for p in pts])], dtype="float64")
        a = s.read(1).astype("float32"); T = s.transform; r = int(buf / abs(T.a)); out = []
        for p in pts:
            row, col = rasterio.transform.rowcol(T, p.x, p.y)
            w = a[max(row - r, 0):row + r + 1, max(col - r, 0):col + r + 1]
            out.append(np.nanmean(w) if w.size else np.nan)
        return np.array(out)


def site_features(g):
    """g: GeoDataFrame of planting spaces (UTM) with ps columns. Returns feature frame indexed like g."""
    f = pd.DataFrame(index=g.index)
    for c in ("jurisdiction", "pssite", "plantingspaceonstreet", "treeguard"):
        f["ps_" + c] = g[c].astype("string").fillna("NA") if c in g else "NA"
    f["ps_overhead"] = pd.to_numeric(g.get("overheadutilities"), errors="coerce")
    bbl = pd.to_numeric(g.bbl, errors="coerce").astype("Int64").astype(str)
    m = pd.DataFrame({"bbl": bbl}).merge(pl.drop_duplicates("bbl"), on="bbl", how="left").set_index(g.index)
    f["lu_landuse"] = m.landuse.astype("string").fillna("NA")
    f["lu_zone"] = m.zonedist1.astype("string").str[:1].fillna("NA")
    for c in ("numfloors", "unitsres", "yearbuilt", "lotarea"):
        f["lu_" + c] = pd.to_numeric(m[c], errors="coerce")
    nb = gpd.sjoin_nearest(g[["geometry"]], bf[["height_roof", "geometry"]], distance_col="dist_building_m", max_distance=300)
    nb = nb[~nb.index.duplicated()]
    f["dist_building_m"] = nb.dist_building_m; f["near_bldg_height_m"] = nb.height_roof
    nc = gpd.sjoin_nearest(g[["geometry"]], cu[["geometry"]], distance_col="dist_curb_m", max_distance=100)
    f["dist_curb_m"] = nc[~nc.index.duplicated()].dist_curb_m
    f["lst_summer_c"] = raster_sample(g.geometry, PB / "landsat_lst_summer_median.tif")
    f["ndvi_pt"] = raster_sample(g.geometry, PB / "s2_ndvi_summer_median.tif")
    f["ndvi_100m"] = raster_sample(g.geometry, PB / "s2_ndvi_summer_median.tif", buf=100)
    f["hvi"] = pd.to_numeric(g.zipcode.astype(str).str[:5].map(dict(zip(hvi.zcta20, hvi.hvi))), errors="coerce")
    return f


ps = ps.drop_duplicates("globalid").set_index("globalid", drop=False)
SF = site_features(ps)

# ---------------- species traits from the KB ----------------
kb = pd.read_csv(ROOT / "data/species/species_kb.csv")
kb["key"] = kb.taxon.str.replace(r"'.*?'", "", regex=True).str.replace(r" spp?\.", "", regex=True).str.split().str[:2].str.join(" ").str.strip()
ORD = {"none": 0, "none_reported": 0, "low": 1, "low-moderate": 1.5, "moderate": 2, "medium": 2, "high": 3}
TR = pd.DataFrame({"key": kb.key})
TR["t_size"] = kb.size_class.map({"small": 1, "intermediate": 2, "medium": 3, "large": 4})
for c in ("tol_salt", "tol_drought", "tol_wet", "tol_pollution", "tol_shade", "loc_small_pit_lt3ft", "loc_narrow_space"):
    TR["t_" + c] = pd.to_numeric(kb[c].map({"True": 1, "False": 0, True: 1, False: 0}).fillna(kb[c]), errors="coerce")
TR["t_native_ny"] = kb.native_NY_region.map({"yes": 1, "no": 0, "cultivar-of-native": 1, "hybrid-nonnative": 0})
TR["t_root_risk"] = kb.root_sidewalk_damage_risk.map(ORD)
TR["t_climate"] = kb.climate_suitability_2070_2099.map({"likely suitable": 2, "uncertain": 1, "likely reduced": 0})
TR = TR.drop_duplicates("key")
TRAIT_COLS = [c for c in TR.columns if c != "key"]


def species_frame(sci):
    s = pd.Series(sci).str.replace(r"'.*?'", "", regex=True).str.split().str[:2].str.join(" ").str.strip()
    out = pd.DataFrame({"key": s.values})
    out = out.merge(TR, on="key", how="left")
    return out[TRAIT_COLS].reset_index(drop=True)


# ---------------- training table ----------------
d = d[d.plantingspaceglobalid.isin(SF.index)].copy()
X = SF.loc[d.plantingspaceglobalid].reset_index(drop=True)
X = pd.concat([X, species_frame(d.sci.values)], axis=1)
top = d.sci.value_counts(); keep_sp = set(top[top >= 30].index)
X["sp"] = pd.Series(np.where(d.sci.isin(keep_sp), d.sci, "other")).values
X["genus"] = d.genus.values
X["exposure_yr"] = d.exposure_yr.values
y = d.y.astype(int).values
CAT = [c for c in X.columns if not pd.api.types.is_numeric_dtype(X[c])]
for c in CAT:
    X[c] = X[c].astype("category")
xy = np.c_[d.geometry.x.values, d.geometry.y.values]
groups = np.floor(xy[:, 0] / 1000).astype(np.int64) * 100000 + np.floor(xy[:, 1] / 1000).astype(np.int64)
print(f"training rows {len(X)} | failure rate {y.mean():.3f} | species kept {len(keep_sp)} | 1-km blocks {len(set(groups))}")

params = dict(objective="binary", learning_rate=0.05, num_leaves=31, min_data_in_leaf=50, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0, verbose=-1, seed=42)
cohort = d.createddate.dt.year.values
SETS = {"exposure_only": ["exposure_yr"],
        "exposure+species": ["exposure_yr", "sp", "genus"] + TRAIT_COLS,
        "full": list(X.columns)}
oof = {k: np.zeros(len(y)) for k in SETS}
for tr, te in GroupKFold(5).split(X, y, groups):
    for k, cols in SETS.items():
        m = lgb.train(params, lgb.Dataset(X.iloc[tr][cols], y[tr], categorical_feature=[c for c in CAT if c in cols]), 400)
        oof[k][te] = m.predict(X.iloc[te][cols])


def within_cohort_auc(p):
    """Mean AUC within record-year cohorts (weighted by n): ranking at equal exposure."""
    num = den = 0
    for yr in np.unique(cohort):
        mk = cohort == yr
        if y[mk].min() != y[mk].max() and mk.sum() >= 100:
            num += roc_auc_score(y[mk], p[mk]) * mk.sum(); den += mk.sum()
    return round(num / den, 4)


def calib(p, yy, bins=10):
    q = pd.qcut(p, bins, duplicates="drop")
    return pd.DataFrame({"pred": p, "obs": yy}).groupby(q, observed=True).mean().round(3).values.tolist()


from sklearn.isotonic import IsotonicRegression
iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(oof["full"], y)
p_cal = iso.predict(oof["full"])
metrics = {"n": int(len(y)), "failure_rate": round(float(y.mean()), 4), "spatial_blocks": int(len(set(groups))),
           "auc": {k: round(roc_auc_score(y, v), 4) for k, v in oof.items()},
           "within_cohort_auc": {k: within_cohort_auc(v) for k, v in oof.items()},
           "brier": {k: round(brier_score_loss(y, v), 4) for k, v in oof.items()},
           "brier_full_isotonic": round(brier_score_loss(y, p_cal), 4),
           "calibration_raw_deciles_[pred,obs]": calib(oof["full"], y),
           "calibration_isotonic_deciles_[pred,obs]": calib(p_cal + 1e-9 * np.arange(len(p_cal)), y)}
final = lgb.train(params, lgb.Dataset(X, y, categorical_feature=CAT), 400)
final.save_model(str(OUTM / "survival_lgbm.txt"))
imp = pd.Series(final.feature_importance("gain"), index=X.columns).sort_values(ascending=False)
metrics["top_features_gain_pct"] = (100 * imp / imp.sum()).round(1).head(15).to_dict()
(OUTP / "survival_cv_metrics.json").write_text(json.dumps(metrics, indent=2))
print(json.dumps(metrics, indent=1))
import joblib
joblib.dump(iso, OUTM / "survival_isotonic.joblib")

# ---------------- score Area A candidates x approved species ----------------
sites = gpd.read_file(ROOT / "data/processed/sites_area_a.gpkg")
cand = sites[(sites.in_core.astype(str) == "True") & (sites.site_class != "living_tree")]
cand = cand[cand.ps_id.isin(SF.index)]
approved = kb[kb.nyc_approved.astype(str) == "True"].taxon.tolist()
rows = []
for t in approved:
    Xs = SF.loc[cand.ps_id].reset_index(drop=True)
    Xs = pd.concat([Xs, species_frame([t] * len(Xs))], axis=1)
    stripped = " ".join(t.replace("'", " '").split(" '")[0].replace(" sp.", "").replace(" spp.", "").split())
    sci_match = next((c for c in (t, stripped) if c in keep_sp), None)  # exact taxon, else cultivar's parent / genus label
    Xs["sp"] = sci_match or "other"; Xs["genus"] = t.split()[0]; Xs["exposure_yr"] = 5.0
    for c in CAT:
        Xs[c] = pd.Categorical(Xs[c].astype(str), categories=X[c].cat.categories)
    p = final.predict(Xs[X.columns])
    rows.append(pd.DataFrame({"ps_id": cand.ps_id.values, "taxon": t, "species_in_training": sci_match is not None, "p_fail_5yr_raw": p.round(4),
                             "p_fail_5yr": iso.predict(p).round(4)}))
sc = pd.concat(rows)
sc.to_csv(ROOT / "data/processed/area_a_species_failure_risk.csv", index=False)
summ = sc.groupby("taxon").agg(median_p_fail=("p_fail_5yr", "median"), in_training=("species_in_training", "first")).sort_values("median_p_fail")
print(f"\nscored {cand.ps_id.nunique()} candidate sites x {len(approved)} approved species")
# independent check: species ranking vs 2015 census young-tree % poor (Bronx)
kbq = kb.set_index("taxon")
summ["census_young_pct_poor"] = pd.to_numeric(kbq.reindex(summ.index).bronx_c15y_pct_poor, errors="coerce")
from scipy.stats import spearmanr
ok = summ.census_young_pct_poor.notna()
rho = spearmanr(summ.median_p_fail[ok], summ.census_young_pct_poor[ok])
metrics["spearman_vs_census_young_poor"] = {"rho": round(float(rho.statistic), 3), "p": round(float(rho.pvalue), 4), "n_species": int(ok.sum())}
(OUTP / "survival_cv_metrics.json").write_text(json.dumps(metrics, indent=2))
summ.to_csv(OUTP / "area_a_species_failure_summary.csv")
print(summ.round(3).to_string())
print("Spearman vs 2015 census young-tree %poor:", metrics["spearman_vs_census_young_poor"])

# ---------------- direction of site effects (SHAP-style contributions, final model) ----------------
contrib = final.predict(X, pred_contrib=True)[:, :-1]
eff = {}
for f in ["ndvi_pt", "ndvi_100m", "dist_curb_m", "lst_summer_c", "near_bldg_height_m", "dist_building_m", "lu_lotarea", "hvi"]:
    j = list(X.columns).index(f); v = X[f].astype(float)
    q = pd.qcut(v.rank(method="first"), 5, labels=False)
    eff[f] = {"quintile_means": [round(float(v[q == i].mean()), 2) for i in range(5)],
              "mean_logodds_contrib": [round(float(contrib[q.values == i, j].mean()), 3) for i in range(5)]}
metrics["site_effect_direction"] = eff
(OUTP / "survival_cv_metrics.json").write_text(json.dumps(metrics, indent=2))
print(json.dumps(eff, indent=1))

# ---------------- site-level risk for Area A candidates (robust output) ----------------
trained = sc[sc.species_in_training]
site = trained.groupby("ps_id").p_fail_5yr.agg(site_risk_median="median", site_risk_min="min", site_risk_max="max").reset_index()
site.to_csv(ROOT / "data/processed/area_a_site_failure_risk.csv", index=False)
print(site.describe().round(3).to_string())
