# Urban Tree GeoAI: Pilot Plan v2

**Location:** Mott Haven, South Bronx, New York City (core site). A peri-urban contrast site and a European transfer test are added later.
**Date:** 14 Nov 2026. This plan builds on `Chat.txt` and keeps its corridor choice: Third Avenue, E 135th to E 139th St, plus Graham Triangle. It adds a satellite layer, a ground-sensor layer, a street-level imagery layer, a machine-learning layer and an evaluation design.

---

## 1. Is it feasible?

**Yes, as a decision-support system for one neighbourhood within about 12 months. A worldwide "optimum tree" oracle is not feasible yet.**

| Part | Feasible now? | Why |
|---|---|---|
| Finding where a tree can physically go | **Yes** | NYC publishes trees, planting spaces, sidewalks, buildings, LiDAR and 15 cm imagery |
| Shade and pedestrian heat effect per tree | **Yes, by physics models** | UMEP/SOLWEIG models this at 1 m. It can be validated with globe thermometers |
| Which species will *survive and grow* at a site | **Partly, by ML** | NYC tree records hold hundreds of thousands of trees with species, size and condition, enough to train a survival/health model |
| Stormwater interception, pollutant deposition, CO₂ | **Yes, approximate** | i-Tree Eco-style equations. Report these as estimates, not measurements |
| Street-level air quality improvement | **Screening only** | Trees can trap pollution in narrow streets. Species emit BVOCs (ozone precursors). Rank the risk; do not promise a percentage |
| Soil moisture gain | **No (not credibly)** | Trees consume water. Model the water balance instead |
| Root behaviour per site | **Proxy only** | No public underground utility data. Use 311 sidewalk/root complaints and pit size as proxies |
| Any city in the world | **Later** | The method transfers, but data quality drops. Section 9 explains the global data stack |

**What the "AI" actually is:** five connected modules, not one model. They are: (1) a site characterisation engine, (2) a species knowledge base, (3) an ML survival/growth model, (4) physics-based benefit models, and (5) a multi-objective optimiser. A grounded LLM interface sits on top for planners. The LLM explains and queries results; it never invents numbers.

---

## 2. Study design

| Area | Purpose | Size |
|---|---|---|
| **A. Core**: Mott Haven, Third Ave corridor + Graham Triangle | Full modelling, field validation, comparison against the city's real street design proposal | ~0.25–0.5 km² |
| **B. Training region**: all of the Bronx (or all 5 boroughs) | Train the survival/health ML model on many trees | Borough/city |
| **C. Peri-urban contrast**: Staten Island south shore (e.g. Tottenville / Charleston) | Tests a different land use: low density, more open soil, salt spray, existing habitat | ~0.5 km² |
| **D. Transfer test** (phase 2): Berlin (Baumkataster + Umweltatlas) | Checks that the method works outside NYC | ~0.5 km² |

Area C still needs confirming against NYC Parks land and the Staten Island Bluebelt. Pick a site where planting would not damage valuable open habitat.

---

## 3. Data stack

### 3.1 Satellite (context and change detection)

| Data | Resolution | Use | Access |
|---|---|---|---|
| **Landsat 8/9 LST** (Collection 2 L2) | 100 m thermal, delivered at 30 m | Summer surface-heat screening, 2013–present | USGS EarthExplorer / AWS / GEE, free |
| **ECOSTRESS LST** | ~70 m | **Afternoon** surface temperature (Landsat only passes ~10:30 am). Diurnal heat, plant water stress | NASA Earthdata / AWS, free. Mission still acquiring in 2026 |
| **Sentinel-2 L2A** / **HLS** (Harmonized Landsat-Sentinel) | 10–30 m | NDVI and phenology, canopy greenness trend, tree stress over time | Copernicus / NASA, free |
| **PlanetScope** | 3 m daily | Optional: fine canopy change. Paid; US researchers may get access via NASA CSDA | Optional |
| Sentinel-5P NO₂ | ~5 km | City-scale context only. **Too coarse for street decisions** | Free |

