# Recorded-Condition Risk Model (Module 3)

**Revised:** 16 Nov 2026, after an external audit. This replaces the earlier "survival model" write-up.
**Scripts:** `download_bronx_training.py`, `bronx_composites.py`, `train_condition_risk.py`
**Model file:** `models/condition_risk_lgbm.txt` (LightGBM)
**Metrics:** `outputs/condition_risk_cv_metrics.json`
**Area A outputs:**
- `data/processed/area_a_site_condition_risk.csv`: relative site score, with a `has_prediction` flag
- `data/processed/area_a_species_condition_risk.csv`: site × species scores
- `outputs/area_a_species_condition_summary.csv`

## What it is, and what it is not

It is a model of the **current recorded condition** of small-diameter street trees in the NYC Forestry inventory (Bronx). Its output, `p_poor`, is a **relative ranking score**.

It is **not** a survival model and **not** a "5-year failure probability". Three reasons:

1. **No planting dates.** `createddate` is when the record was created, not when the tree was planted.
2. **Selection bias.** Trees are selected by their present trunk size (≤4 in). Trees that grew past 4 in are dropped, so older records are enriched for trees that died or stagnated.
3. **Probabilities do not hold up.** An honest calibration test makes the error worse, not better (see Validation).

| Label | Definition (NYC Forestry Tree Points) |
|---|---|
| Poor (1) | Dead or Critical; Stump, Uprooted or Shaft; Retired and recorded Dead/Critical/Poor; standing in Poor condition |
| Good (0) | Standing in Good or Excellent condition |
| Excluded | Fair or Unknown condition; Retired with Good/Excellent/Fair/Unknown (likely administrative) |

- **Training data:** 20,309 small trees in the Bronx; 16.6% recorded poor; 139 species with at least 30 trees; 132 one-kilometre blocks.
- **Features:** species, genus and species-KB traits; planting-space attributes; PLUTO land use; distance to curb and building; nearest building height; Landsat summer surface temperature; Sentinel-2 NDVI (deduplicated and offset-corrected); Heat Vulnerability Index; record age in years (set to 5 as a reference value when scoring).

## Validation

Spatial cross-validation: 5 folds, holding out whole 1 km blocks.

| Model | AUC | AUC within record-year cohorts | Brier (raw) |
|---|---|---|---|
| Record age only | 0.715 | 0.536 | 0.108 |
| + species & traits | 0.736 | 0.553 | 0.116 |
| **+ site conditions** | **0.779** | **0.648** | 0.117 |

**Ranking holds.** Within the same record year, site features lift AUC from 0.55 to 0.65; species adds only 0.02.

**Probabilities do not.**
- A constant prediction scores Brier 0.139. Record age alone scores 0.108, which is *better* than the full model (0.117).
- **Nested calibration test:** for each outer fold, an isotonic calibrator was fitted on inner out-of-fold predictions from the training blocks only, then applied to the untouched test blocks. Result: Brier **0.129**, worse than the raw score. Calibration learned in some neighbourhoods does not transfer to others.
- Therefore no calibrator is applied. Outputs carry the raw score and must be read as "higher = worse site", never as a percentage chance.

**Selection-bias check** (trunk-size cut-off):

| Cut-off | Trees | Poor rate in 2015 records | Poor rate in 2025 records | AUC | AUC within cohort |
|---|---|---|---|---|---|
| ≤4 in | 20,309 | 55.9% | 2.2% | 0.779 | 0.648 |
| ≤6 in | 28,267 | 41.9% | 2.2% | 0.755 | 0.654 |
| ≤8 in | 34,849 | 36.0% | 2.2% | 0.727 | 0.658 |

Widening the cut-off lets surviving trees back in, and the poor rate of old records falls from 56% to 36%. So part of the "old records fail more" pattern is an artefact of how the sample is drawn. The within-cohort ranking result is stable across all three cut-offs.

**External check:** the model's species ranking against 2015-census young-tree % poor gives Spearman ρ = 0.18, p = 0.31, n = 35. Not significant. The species ranking should not be used.

## What it supports

1. **Flagging sites.** At equal record age, site conditions separate good from poor records better than species does.
2. **Direction of site effects** (mean SHAP log-odds, lowest → highest quintile). These are associations, not causes:
   - **Greenness at the spot** (NDVI 0.07 → 0.80): +0.48 → −0.42. Paved surroundings go with poorer condition. Some reverse causality is possible.
   - **Distance to curb** (0.3 → 46 m): curbside +0.10/+0.16, set-back sites −0.10.
   - **Heat Vulnerability Index** (2 → 5): −0.17 → +0.07–0.11.
   - **Large lots:** −0.13.
   - **Summer surface temperature:** no consistent direction.
3. **Area A:** 80 of 98 confirmed candidate sites have a score (range 0.04–0.47). The other 18 have no Bronx planting-space match; they are flagged `has_prediction = False` and are never given a substitute value.

## Limits

- **Not survival.** A real survival model needs one record per tree with a planting date, repeated inspections, and death or removal dates with reasons.
- **Species not in training** (for example Crimean linden, Turkish filbert) get the site's value and a flag.
- **No soil, pit-size or watering data.** These are probably the strongest real drivers.
- **Next upgrade:** build a tree-level history from Forestry inspections and work orders, or use the Trees Count 2025 census when it is released, and model interval-censored survival.
