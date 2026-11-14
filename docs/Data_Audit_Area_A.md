# Data Audit: Area A (Mott Haven, Third Ave E 135th to E 139th St)

**Run:** 14 Nov 2026. Scripts are in `scripts/`; raw outputs are in `data/raw/`.
**Areas:**
- **Core:** 250 m buffer around the corridor, **0.478 km²**. bbox −73.9320, 40.8074, −73.9208, 40.8151.
- **Context:** 1 km buffer, **4.26 km²**.
- Boundary files: `data/aoi/`. Endpoints were geocoded with NYC Planning GeoSearch: 2500 3 Ave ≈ E 135th, 2600 3 Ave ≈ E 138th/139th, Graham Triangle (−73.92763, 40.81054).

## 1. Verdict

| Layer group | Status | Notes |
|---|---|---|
| Tree inventory and history | **Ready** | Live records updated Nov 2026, plus 2005 and 2015 censuses |
| Planning / land use / street geometry | **Ready** | Downloaded for the context area |
| Satellite (Landsat, Sentinel-2, ECOSTRESS) | **Ready to download** | Enough clear summer scenes every year from 2019 to 2026 |
| Aerial imagery (city 2024) | **Usable with a caveat** | Captured **14–24 March 2024 (leaf-off)**. Use NAIP 2022 (leaf-on) for canopy |
| LiDAR | **Ready to download** | City 2017 topobathymetric LiDAR (`7sc8-jtbz`, link-out) |
| Soil | **Weak** | SSURGO is almost entirely "Urban land" with no drainage class. Field sampling is needed |
| Weather | **Partial** | Nearest Micronet stations (Bronx `BRON`, Tremont/Van Nest `BXVNST`) are several km away. Historical data access needs a request |
| Air quality | **Ready (coarse)** | NYCCAS neighbourhood indicators for 2019–2024 downloaded. Not street-level |
| Planting space dimensions and overhead wires | **Major gap** | Width/length are recorded for only 3 of 594 spaces and overhead wires for 28. **Street-level imagery must fill this** |

## 2. NYC Open Data (downloaded, context area)

| Dataset (ID) | Updated | Rows citywide | Core | Context | File |
|---|---|---|---|---|---|
| Forestry Tree Points (`hn5i-inap`) | 2026-11-04 | 1,125,266 | 675 | 7,160 | `nyc_opendata/hn5i-inap_*.geojson` |
| Forestry Planting Spaces (`82zj-84is`) | 2026-10-22 | 1,130,942 | 594 | 6,017 | ✓ |
| Forestry Inspections (`4pt5-3vv4`) | 2026-11-05 | 2,071,505 | 1,288 | 13,755 | ✓ |
| Forestry Work Orders (`bdjm-n7q4`) | 2026-11-08 | 1,573,619 | 969 | 10,739 | ✓ |
| Forestry Service Requests (`mu46-p9is`) | 2026-11-09 | 1,155,301 | 279 | 4,036 | ✓ |
| Forestry Risk Assessments (`259a-b6s7`) | 2026-10-28 | 1,574,692 | — | — | No geometry; join by tree ID later |
| 2015 Street Tree Census (`uvpi-gqnh`) | 2017 | 683,788 (Bronx 85,203) | 347 in core polygon | 5,013 (context) | ✓ |
| 2005 Street Tree Census (`29bw-z7pj`) | 2017 | 592,372 | 166 | 1,540 | Counted; not saved (format error, low priority) |
| Building footprints (`5zhs-2jue`) | 2026-11-08 | 1,082,972 | 319 | 2,833 | ✓ |
| Planimetric sidewalks (`52n9-sdep`) | 2024-04-24 | 50,865 | 58 | 365 | ✓ |
| Planimetric curbs (`5xvt-8cbk`) | 2024-04-24 | 217,662 | 230 | 1,890 | ✓ |
| Hydrants (`5bgh-vtsn`) | 2025-12-18 | 109,725 | 123 | 825 | ✓ |
| Bus stop shelters (`t4f2-8md7`) | 2026-10-01 | 3,312 | 4 | 39 | ✓ |
| DEP green infrastructure (`df32-vzax`) | 2026-11-06 | 16,051 | 1 | 36 | ✓ |
| PLUTO tax lots (`64uk-42ks`) | 2026-08-24 | 858,284 (Bronx 89,362) | 482 | 3,714 | ✓ (points; MapPLUTO polygons still to fetch) |
| Heat Vulnerability Index (`4mhf-duep`) | 2024 | 184 ZCTAs | — | — | `hvi_rankings.csv`: **10454 and 10451 = 5 (highest)** |
| NYCCAS / Air Quality & Health (`c3uy-2p5r`) | 2026-06-18 | — | — | — | `nyccas_air_quality_mott_haven.csv` (PM2.5, NO₂, O₃, traffic density, 2019–2024) |