### 3.2 Airborne (the geometry backbone)

| Data | Use |
|---|---|
| **NYC 2024 orthophoto (~15 cm)** | Map pits, paving, crowns; check current conditions |
| **NYC 2017 LiDAR** (check for any newer city or USGS 3DEP collection) | DSM/DEM → building heights, canopy height model, **sun-hours and sky-view factor at 1 m** |
| **NYC high-resolution land cover** (6-inch class) | Impervious / tree / grass / soil fractions per site |
| **NAIP** (60 cm, 4-band with NIR) | NDVI at sub-metre scale if the city ortho lacks NIR |

**Date mismatch:** the LiDAR is from 2017 and the imagery from 2024. Flag trees that have since been removed or planted and buildings that have changed, using Forestry work orders and DOB permits.

### 3.3 Ground data (the part most pilots lack)

| Data | What it gives | Role in the model |
|---|---|---|
| **NYC Forestry Tree Points + Planting Spaces + Work Orders / Inspections** | Species, DBH, condition, planting date, removals, site dimensions | **Main ML training labels** (survival, condition, growth) |
| **2015 Street Tree Census** (~680k trees) | Species, DBH, health, root/trunk/branch problems such as "root stone", "root grate", "sidewalk damage" | Training labels for **root–infrastructure conflict** and health |
| **Trees Count 2025** (fourth census, *in progress*) | 2015 → 2025 change per tree, once released | Gold-standard **10-year survival and growth** labels. Add them when published |
| **NYC 311** (tree damage, root/sidewalk, dead tree requests) | Location-specific complaints | Root-conflict and maintenance-risk labels |
| **NYS Mesonet NYC Micronet** (29 stations, 5-min) | Air temperature, humidity, wind, solar radiation, precipitation | Weather forcing for SOLWEIG; validation |
| **NOAA ASOS** (LGA, Central Park, JFK) | Long-term weather | Climate context, heat-day selection |
| **NYCCAS** (annual PM2.5/NO₂ surfaces + real-time monitors, incl. Mott Haven) | Neighbourhood air quality | Pollution exposure layer; prioritising where people breathe worst air |
| **PurpleAir** (public low-cost PM2.5 sensors) | Dense but uncalibrated PM2.5 | Supplementary only; apply the EPA correction |
| **2021 community heat campaign** (South Bronx / N. Manhattan, 24 Jul 2021) | Street-level air temperature/humidity traverse | Historical heat validation (check raw data availability) |
| **NRCS SSURGO + NYC Reconnaissance Soil Survey** | Soil texture, drainage, urban fill classes | Broad soil constraints. **Not pit-level** |
| **NYC DEP stormwater flood maps, green infrastructure layer** | Flood exposure, existing bioswales | Water-benefit targeting; avoiding conflicts |
| **Heat Vulnerability Index (NYC DOHMH)** | Social vulnerability to heat | Equity weight in the optimiser |

### 3.4 Street-level imagery (ground truth at scale)

| Source | Licence fit | Use |
|---|---|---|
| **Mapillary** (Meta) | Open, CC-BY-SA, API, derived data allowed | **Primary.** Detect overhead wires, sidewalk width, pit size, tree presence/species check, shop awnings; compute **sky-view factor** from panoramas |
| **Your own 360° capture** (e.g. an Insta360 camera, uploaded to Mapillary) | You own it | Fill gaps in the core area; summer + winter (leaf-off) passes |
| Google Street View | Viewing allowed; storing/deriving datasets restricted by its terms | Manual visual checks only. **Do not build training data from it** |

Street-level checks do two jobs:
- **Overhead wires** are the biggest constraint on tree height that LiDAR misses. Detect them from images with a segmentation model, or label 200–300 images by hand.
- **Sky-view factor** from panoramas validates the LiDAR-derived SVF.

### 3.5 Planning and land-use layer (what makes it a planning tool)

