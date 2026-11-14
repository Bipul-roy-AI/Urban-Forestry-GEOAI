# Young-Tree Failure Model (Module 3)

**Built:** 15 Nov 2026
**Scripts:** `download_bronx_training.py`, `bronx_composites.py`, `train_survival.py`
**Model files:** `models/survival_lgbm.txt` (LightGBM), `models/survival_isotonic.joblib` (calibration)
**Metrics:** `outputs/survival_cv_metrics.json`
**Area A outputs:**
- `data/processed/area_a_site_failure_risk.csv`: **site risk, the main output**
- `data/processed/area_a_species_failure_risk.csv`: site × species
- `outputs/area_a_species_failure_summary.csv`

## What it predicts

The probability that a **young street tree** (trunk ≤4 in) is recorded as failed rather than healthy after **5 years of record exposure**, at a given planting space. Training covers the whole Bronx (Area B).

| Label | Definition (NYC Forestry Tree Points) |
|---|---|
| Failed (1) | Dead or Critical; Stump, Uprooted or Shaft; Retired and recorded Dead/Critical/Poor; standing in Poor condition |
| Healthy (0) | Standing in Good or Excellent condition |
| Excluded | Fair or Unknown condition; Retired with Good/Excellent/Fair/Unknown (likely administrative) |

- **Training data:** 20,309 young trees in the Bronx; 16.6% failed; 139 species with at least 30 trees.
- **Features:**
  - species and genus, plus traits from the species KB
  - planting-space attributes
  - PLUTO land use
  - distance to curb and building, height of the nearest building
  - Landsat summer surface temperature (31 clear scenes) and Sentinel-2 NDVI at the point and within 100 m (152 scenes)
  - Heat Vulnerability Index
  - **record exposure in years** (fixed at 5 when scoring)

## Validation

All results are **spatial cross-validation**: 5 folds, holding out whole 1 km blocks (132 blocks).

| Model | AUC | **AUC at equal exposure** (within record-year cohorts) | Brier |
|---|---|---|---|
| Record exposure only | 0.715 | 0.536 | 0.108 |
| + species & traits | 0.736 | 0.553 | 0.116 |
| **Full (+ site)** | **0.779** | **0.652** | 0.116 → **0.106 after isotonic calibration** |

- **Calibration** after isotonic regression is close to perfect. Examples by decile: predicted 0.105 vs observed 0.116, 0.285 vs 0.285, 0.643 vs 0.640.
- **Failure depends strongly on record year:** 64% of young-tree records from 2015 have failed, versus 2% from 2025. That is time-at-risk. **A raw species failure rate is therefore confounded by when each species was planted.** The naive species-rate baseline scored AUC 0.447 across space for this reason, and exposure is included as a covariate.
- **External check:** the model's species ranking vs 2015-census young-tree % poor gives Spearman ρ = 0.22, p = 0.20, n = 35. **Not significant.**

## Findings

1. **Site matters more than species.** At equal exposure, site features add +0.10 AUC and species adds +0.02. The tool should therefore use this model mainly to **flag high-risk sites**, where pit improvements, irrigation or stewardship are needed, rather than to choose species.
2. **Direction of site effects** (mean SHAP log-odds, lowest → highest quintile):
   - **Greenness at the spot** (Sentinel-2 NDVI 0.05 → 0.56): +0.50 → −0.43. Paved locations fail more. *Some reverse causality is possible: healthy trees raise NDVI. The 10 m pixel mostly reflects surroundings.*
   - **Distance to curb** (0.3 → 46 m): curbside pits +0.10/+0.13, set-back or lawn sites −0.11.
   - **Heat Vulnerability Index** (2 → 5): −0.18 → +0.08–0.11.
   - **Large lots** (campuses, parks): −0.15.
   - **Summer surface temperature:** no consistent direction once greenness is included.
3. **Area A candidates** (103 of the 121 core candidates matched a Bronx planting space):
   - 5-year failure risk, median across the trained species: mean 8.6%, range 6.2–22.9%.
   - The best-to-worst species spread at a site averages 5.7% → 19.8%.
   - Use `area_a_site_failure_risk.csv` to prioritise site preparation.

## Limits (state these whenever results are shown)

- **This is not measured survival.** It is a cross-sectional failure label from the live inventory. Removal reasons and inspection timing add noise.
- **Species not in training** (Turkish filbert, Crimean linden, European birdcherry, Sargent cherry, Schubert cherry) fall into "other" and **must not be read as low risk**. They are excluded from the site-risk summary.
- **No soil, pit-size or watering data.** These are probably the strongest real drivers. Field data or the Trees Count 2025 census are needed.
- **Missing feature:** LiDAR shade covers only Area A, not the whole Bronx.
- **Next upgrade:** retrain on Trees Count 2025 → 2015 tree-level survival once released. Add stewardship (311 tree-care requests) and work-order watering history as features.
