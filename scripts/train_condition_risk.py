"""Module 3: recorded-condition risk model for small-diameter street trees (Bronx, Area B), and
species x site scoring for Area A candidates.

WHAT THIS IS (audit fix, Nov 2026): a model of the CURRENT RECORDED CONDITION of small-diameter trees in the
NYC Forestry inventory. It is NOT a survival model and NOT a "5-year failure" prediction:
  - `createddate` is a record-creation date, not a planting date;
  - selecting trees by present DBH (<= 4 in) excludes trees that grew past the threshold, so older record
    cohorts are enriched for trees that failed or stagnated (selection bias). A DBH-threshold sensitivity
    analysis (4 / 6 / 8 in) is reported to show how much this matters.
LABEL: poor = condition Dead/Critical, OR structure Stump/Stump - Uprooted/Shaft, OR Retired with condition
       Dead/Critical/Poor, OR standing in Poor condition; good = standing in Good/Excellent; others dropped.
FEATURES: species & genus, species-KB traits, planting-space attributes, PLUTO land use, distance to
  building/curb, nearest building height, Landsat summer LST, Sentinel-2 NDVI (offset-corrected, deduplicated),
  heat vulnerability, and record age in years (set to 5 when scoring, as a reference value only).
VALIDATION: 5-fold spatial GroupKFold on 1 km blocks; nested models; within-record-year AUC.
  Calibration is TESTED, not used: for each outer fold an isotonic calibrator is fitted on inner out-of-fold
  predictions from the training blocks and applied to the untouched outer test blocks. It made the Brier score
  worse, so outputs carry the raw score (`p_poor`), to be read as a relative ranking only.
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
DBH_MAX = 4
d = tp[(tp.dbh <= DBH_MAX) & tp.y.notna() & tp.genusspecies.notna() & ~tp.genusspecies.str.startswith("Unknown")].copy()
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
from sklearn.isotonic import IsotonicRegression


def cv(Xa, ya, ga, sets, calibrate=None):
    """Outer spatial CV. For set `calibrate`, isotonic is fitted on inner OOF predictions of the training blocks."""
    oof = {k: np.zeros(len(ya)) for k in sets}; cal = np.zeros(len(ya))
    for tr, te in GroupKFold(5).split(Xa, ya, ga):
        for k, cols in sets.items():
            cats = [c for c in CAT if c in cols]
            m = lgb.train(params, lgb.Dataset(Xa.iloc[tr][cols], ya[tr], categorical_feature=cats), 400)
            oof[k][te] = m.predict(Xa.iloc[te][cols])
            if k == calibrate:
                inner = np.zeros(len(tr))
                for itr, ite in GroupKFold(3).split(Xa.iloc[tr], ya[tr], ga[tr]):
                    mi = lgb.train(params, lgb.Dataset(Xa.iloc[tr[itr]][cols], ya[tr[itr]], categorical_feature=cats), 400)
                    inner[ite] = mi.predict(Xa.iloc[tr[ite]][cols])
                iso_f = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(inner, ya[tr])
                cal[te] = iso_f.predict(oof[k][te])
    return oof, cal


oof, p_cal = cv(X, y, groups, SETS, calibrate="full")


def within_cohort_auc(p, yy=None, co=None):
    """Mean AUC within record-year cohorts (weighted by n): ranking at equal record age."""
    yy = y if yy is None else yy; co = cohort if co is None else co
    num = den = 0
    for yr in np.unique(co):
        mk = co == yr
        if yy[mk].min() != yy[mk].max() and mk.sum() >= 100:
            num += roc_auc_score(yy[mk], p[mk]) * mk.sum(); den += mk.sum()
    return round(num / den, 4)


def calib(p, yy, bins=10):
    q = pd.qcut(p + 1e-9 * np.arange(len(p)), bins, duplicates="drop")
    return pd.DataFrame({"pred": p, "obs": yy}).groupby(q, observed=True).mean().round(3).values.tolist()


metrics = {"endpoint": "recorded poor condition (not survival)", "dbh_max_in": DBH_MAX,
           "n": int(len(y)), "poor_rate": round(float(y.mean()), 4), "spatial_blocks": int(len(set(groups))),
           "auc": {k: round(roc_auc_score(y, v), 4) for k, v in oof.items()},
           "within_cohort_auc": {k: within_cohort_auc(v) for k, v in oof.items()},
           "brier_raw": {k: round(brier_score_loss(y, v), 4) for k, v in oof.items()},
           "brier_full_nested_isotonic": round(brier_score_loss(y, p_cal), 4),
           "brier_constant_rate": round(float(np.mean((y - y.mean()) ** 2)), 4),
           "calibration_raw_deciles_[pred,obs]": calib(oof["full"], y),
           "calibration_nested_isotonic_deciles_[pred,obs]": calib(p_cal, y)}
# Review fix: nested calibration makes the Brier score WORSE than the raw score (see metrics), so no calibrator
# is applied to the outputs. `p_poor` is the raw model score: a relative ranking value, not a probability.
final = lgb.train(params, lgb.Dataset(X, y, categorical_feature=CAT), 400)
final.save_model(str(OUTM / "condition_risk_lgbm.txt"))
imp = pd.Series(final.feature_importance("gain"), index=X.columns).sort_values(ascending=False)
metrics["top_features_gain_pct"] = (100 * imp / imp.sum()).round(1).head(15).to_dict()
(OUTP / "condition_risk_cv_metrics.json").write_text(json.dumps(metrics, indent=2))
print(json.dumps(metrics, indent=1))

# ---------------- score Area A candidates x approved species ----------------
sites = gpd.read_file(ROOT / "data/processed/sites_area_a.gpkg")
cand_all = sites[(sites.in_core.astype(str) == "True") & (sites.plantable_status == "candidate")]
cand = cand_all[cand_all.ps_id.isin(SF.index)]
no_pred = sorted(set(cand_all.ps_id) - set(cand.ps_id))   # candidates with no Bronx planting-space match: no prediction
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
    rows.append(pd.DataFrame({"ps_id": cand.ps_id.values, "taxon": t, "species_in_training": sci_match is not None, "p_poor": p.round(4)}))
sc = pd.concat(rows)
sc.to_csv(ROOT / "data/processed/area_a_species_condition_risk.csv", index=False)
summ = sc.groupby("taxon").agg(median_p_poor=("p_poor", "median"), in_training=("species_in_training", "first")).sort_values("median_p_poor")
print(f"\nscored {cand.ps_id.nunique()} candidate sites x {len(approved)} approved species")
# independent check: species ranking vs 2015 census young-tree % poor (Bronx)
kbq = kb.set_index("taxon")
summ["census_young_pct_poor"] = pd.to_numeric(kbq.reindex(summ.index).bronx_c15y_pct_poor, errors="coerce")
from scipy.stats import spearmanr
ok = summ.census_young_pct_poor.notna()
rho = spearmanr(summ.median_p_poor[ok], summ.census_young_pct_poor[ok])
metrics["spearman_vs_census_young_poor"] = {"rho": round(float(rho.statistic), 3), "p": round(float(rho.pvalue), 4), "n_species": int(ok.sum())}
(OUTP / "condition_risk_cv_metrics.json").write_text(json.dumps(metrics, indent=2))
summ.to_csv(OUTP / "area_a_species_condition_summary.csv")
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
(OUTP / "condition_risk_cv_metrics.json").write_text(json.dumps(metrics, indent=2))
print(json.dumps(eff, indent=1))

# ---------------- site-level risk for Area A candidates ----------------
trained = sc[sc.species_in_training]
site = trained.groupby("ps_id").p_poor.agg(site_risk_median="median", site_risk_min="min", site_risk_max="max").reset_index()
site["has_prediction"] = True
site = pd.concat([site, pd.DataFrame({"ps_id": no_pred, "has_prediction": False})], ignore_index=True)
site.to_csv(ROOT / "data/processed/area_a_site_condition_risk.csv", index=False)
print("candidates", len(cand_all), "| with prediction", len(cand), "| without", len(no_pred))
print(site.describe().round(3).to_string())

# ---------------- DBH-threshold sensitivity (selection-bias check) ----------------
sens = {}
for thr in (4, 6, 8):
    d2 = tp[(tp.dbh <= thr) & tp.y.notna() & tp.genusspecies.notna() & ~tp.genusspecies.str.startswith("Unknown")].copy()
    d2 = d2[d2.plantingspaceglobalid.isin(SF.index)]
    d2["sci"] = d2.genusspecies.str.split(" - ").str[0].str.strip()
    X2 = pd.concat([SF.loc[d2.plantingspaceglobalid].reset_index(drop=True), species_frame(d2.sci.values)], axis=1)
    X2["sp"] = np.where(d2.sci.isin(keep_sp), d2.sci, "other"); X2["genus"] = d2.sci.str.split().str[0].values
    X2["exposure_yr"] = ((NOW - d2.createddate).dt.days / 365.25).clip(0, 30).values
    for c in CAT:
        X2[c] = pd.Categorical(X2[c].astype(str), categories=X[c].cat.categories)
    X2 = X2[X.columns]; y2 = d2.y.astype(int).values; co2 = d2.createddate.dt.year.values
    g2 = np.floor(d2.geometry.x.values / 1000).astype(np.int64) * 100000 + np.floor(d2.geometry.y.values / 1000).astype(np.int64)
    o2, _ = cv(X2, y2, g2, {"exposure_only": ["exposure_yr"], "full": list(X.columns)})
    by_year = pd.Series(y2).groupby(co2).mean()
    sens[f"dbh<={thr}in"] = {"n": int(len(y2)), "poor_rate": round(float(y2.mean()), 3),
                             "poor_rate_2015_records": round(float(by_year.get(2015, np.nan)), 3),
                             "poor_rate_2025_records": round(float(by_year.get(2025, np.nan)), 3),
                             "auc_full": round(roc_auc_score(y2, o2["full"]), 4),
                             "within_cohort_auc_full": within_cohort_auc(o2["full"], y2, co2),
                             "within_cohort_auc_exposure_only": within_cohort_auc(o2["exposure_only"], y2, co2)}
metrics["dbh_threshold_sensitivity"] = sens
(OUTP / "condition_risk_cv_metrics.json").write_text(json.dumps(metrics, indent=2))
print(json.dumps(sens, indent=1))
