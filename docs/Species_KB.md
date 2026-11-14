# Species Knowledge Base (Module 2)

**Built:** 14 Nov 2026.
**Scripts:** `species_local_performance.py` → `species_usda_plants.py` → `build_species_kb.py`
**Outputs** (all in `data/species/`):
- `species_kb.csv`: wide table, **49 taxa**, with `_match_level` and `_conflict` companion columns
- `species_kb_evidence.csv`: **2,687 sourced values**, each with a `source_id` (updated 15 Nov 2026 with research-agent evidence)
- `raw/agent_*.csv`: research-agent evidence rows, with citation, URL, page/table locator and notes
- `agent_rows_rejected.csv`: rows not merged (all 9 are intentional blanks explaining missing data)
- `sources.csv`: source registry with URLs and access date
- Inputs: `nyc_parks_approved_species.csv`, `bronx_census2015_by_species.csv`, `usda_plants_profile.csv`, `usda_plants_traits.csv`, `species_pool.csv`

**Rule:** every value carries a source; unknown stays empty and is never guessed.

## Species pool

- **41 NYC Parks–approved species**. These are the only candidates for new planting.
- **8 non-approved species that are common in the Area A core**: London planetree, Callery pear, red maple, hackberry, American elm and 'Princeton' elm, buckeye/horsechestnut, green ash. They are included for retention decisions and diversity accounting, not for planting.

## Fields and sources

| Group | Fields | Source | Coverage / caveat |
|---|---|---|---|
| Planting rules | `nyc_approved`, `size_class`, `mature_height_class_ft`, `form`, `growth_rate`, `tol_*` (salt, drought, wet, wind, pollution, high pH, shade), `loc_*` (median, narrow space, small pit <3 ft), `notes` | NYC Parks approved list | All 41 approved. **`tol_*` = 0 means "not listed as tolerant", not "intolerant"** |
| Local performance (Bronx) | `bronx_c15_n`, `_pct_good`, `_pct_poor`, `_pct_sidewalk_damage`, `_pct_root_problem`, `_mean_dbh_in`; young trees (DBH ≤3 in) `bronx_c15y_n`, `_pct_good`, `_pct_poor`; `bronx_match_level` | 2015 Street Tree Census | 42 of 49 taxa. Genus-level for Amelanchier, Malus, Crataegus and the mixed "Prunus" group |
| USDA traits | `usda_symbol`, `native_L48`, `usda_drought_tol`, `_shade_tol`, `_salinity_tol`, `_anaerobic_tol`, `_moisture_use`, `_mature_height_ft`, `_growth_rate`, `_lifespan`, `_root_depth_min_in`, `_ph_min/max`, `_temp_min_f`, `_bloom_period`, `_caco3_tol`, `_foliage_porosity_summer`, `_toxicity` | USDA PLANTS API | Symbol found for 37 of 49; full trait records for ~23 (mostly natives). `native_L48` only at species level |
| Pest risk | `alb_regulated_host`, `eab_host` | APHIS DA-2015-22 (ALB, 12 genera); APHIS EAB | Flags: Platanus, Acer, Ulmus, Koelreuteria, Aesculus, Fraxinus |
| Diversity | `core_species_share_pct`, `core_genus_share_pct`, `diversity_flag` | Forestry Tree Points, 473 living trees in core | 10-20-30 rule |

## What the KB already tells us about Area A

- **London planetree is 19.9% of core trees (genus 20.7%).** It breaks both the 10% species and the 20% genus guideline. It is not on the current approved list, and it is an ALB regulated host. Plan to **retain the existing trees but not add more**.
- **Oaks are 19.2% of the core, close to the 20% genus limit.** Every approved oak is flagged, so the optimiser must limit new oaks.
- **Goldenraintree** (approved, small-pit tolerant) is an ALB regulated host. It is still allowed, but carries a pest-risk flag.
- **Young-tree health in the Bronx** (2015, DBH ≤3 in, share in Good condition):
  - Strongest: sawtooth oak 89%, English oak 88%, Cornelian cherry 87%, sweetgum 84%, serviceberry 83%.
  - Weakest: American hornbeam 68%, American elm 71%, black gum 74%, dawn redwood 74%.
- **Sidewalk damage** is highest for honeylocust (38%), London planetree (36%), willow oak (35%) and baldcypress (35%). It is lowest for Schubert cherry (12%) and serviceberry (15%). Damage rises with tree size: use the `bronx_c15_mean_dbh_in` column to compare like with like.

## Not possible with current public data (checked)

- **Per-species mortality from the 2015 census:** dead trees and stumps have no species recorded.
- **2005→2015 survival:** the 2005 positions are street addresses, not trees (45% of trees share a point; median offset 8.6 m).
- **Planting dates from Tree Points:** `createddate` is a record date. Planting work orders start in 2024 and do not link to the tree.
- **Real survival will be possible when Trees Count 2025 is released**, because both 2015 and 2025 record trees with GPS.

