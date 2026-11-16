# Benefit Modelling (Module 4)

**Revised:** 16 Nov 2026, after an external audit and a code review. Earlier numbers are superseded.
**Scripts:** `solweig_scenarios.py` (pedestrian heat), `benefits.py` (per-site benefits), `evaluate_plans.py` (whole-plan comparison)
**Outputs:**
- `data/processed/area_a_site_benefits.csv`: one row per confirmed candidate site (98)
- `outputs/benefits_summary.json`, `outputs/plan_evaluation.json`
- `outputs/benefits_map.png`
- Heat rasters (`data/processed/solweig/`) are rebuilt by the scripts and not stored in the repository

## What changed in this revision

| Problem found | Fix |
|---|---|
| Weather file is in UTC−5, but the model was told UTC−4, so sun and weather were one hour apart | Model clock set to UTC−5; a check asserts that radiation peaks at solar noon |
| Cooling was summed in overlapping 15 m buffers (3,783 m² reported; 2,277 m² unique) | Each sidewalk pixel belongs to its nearest site; totals are asserted to add up |
| No ground-material map (uniform default surface) | Material map: buildings, grass, water, paved. Sidewalk polygons are always paved |
| "10-year" and "20-year" labels with no growth model | Scenarios are named by **assumed crown size** (5 m, 8 m) |
| Trees placed at sites with conflicting records | Only the 98 confirmed candidates receive trees |
| Heat rasters had no map coordinates | Every raster is written with CRS and transform |

## 1. Pedestrian heat: SOLWEIG mean radiant temperature (Tmrt)

| Item | Setting |
|---|---|
| Engine | `solweig` 0.1.0b103 by UMEP-dev: an experimental Rust/Python port, parity-tested against reference UMEP. Lindberg et al. (2008), *Int J Biometeorol* 52, 697–713 |
| Domain | Area A core + 150 m buffer, 1 m grid (1,234 × 1,160 px) |
| Surfaces | DSM = ground + buildings (LiDAR 2017; NYC footprints); CDSM = refined canopy height; DEM = DTM |
| Ground materials | 58% paved, 29% buildings, 12% grass, 1% water. From NAIP imagery and footprints. Sidewalk concrete is approximated as asphalt |
| Weather | **24 Jun 2025**, hottest clear summer day of 2019–2025 in ERA5 (Open-Meteo archive). Air temperature shifted −2.4 °C so the peak (37.8 °C) equals the mean of observed maxima at Central Park (99 °F) and LaGuardia (101 °F) |
| Afternoon window | 13:00–17:00 EDT (four hourly intervals) |
| Scenarios | **S0** current canopy; **S1** one tree per candidate with a 5 m crown (7 m tall); **S2** with an 8 m crown (11 m tall) |

### Results (afternoon mean)

- **Plausibility check:** existing sidewalk under canopy averages **45.3 °C** Tmrt against **62.3 °C** in the open. This is a model output compared with itself, not an independent validation.
- **Core sidewalks:** 58.7 °C now → 58.3 °C (5 m crowns) → **57.9 °C** (8 m crowns). The share above 60 °C falls from **53.1% → 51.4% → 50.1%**.
- **Unique sidewalk cooled by more than 10 °C:** **1,139 m²** (5 m crowns) and **2,167 m²** (8 m crowns). Each square metre is counted once.
- **Per site** (sidewalk nearest to that site, median): **−2.6 °C** with a 5 m crown and **−4.8 °C** with an 8 m crown; 22 m² cooled by more than 10 °C with an 8 m crown.
- **Adverse changes:** 4 m² of sidewalk gets more than 1 °C warmer. These are reported, not hidden.
- **Eight sites** have no sidewalk within 15 m that a nearer site does not claim. They are flagged `no_sidewalk_benefit`.

**Interpretation:** a new tree makes a strong local difference, but 98 trees shift the corridor average by less than 1 °C.

## 2. Air quality and stormwater (first-order)

Per-square-metre canopy rates from Nowak et al. (2018), *The urban forest of New York City*, USDA FS RB NRS-117 (21% tree cover; O₃ 735, NO₂ 240, PM2.5 38 tons/yr, Table 11 p. 19; avoided runoff 69 million ft³/yr, p. 22; NYC land 783.8 km²; "tons" read as US short tons).

New canopy is taken from the **simulated** crown mask (buildings excluded, overlapping crowns counted once): 3,761 m² for 8 m crowns.

| Per m² of canopy per year | O₃ | NO₂ | PM2.5 | Avoided runoff |
|---|---|---|---|---|
| Rate | 4.05 g | 1.32 g | 0.21 g | 11.9 L |
| Per site, 8 m crown (median 42 m² new canopy) | 170 g | 56 g | 9 g | 499 L |
| All 98 sites, 8 m crowns | 15.2 kg | 5.0 kg | 0.8 kg | 44.6 m³ |

**Caveats:**
- These are citywide averages for an existing, mostly mature canopy. Young trees with lower leaf area deliver less.
- They estimate pollutant **removal**, not the change in the air people breathe. Dense crowns in narrow streets can trap pollution.
- Oaks are high isoprene emitters (an ozone precursor; see the species KB).

## 3. Whole-plan evaluation

The optimiser uses an additive per-site estimate to search. Shortlisted plans are then **re-simulated as a whole** in SOLWEIG, with every tree at its own assumed crown size, and compared on unique sidewalk pixels (`evaluate_plans.py`). The simulated value is the one to report. Results are in [Optimiser.md](Optimiser.md).

## Limits

- **One hot day, assumed crown sizes.** There is no growth model yet; the USFS Urban Tree Database file still has to be acquired.
- **Tmrt is not air temperature.** SOLWEIG models radiation; it does not model cooling of the air by evapotranspiration.
- **Geometry dates differ:** LiDAR 2017, imagery 2022–23, city records 2026.
- **Road pavement under tree crowns** outside sidewalk polygons can still be labelled grass.
- **Shadow reach is capped at 150 m** (machine memory limit).
- **No field validation.** Tmrt needs globe-thermometer or radiation measurements; air-temperature loggers alone cannot validate it.
