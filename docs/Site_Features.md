# Site Layer: Feature Dictionary (Module 1)

**Built:** 14 Nov 2026 with `scripts/build_sites.py`
**Outputs:**
- `data/processed/sites_area_a.gpkg` (layer `sites`, EPSG:32618) and `sites_area_a.csv`
- `data/processed/sites_summary.json`
- Check map: `outputs/site_layer_check.png`

**Pipeline:**
1. `make_aoi.py`
2. `audit_*` / `download_*`
3. `refine_lidar.py`
4. `shade_hours.py`
5. `composites.py`
6. `build_sites.py`

## Contents

- **One row per NYC Forestry planting space** in the 4.26 km² context area: **6,017 sites, 594 in the core**.

| Site class | Context | Core | Meaning |
|---|---|---|---|
| `empty` | 987 | 88 | No tree recorded on the space |
| `removed_or_stump` | 286 | 29 | Tree retired or stump |
| `dead_tree` | 77 | 4 | Tree recorded Dead or Critical |
| `living_tree` | 4,667 | 473 | Existing tree, a candidate for retention and care |

- **Candidate pool for new planting in the core: 121 sites** (empty + removed/stump + dead).
  - Their land use is mostly multi-family elevator (31), commercial/office (27) and mixed residential/commercial (26).
  - Their median building-only sun is 9 h on 15 July, and median afternoon surface temperature is 37.8 °C.

## Features

| Group | Column(s) | Source | Notes |
|---|---|---|---|
| ID / location | `ps_id`, `in_core`, `streetname`, `buildingnumber`, `zipcode`, `bbl`, `nta` | Forestry Planting Spaces | `bbl` is missing for 34% of sites |
| Space attributes | `psstatus`, `pssite`, `plantingspaceonstreet`, `jurisdiction`, `treeguard`, `width`, `length`, `overheadutilities` | Planting Spaces | **`width`/`length` 99.9% missing; `overheadutilities` 94% missing** |
| Current tree | `tree_id`, `tree_species`, `tree_dbh_in`, `tree_condition`, `tree_structure`, `tree_created`, `site_class` | Forestry Tree Points (latest per space) | |
| Maintenance history | `wo_n`, `wo_planting_n`, `wo_removal_n`, `planting_attempts_failed`, `wo_sidewalk_damage` (1,048 true), `wo_wire_conflict` (103 true), `wo_recommended_species` (265 sites) | Forestry Work Orders, matched to the **nearest space within 3 m** (the WO planting-space ID is empty here) | 941 sites have no work order |
| Inspections | `insp_n`, `insp_sidewalk_rating_max` | Forestry Inspections (by space ID) | |
| Complaints | `sr_15m_n` | Forestry Service Requests within 15 m | |
| 2015 census | `c15_*` (status, health, sidewalk, root_stone/grate/other, species, dbh, curb_loc), `c15_root_problem`, `c15_dist_m` | 2015 Street Tree Census, nearest ≤3 m | ~49% matched; empty spaces had no tree in 2015 |
| Street geometry | `dist_building_m`, `dist_curb_m`, `dist_hydrant_m`, `dist_bus_shelter_m`, `dist_green_infra_m`, `sidewalk_width_m` | Footprints, planimetric curbs/sidewalks, hydrants, shelters, DEP GI | Sidewalk width = 2 × max distance-to-edge within 6 m: an approximation |
| Sun / shade | `sun_hours_bldg_jul15`, `bldg_shade_hours_13_17`, `shade_total_hours_jul15` (3 m mean) | `shade_hours.py`: ray-cast on 1 m LiDAR, 15 Jul, 08–19 EDT | "bldg" = buildings only (sun available to a new tree); "total" includes 2017 trees |
| 3D context | `canopy_frac_10m`, `canopy_frac_30m`, `building_frac_30m`, `veg_frac_30m`, `impervious_frac_30m_proxy`, `max_obstacle_height_30m`, `canyon_hw_proxy`, `ground_elev_m` | LiDAR 2017 + NAIP 2022/23 NDVI | Impervious = 1 − vegetated fraction (proxy; includes roofs) |
| Heat | `lst_landsat_median_c`, `lst_landsat_p90_c`, `lst_ecostress_pm_median_c` | Landsat 8/9 (77 scenes, ~10:30 EDT); ECOSTRESS 12–16 EDT (129 granules) | **Surface** temperature, 30 m / 70 m: neighbourhood scale, not per tree |
| Greenness | `ndvi_s2_median` | Sentinel-2 summer median (105 scenes) | 10 m |
| Land use | `lot_landuse`, `lot_landuse_name`, `lot_bldgclass`, `lot_zonedist1`, `lot_numfloors`, `lot_yearbuilt`, `lot_unitsres`, `lot_join` | PLUTO by BBL, else nearest lot ≤40 m | 1,096 sites (18%) still unmatched; MapPLUTO polygons would fix this |
| Vulnerability | `hvi` | NYC Heat Vulnerability Index by ZCTA | All core sites = 5 (highest), so no variation inside the core |
| Soil | `soil_musym`, `soil_muname`, `soil_substratum` | SSURGO map units (SDA) | Substratum classes: Flatbush, outwash, Greenbelt, till, reclaimed, tidal marsh (47 sites) |

## Sanity checks (passed)

- Sun position: solar noon ≈ 13:00 EDT at 70.6° altitude on 15 July, as expected for 40.8° N.
- At 13:00–15:00, buildings shade only 5–6% of the context area, which is the shade gap trees must fill.
- Afternoon surface temperature correlates with impervious fraction (r = +0.39) and with canopy within 30 m (r = −0.28).
- Landsat and ECOSTRESS surface temperatures agree (r = 0.74).

## Known gaps → next actions

1. **Overhead wires and pit dimensions** are mostly missing. Fill them from **Mapillary** street imagery (needs your token) or a manual survey of the 121 core candidates.
2. **Canopy validation**: compare `canopy_mask_1m` with the NYC 2017 6-inch land cover tree class.
3. **Land use**: replace the PLUTO point join with MapPLUTO polygons.
4. **Underground utilities and pit soil** are not public. Every recommendation stays "subject to utility markout and pit survey".
5. **Hourly shade for other dates** (June/August) and a sky-view factor, as SOLWEIG inputs.