Not yet pulled: 311 records in full (counted only, below), stormwater flood maps (`9i7c-xyvv`, file), land cover 2017 6-inch (`he6d-2qns`), tree canopy change 2010–2017 (`by9k-vhck`), zoning GIS, MapPLUTO polygons.

## 3. What the core area already tells us

- **Trees:** 675 tree records. 539 are standing trees, 118 retired (removed) and 18 stumps.
  - Condition: 118 excellent, 228 good, 215 fair, 15 poor, **86 dead**.
  - **70 species.** The most common are London planetree **17.4%**, pin oak 8.6% and Japanese zelkova 8.1%. London planetree alone breaks the 10% single-species guideline, a real diversification target.
  - Median trunk diameter (DBH) is 7 in, a young stock.
- **Planting spaces:** 594 in total, 509 populated and **85 empty**. The empty spaces are the immediate candidate set. Retired and dead trees add replanting candidates.
- **2015 census (core):** 347 trees. 328 alive (200 good, 92 fair, 36 poor), 13 dead, 6 stumps. **106 trees (32%) had sidewalk damage recorded.** This is a direct label for root–pavement conflict.
- **311 since 2020 (core):**
  - 70 "New Tree Request" (residents asking for trees: demand signal).
  - 68 broken sidewalk, 31 sidewalk violation, 13 collapsed sidewalk.
  - 34 fallen tree or limb, 18 branches hitting buildings.
  - 6 dead/dying trees planted more than 2 years ago (establishment failure).
- **Soil (SSURGO):** "Urban land" on tidal-marsh, outwash or reclaimed substratum, plus small Greenbelt/Flatbush inclusions (well drained, hydrologic group B). **The tidal-marsh substratum matters**: it suggests a high water table or poor drainage in parts of the corridor, to be checked in the field.

## 4. Satellite (search only, June–August, over the core)

| Collection | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|
| Landsat C2 L2, all / ≤20% cloud | 26/14 | 29/10 | 26/10 | 35/10 | 37/11 | 32/10 | 36/13 | 31/17 |
| Sentinel-2 L2A, all / ≤20% cloud | 36/13 | 37/17 | 37/7 | 43/12 | 66/16 | 35/7 | 42/12 | 44/19 |
| ECOSTRESS L2T LSTE granules (cloud not filtered) | 60 | 62 | 58 | 65 | 79 | 49 | 53 | 146 |

- **ECOSTRESS overpass times** (local EDT) spread across the whole day. **36–41 granules fall at 13:00–14:00**, giving real afternoon surface-heat data that Landsat (~10:30) cannot provide.
- **NAIP** (Planetary Computer) years over the core: 2011, 2013, 2015, 2017, 2019, 2021, 2022. The latest (2022) is 0.6 m with NIR, and is the leaf-on canopy source.
- **City orthoimagery:** 2024, 6-inch, colour-infrared yes, but **leaf-off (March)**. It is delivered as WMTS tiles; a raw raster download route needs confirming.

## 5. Weather stations

- **NWS/ASOS:** Central Park (KNYC) and LaGuardia (KLGA) are nearest. Free via the NWS API and NOAA ISD.
- **NYS Mesonet NYC Micronet:** Bronx stations `BRON` and `BXVNST` exist, but neither is inside Area A. A data request to the Mesonet is required for 5-minute archives, including solar radiation, which SOLWEIG needs.
- **Conclusion:** our own loggers in the corridor (field campaign, summer 2027) are necessary, not optional.