| Data | Use |
|---|---|
| **MapPLUTO** (tax-lot land use, building class, floor area) | Land-use type per frontage → objective weights (residential, commercial, industrial, institutional, open space) |
| **Zoning (ZoLa / zoning districts)** | Future development pressure; where buildings may grow and shade trees |
| **NYC Planimetrics** (sidewalks, curbs, hydrants, driveways, bus stops) | Hard placement constraints |
| **NYC Street Design Manual + Parks Tree Planting Standards** | Official clearance rules (codify them, do not guess buffers) |
| **Third Avenue corridor improvement concept + DOT/DDC capital projects** | **The "real proposal" baseline** to compare against |
| **NYC approved street tree species list** | Starting species pool |

### 3.6 Species knowledge base (~25 species to start)

Build this by hand and source every field; it is the system's foundation. Fields:

- **Growth:** mature height/spread, growth rate, longevity. Use the **USFS Urban Tree Database** allometric equations, for which Queens, NY is a reference city.
- **Tolerance:** USDA zone (NYC ≈ 7b), drought, flooding, **road salt**, compaction, shade.
- **Infrastructure:** root aggressiveness, minimum soil volume, wire clearance, sidewalk heave risk.
- **Environment:** shade density (leaf area index), **BVOC/isoprene emission class** (ozone risk), **pollen allergenicity**, **pollinator value** (native bees and other insects), stormwater interception.
- **Climate future:** suitability under 2050–2080 climate (e.g. USFS Climate Change Tree Atlas).
- **Risk:** pests (emerald ash borer → avoid *Fraxinus*; spotted lanternfly host → avoid *Ailanthus*), maintenance.
- **Local:** native to the NY region (yes/no), nursery availability, NYC Parks approval.
- **Diversity rule:** no more than 10% of one species, 20% of one genus, 30% of one family. This "10-20-30" guideline is applied by the optimiser.

Unknown trait = `null`, never guessed. Every value carries its source.

---

## 4. System architecture

```
[Data layers] → (1) Site engine → per-site feature vector
                                     │
[Species KB] ───────────────────────┤
                                     ▼
              (2) ML survival / condition / growth model
                                     ▼
              (3) Benefit models: SOLWEIG Tmrt, shade hours,
                  stormwater, deposition, BVOC/allergy risk
                                     ▼
              (4) Multi-objective optimiser (per land use)
                                     ▼
              (5) Planner interface: map + grounded LLM Q&A
```

**(1) Site engine.** Each candidate site (existing planting space or detected vacant pit) gets about 40 features:
- Space: sidewalk width, pit area, distance to buildings, curb, hydrant, driveway.
- Wires (yes/no) from street imagery.
- Sun-hours (June–August) and sky-view factor from LiDAR.
- Impervious fraction in a 30 m buffer.
- Summer LST from Landsat and ECOSTRESS afternoon passes.
- Soil class, flood exposure, NYCCAS PM2.5/NO₂, land use from MapPLUTO.
- Heat Vulnerability Index, pedestrian activity proxy (bus stops, schools, commercial frontage).

**(2) ML model.** Use gradient-boosted trees (LightGBM/XGBoost) as a baseline, then optionally a spatial model.
- **Targets:** tree alive after N years; condition (good/fair/poor); DBH growth rate; root-sidewalk conflict.
- **Inputs:** site features × species traits.
- **Validation:** spatial block cross-validation. Hold out whole neighbourhoods, otherwise accuracy is inflated.
- **Output:** P(survive 10 yr | species, site) and expected crown size at 5/10/20 years.

**(3) Benefit models.**
- **Pedestrian heat:** UMEP/SOLWEIG mean radiant temperature (Tmrt) at 1 m for a typical hot day, run for current, proposed and 5/10/20-year canopy.
- **Shade:** shaded hours at bus stops, crossings and building entrances.
- **Stormwater:** canopy interception plus pit infiltration.
- **Air quality:** deposition estimate (i-Tree method) *and* a ventilation risk flag for street canyon H/W > ~1 with dense crowns, *and* a BVOC/ozone flag.
- **Pollinator/biodiversity score** and **allergy score**.