## Traits added 15 Nov 2026 (four research agents, merged by `build_species_kb.py`)

| Field | Taxa filled (of 49) | Main sources | Notes |
|---|---|---|---|
| `native_NY_region` | 45 | New York Flora Atlas; USDA PLANTS; POWO | Values: yes / no / hybrid-nonnative / cultivar-of-native. **Honeylocust and Eastern redbud = not native to NY** (naturalised), although USDA lists both as US natives |
| `usda_symbol` | 47 | USDA PLANTS API (verified) | London planetree = PLHI (*Platanus × hispanica*). Not in PLANTS: *Eucommia*, *Prunus sargentii* |
| `bvoc_isoprene_class` / `_monoterpene_class` (+ `_ef` where given) | 46 / 34 | Hewitt et al. Lancaster emission survey; Karlik & Pittenger (2012) UC ANR 8484 | Isoprene: low <5, moderate 5–20, high >20 µg g⁻¹ h⁻¹. **All oaks = high isoprene** (an ozone-formation risk) |
| `pollen_allergenicity` | 45 | Cariñanos et al. (2014, 2019); Citree (TU Dresden); Pollen Library | 29 taxa have conflicting ratings. The KB takes the **highest** among equally specific sources |
| `pollinator_value`, `pollinator_notes` | 44 | Xerces Society NE/Mid-Atlantic lists; NRCS/Xerces handbook; Ohio State ENT-71; Tallamy & Shropshire (2009) | Notes include caterpillar host counts by genus (Quercus 534, Prunus 456, Malus 308) |
| `climate_suitability_2070_2099` | 31 | NIACS (2021) *Climate change vulnerability of urban trees: New York, NY*; USFS Climate Change Tree Atlas (Gateway region) | **Renamed from "2050": the sources project 2070–2099.** Value is RCP8.5; RCP4.5 is in notes. 8 taxa have NIACS-vs-Atlas conflicts |
| `root_sidewalk_damage_risk` | 48 | Gilman & Watson USFS/UF street-tree fact sheets ST-series (1993/94) | Only two classes: high = "can lift sidewalks", low = "usually not a problem" |
| `min_soil_volume_m3` | 39 | UF EP309 size classes (Minnesota Stormwater Manual summary) | By size class: large 76.5, medium 34.0, small 8.5 m³ (assumes 3 ft depth) |
| `nyc_min_pit_rule` | 49 | NYC Parks Street Tree Planting Standards (2016), p. 6 | Standard pit 5 × 10 ft |
| `wire_compatible` | 21 | NYC Parks standards p. 7 (no large trees under primary wires); UF fact sheets | Only where a source states it |

### Merge rules
- **Specificity:** species and cultivar evidence beats genus or size-class evidence.
- **Risk fields** (allergy, BVOC, root damage): among equally specific sources, keep the **highest risk**.
- **Disagreements** are always visible in a `<field>_conflict` column, listing each value with its source ID.

### Verification
- **Taxon names:** all 640 agent rows use exact pool names.
- **URLs:** 147 of 176 cited URLs respond normally. The other 29 are bot-blocks (DOI, Kew, MDPI, Xerces) or rate limits (Internet Archive), not dead links.
- **Values checked against the original documents:**
  - Sweetgum isoprene 15.72–86 (Lancaster survey p. 15) ✓
  - Zelkova roots "usually not a problem" (ST-677) ✓
  - Red maple roots "can lift sidewalks" (ST-41) ✓
- **NIACS:** the pin oak row exists. Its vulnerability symbols could not be machine-read from the PDF, so the agent's reading of those symbols is unverified.

### Caveats
- **Root damage depends more on site than species.** Randrup et al. (2001) and Sydnor et al. (2000) find tree age, soil and rooting volume matter more. Use the root field as a modifier, not a filter.
- **Allergenicity scores** from Cariñanos are based on Mediterranean species. Karlik & Pittenger is written for California.
- **Fact-sheet dates:** the 1993/94 sheets were later revised. Only Ginkgo was checked against its current version.

## Still pending

| Field | Planned source | Blocker |
|---|---|---|
| `crown_spread_allometry_UTD` (DBH → height, crown width vs. age) | USFS Urban Tree Database RDS-2016-0005 (Northeast reference city: Queens) | **Server blocks scripted download. Please download the zip manually** from https://www.fs.usda.gov/rds/archive/catalog/RDS-2016-0005 into `data/species/raw/` |
| `nursery_availability_NY` | NYC Parks contract growers / regional nurseries | Needs outreach |
| Climate rating for 18 taxa (mostly non-native ornamentals) | Not in the NIACS NYC list or the Tree Atlas | No NYC-specific source; congener ratings were deliberately not borrowed |
| BVOC / allergy for *Eucommia*, *Styphnolobium*, *Maackia* | — | No open source found |
