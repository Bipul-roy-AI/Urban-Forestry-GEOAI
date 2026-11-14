# Benefit Modelling (Module 4)

**Built:** 15 Nov 2026. **Scripts:** `solweig_scenarios.py` (pedestrian heat), `benefits.py` (per-site benefits, air quality, stormwater)
**Outputs:**
- `data/processed/area_a_site_benefits.csv`: one row per core candidate site (121)
- `data/processed/solweig/<scenario>/tmrt/`: hourly Tmrt rasters
- `data/processed/solweig/delta_tmrt_pm_*.tif`
- `outputs/benefits_summary.json`
- `outputs/benefits_map.png`

## 1. Pedestrian heat: SOLWEIG mean radiant temperature (Tmrt)

| Item | Setting |
|---|---|
| Engine | `solweig` 0.1.0b103 by UMEP-dev: an experimental Rust/Python port, parity-tested against reference UMEP (not the reference implementation). Lindberg et al. (2008), *Int J Biometeorol* 52, 697–713 |
| Domain | Area A core + 150 m buffer, 1 m grid (1,234 × 1,160 px) |
| Surfaces | DSM = ground + buildings (LiDAR 2017; NYC footprints); CDSM = refined canopy height; DEM = DTM |
| Weather | **24 Jun 2025**, the hottest clear summer day of 2019–2025 in ERA5 (Open-Meteo archive), 07–20 EDT. ERA5 air temperature shifted −2.4 °C so the peak (37.8 °C) equals the mean of the observed maxima: Central Park 99 °F, LaGuardia 101 °F (NOAA ACIS) |
| Shadow reach | Capped at 150 m (machine tile limit). Tallest buildings ~60 m, so only very low sun angles are affected |
| Scenarios | **S0** current canopy; **S1** one tree at each of the 121 core candidate sites, 10 yr (height 7 m, crown Ø 5 m); **S2** same sites, 20 yr (11 m, Ø 8 m) |
| Crown sizes | **Assumptions** for a generic medium street tree, pending USFS Urban Tree Database growth curves |

### Results (afternoon mean, 13–16 h)

- **Sanity check:** existing sidewalk under canopy averages **45.1 °C** Tmrt versus **60.1 °C** in the open. A 15 °C shade benefit is in the range reported in the SOLWEIG literature.
- **Core sidewalks overall:** 57.0 → 56.5 (10 yr) → **56.1 °C** (20 yr). The share of sidewalk with Tmrt >60 °C falls from **49.0% → 46.9% → 45.5%**.
- **Locally, per site** (sidewalk within 15 m, median):
  - **−2.5 °C at 10 years and −4.8 °C at 20 years**.
  - 27 m² of sidewalk cooled by more than 10 °C at 20 years.
  - The best sites reach about −13 °C over 100–140 m².
- **Highest risk-adjusted cooling:** commercial and mixed-use frontages on **Third Avenue, E 137th St, Lincoln Ave and E 141st St**. These are wide, sunny sidewalks with little existing canopy.
- **Weak sites:** 5 sites give almost no cooling, and 6 have no sidewalk within 15 m. They are already shaded or set back.

**Interpretation:** 121 trees make a strong *local* difference but only shift the corridor average by ~1 °C. Moving the whole corridor means more planting sites, larger crowns (soil volume) and targeting the frontages people actually use.

## 2. Air quality and stormwater (first-order)

Per-square-metre canopy rates derived from Nowak et al. (2018), *The urban forest of New York City*, USDA FS RB NRS-117:
- 21% tree cover
- removal of O₃ 735, NO₂ 240 and PM2.5 38 tons/yr (Table 11, p. 19)
- avoided runoff 69 million ft³/yr (p. 22)
- NYC land area 783.8 km² (US Census); "tons" read as US short tons

| Per m² of canopy per year | O₃ | NO₂ | PM2.5 | Avoided runoff |
|---|---|---|---|---|
| Rate | 4.05 g | 1.32 g | 0.21 g | 11.9 L |
| Per site, 20-yr tree (median 49 m² new canopy) | 199 g | 65 g | 10 g | 582 L |
| All 121 sites, 20 yr | 20.1 kg | 6.5 kg | 1.0 kg | 58.8 m³ |

**Caveats:**
- These are citywide averages for an existing, mostly mature canopy (2010 conditions). Young trees with lower leaf area deliver less.
- Street-level air quality can **worsen** under dense crowns in narrow canyons, because trees reduce ventilation.
- **Oaks are high isoprene emitters** (an ozone precursor; see the species KB).
- Treat these numbers as removal estimates, not as changes in concentration people breathe.

## 3. Risk adjustment

`exp_cooled_m2_20yr` = sidewalk area cooled by >10 °C × (1 − 5-year failure risk from the survival model). 18 sites have no risk score (no Bronx planting-space match).

## Limits and next steps

- **One hot day, one generic tree shape.** Species-specific crowns need the USFS growth curves (manual download pending). Leaf transmissivity uses SOLWEIG defaults.
- **The 2017 LiDAR canopy** includes trees since removed and misses newer plantings.
- **Tmrt is not air temperature.** Report it as pedestrian radiant heat. UTCI can be added from the same run.
- **No field validation yet.** The summer-2027 globe-thermometer campaign is the test.
- **Next:** the optimiser chooses *which* sites and species within a budget, balancing cooling, survival risk, diversity (10-20-30), allergy/BVOC flags and soil volume.