## 6. Actions only you can take (accounts and requests)

| # | Action | Why |
|---|---|---|
| 1 | Create a free **NASA Earthdata** login | Download ECOSTRESS (and HLS) granules |
| 2 | Create a **Mapillary** account and developer token | Street-level images to fill planting-space width and **overhead wire** gaps (95% missing) |
| 3 | Submit an **NYS Mesonet data request** (research use) for `BRON`, `BXVNST`, Jun–Aug 2019–2026 | Weather forcing (including solar radiation) for SOLWEIG |
| 4 | Optional: Google Earth Engine or Planetary Computer account | Faster Landsat/Sentinel processing (Planetary Computer search already works without an account) |

## 7a. Rasters downloaded (14 Nov 2026)

All rasters are in EPSG:32618 (UTM 18N) and cover the 4.26 km² context area.

| Product | File(s) | Details |
|---|---|---|
| **LiDAR 2017** (USGS 3DEP EPT `NY_NewYorkCity`, public AWS) | `lidar/dsm_1m.tif`, `dtm_1m.tif`, `chm_1m.tif`, `bldg_1m.tif`, `canopy_mask_1m.tif`, `density_1m.tif` | 990 octree nodes, 229 MB of LAZ, **5.4 pts/m²**, 2.7% empty 1 m cells |
| **NAIP** (4-band, 0.6 m) | `naip/naip_2023_context.tif`, `lidar/ndvi_naip_1m.tif` | Mosaic: 2023-08-20 (15%) + 2022-07-19 (85%), both leaf-on. 100% coverage |
| **Landsat 8/9 LST** (°C, cloud-masked, 30 m) | `landsat_lst/*.tif`, `landsat_lst_scenes.csv` | 77 summer scenes 2019–2026 (46 L8, 31 L9). Scenes >80% clear over context: 6, 3, 5, 6, 6, 10, 11, 12 per year |
| **Sentinel-2 L2A** (B02, B03, B04, B08, B11, SCL; 10 m) | `sentinel2/*.tif`, `sentinel2_scenes.csv` | **105 summer scenes 2019–2026, complete.** Scenes >80% clear over context: 11, 14, 7, 12, 14, 7, 12, 17 per year |
| **ECOSTRESS L2T LSTE v002** (°C, cloud-masked, 70 m) | `ecostress/*_LST_c.tif`, `ecostress_scenes.csv` | 487 summer granules 2019–2026 (via user's Earthdata token). **158 near-fully clear** over context. **53 clear afternoon (12–16 h EDT) scenes**: 5, 7, 6, 3, 11, 6, 8, 7 per year |

**LiDAR classification problem and fix.** The USGS NYC cloud has **no building class**. Classes 1 and 17 both mix roofs and trees: about 38% of points in each class fall inside building footprints. The first canopy model therefore counted roofs as trees (42% "canopy"). It was rebuilt in `scripts/refine_lidar.py`:
1. Buildings are masked using NYC footprints (+1 m buffer).
2. Height above ground must exceed 2 m.
3. A 3×3 morphological opening removes poles and wires.
4. NAIP NDVI must exceed 0.2.

The refined result: **canopy >2 m covers 9.5% of the core area and 6.1% of the context area** (the context includes the Harlem River and highways). Median canopy height in the core is **12.8 m**, 95th percentile **18.6 m**.

Caveat: the three sources have different dates (LiDAR 2017, NAIP 2022–23, footprints 2026). Validate the canopy against the city's 2017 6-inch land cover tree class before modelling.

## 7. Next data steps (no account needed)

1. Download NAIP 2022 and Landsat/Sentinel-2 summer stacks for the context area (Planetary Computer).
2. Fetch the 2017 LiDAR tiles covering the context area; build DSM, DEM, CHM and sun-hours/sky-view factor.
3. Pull MapPLUTO polygons, zoning, 2017 land cover 6-inch, canopy change 2010–2017 and stormwater flood maps.
4. Join Forestry inspections, work orders and risk assessments to tree points → per-tree history table.
5. Bronx-wide pull of Tree Points + 2015 census for ML training (Area B).