**(4) Optimiser.** Use NSGA-II (pymoo).
- **Decision variables:** which site, which species, and which site improvement (none / larger pit / structural soil / depaving).
- **Objectives:** maximise expected Tmrt reduction weighted by people exposure and vulnerability; maximise survival-weighted canopy at 20 years; minimise cost and irrigation; maximise biodiversity; minimise allergy/BVOC risk.
- **Constraints:** hard placement rules, 10-20-30 diversity, budget.
- **Output:** a Pareto set. The planner picks a balance. **Land use changes the weights:** shade at bus stops on commercial streets, root safety on residential streets, pollution and soil remediation in industrial areas, habitat continuity in parks and peri-urban areas.

**(5) Interface.**
- QGIS project + a web map (e.g. Streamlit + MapLibre).
- LLM layer with tool calls over the results database. Example: *"Show sites on Third Ave where a medium tree survives with P>0.8 and cuts afternoon Tmrt at the bus stop by >5 °C."*
- Every answer cites its data layer and states its uncertainty.

---

## 5. Evaluation: how we know it works

| Level | Test | Pass signal |
|---|---|---|
| **A. Prediction** | Held-out survival/condition (spatial blocks); later, true 2015→2025 census change | AUC ≥ ~0.7 for survival; calibrated probabilities. Target is to be set after the baseline |
| **B. Physics** | SOLWEIG Tmrt vs. **your measured Tmrt** (globe thermometer) and Micronet air temperature; LiDAR SVF vs. street-image SVF | Tmrt RMSE within the range reported in SOLWEIG validation studies; SVF agreement |
| **C. Retrospective "natural experiment"** | Blocks heavily planted 2010–2018 (from work orders) vs. matched unplanted blocks → change in summer LST/NDVI (difference-in-differences) | Shows whether the benefit signal is detectable at all. Honest either way |
| **D. Decision quality** | Compare the optimiser against: random feasible planting, a "plant the hottest gaps" rule, UMEP TreePlanter, **the city's Third Ave design**, and an arborist's plan, all on the same budget | More vulnerability-weighted shade per dollar, fewer conflicts, higher expected survival |
| **E. Expert review** | Blind ranking by 2–3 arborists/planners (NYC Parks, NYC Street Tree Consortium, local university) | Recommendations judged plausible ≥ 70% of the time (proposed threshold) |

---

## 6. Field campaign (summer 2027, the next feasible season)

| Item | Qty | Purpose | Rough cost (estimate) |
|---|---|---|---|
| Air temperature/RH loggers with radiation shields (e.g. Onset HOBO MX2301) | 8–10 | Shaded vs. unshaded street pairs | ~$2–3k |
| Black-globe / heat-stress meter (e.g. Kestrel 5400) | 2 | **Tmrt validation** (air temperature alone cannot validate it) | ~$1k |
| Low-cost PM2.5 sensors (PurpleAir) | 3–4 | Under-canopy vs. open street, with colocation at NYCCAS site for calibration | ~$1k |
| Soil moisture probe + penetrometer | 1 each | Pit soil moisture, compaction at ~30 sample pits | ~$1k |
| 360° camera | 1 | Mapillary capture of core and peri-urban areas | ~$0.5k |
| Handheld IR thermometer | 1 | Surface temperature spot checks (pavement under vs. outside canopy) | ~$0.1k |

**Total about $6–8k.** Put loggers on private property or institutional partners' sites (schools, community gardens, a local CBO such as WE ACT or The POINT CDC); street furniture needs permits. Measure on clear, hot days (heat advisory forecasts), running hourly from 10:00 to 19:00.

---

## 7. Timeline (Nov 2026 – Oct 2027)

| Months | Work |
|---|---|
| **Nov–Dec 2026** | Data-access audit and downloads. Reproduce the UMEP NYC SOLWEIG tutorial. Build the species KB v0 |
| **Jan–Feb 2027** | Site engine + candidate sites for Area A. LiDAR sun-hours/SVF. Mapillary wire/SVF extraction |
| **Mar–Apr 2027** | ML survival/condition model on Area B (spatial CV). Retrospective LST/NDVI test (Evaluation C) |
| **May 2027** | Benefit models + optimiser v1. Baselines. Recruit expert reviewers and field partners |
| **Jun–Aug 2027** | **Field campaign.** Physics validation (B). Summer 360° imagery. ECOSTRESS afternoon scenes |
| **Sep 2027** | Peri-urban Area C. Decision-quality comparison (D) and expert review (E) |
| **Oct 2027** | Web map + LLM interface. Write-up (paper + planner brief). Add Trees Count 2025 labels if released |

A **demo** (map + candidate sites + shade simulation for one block) is possible by **end of Jan 2027**. It is not a validated result.

---

## 8. Tools

Python (geopandas, rasterio, xarray, pystac-client, scikit-learn, LightGBM, pymoo); QGIS + UMEP (SOLWEIG, TreePlanter); PDAL/lidR for LiDAR; Google Earth Engine or Microsoft Planetary Computer for Landsat/Sentinel/HLS; Mapillary API + a segmentation model (e.g. Mask2Former/SAM) for street images; i-Tree tools/equations; Streamlit/MapLibre; PostgreSQL/PostGIS. Track everything with git + DVC. Keep `data/raw` read-only and store a provenance record for every layer.

---

## 9. Scaling to "any place in the world" (phase 3)

Replace city data with global layers and accept lower precision:

| Need | Global source |
|---|---|
| Canopy height | Meta/WRI 1 m global canopy height; GEDI |
| Buildings | Google Open Buildings, Microsoft Building Footprints, Overture Maps |
| Streets/land use | OpenStreetMap, Overture; ESA WorldCover 10 m; Copernicus Urban Atlas (EU) |
| Heat | Landsat, ECOSTRESS |
| Weather/climate | ERA5-Land, WorldClim / CHELSA futures |
| Soil | SoilGrids 250 m (coarse; field check needed) |
| Species | GBIF occurrences + national lists; species-trait databases (some, like TRY, need data requests) |

The NYC-trained ML model will **not** transfer directly. Use the Berlin test (Area D) to measure how much accuracy drops and which local data restore it.

---

## 10. Main risks

1. **Date mismatch** between the 2017 LiDAR and current conditions. Mitigate with work orders, permits and street images.
2. **No underground utility data.** Every recommendation stays "subject to utility markout and pit survey".
3. **Survival labels are biased.** Trees die from vandalism, construction and maintenance, not only site conditions. Include maintenance and stewardship proxies, and do not over-interpret.
4. **Air-quality claims.** Present only as a risk flag plus deposition estimate.
5. **Trees Count 2025 release timing is unknown.** The plan works without it.

---

## Key references (verify before formal citation)

- Lindberg, F., Holmer, B., & Thorsson, S. (2008). SOLWEIG 1.0: Modelling spatial variations of 3D radiant fluxes and mean radiant temperature in complex urban settings. *International Journal of Biometeorology, 52*(7), 697–713.
- McPherson, E. G., van Doorn, N. S., & Peper, P. J. (2016). *Urban tree database and allometric equations* (Gen. Tech. Rep. PSW-GTR-253). USDA Forest Service, Pacific Southwest Research Station.
- Benjamin, M. T., & Winer, A. M. (1998). Estimating the ozone-forming potential of urban trees and shrubs. *Atmospheric Environment, 32*(1), 53–68.
- Santamour, F. S., Jr. (1990). Trees for urban planting: Diversity, uniformity, and common sense. In *Proceedings of the 7th Conference of the Metropolitan Tree Improvement Alliance (METRIA)* (pp. 57–65).

Data sources and links for NYC layers are listed in `Chat.txt`. Additional sources checked on 14 Nov 2026: Trees Count 2025 (treescount-2025-nyc.hub.arcgis.com), NYC Micronet (nysmesonet.org/networks/nyc), ECOSTRESS (ecostress.jpl.nasa.gov).
