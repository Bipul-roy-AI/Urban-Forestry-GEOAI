# Planting Optimiser (Module 5)

**Built:** 15 Nov 2026. **Scripts:** `optimise_planting.py [K] [generations]`, `plot_plan.py [plan] [K]`
**Outputs:**
- `data/processed/optimiser/plan_<name>_K<K>.csv`: one row per site, with species, soil expansion, risk, cooling and flags
- `pareto_K<K>.csv`
- `outputs/optimiser_summary_K<K>.json`
- Map: `outputs/plan_balanced_K30.png`

## Problem

For the **121 candidate planting spaces** in the Area A core (empty spaces, removed trees and dead trees), choose:
- **a species** from the 41 NYC-approved species, and
- **whether to install expanded rooting soil** (structural soil or a connected trench), within a budget of **K installations**. Costs are not assumed; K is the budget lever.

The method is NSGA-II (pymoo), 200 plans × 400 generations. The population is seeded with the rule-based plans, so the Pareto front can only match or beat them.

| Objective | Definition | Source |
|---|---|---|
| ↑ Cooling | Σ sidewalk m² cooled by more than 10 °C at 20 yr (SOLWEIG) × crown-size factor × (1 − 5-yr failure risk) | Modules 3–4 |
| ↓ Health / air risk | Σ pollen allergenicity + isoprene class (0–3 each; highest of conflicting sources) | Species KB |
| ↑ Ecology | Σ native to NY + pollinator value/3 + climate suitability 2070–2099/2 | Species KB |

| Constraint | Rule |
|---|---|
| Diversity (10-20-30) | After planting, including the 473 existing core trees: each species ≤10%, each genus ≤20% |
| Overhead wires | Known wires (11 sites) → no large species. NYC Parks standards p. 7 |
| Narrow sidewalks | Width under 2.5 m (15 sites) → only species NYC lists for narrow space or small pits, or small trees |
| NYC location notes | Sweetgum only at lawn/park sites ("lawn pits only"). Black gum only at wet sites, using tidal-marsh substratum as a proxy (flagged) |
| Soil budget | Expanded soil ≤ K, and it counts only for large species |
| Coverage | Every candidate site gets a tree |

**Assumptions (flagged):**
- Crown diameter at 20 years: small 5 m, intermediate 6 m, medium 7 m, large 8 m.
- A large species **without** expanded soil is capped at a medium crown (needs 76.5 m³ of soil vs ~5 m³ in a standard 5×10 ft pit).
- Species the survival model never saw use the site's median risk, so they carry no species signal.

## Results

Risk-adjusted cooled sidewalk area at 20 years (m²); risk score lower is better; ecology higher is better.

| Soil budget K | Plan | Cooling | Allergy + isoprene | Ecology | Species |
|---|---|---|---|---|---|
| 30 | Optimiser: max cooling | **3,012** | 330 | 134 | 30 |
| 30 | **Optimiser: balanced (recommended)** | 2,801 | **305** | **176** | 26 |
| 30 | Optimiser: health first | 2,559 | 231 | 143 | 21 |
| 30 | Optimiser: ecology first | 2,508 | 326 | 192 | 25 |
| 30 | Rule: biggest tree that fits | 2,943 | 429 | 90 | 19 |
| 30 | Rule: NYC's commonly planted mix | 2,955 | 426 | 87 | 17 |
| 30 | Random feasible species | 2,190 | 378 | 111 | 39 |
| 0 | Optimiser: max cooling / balanced | 2,631 / 2,531 | 339 / 278 | 139 / 162 | |
| 60 | Optimiser: max cooling / balanced | 3,212 / 2,953 | 348 / 304 | 134 / 169 | |

**Findings:**
1. **On cooling alone, simple rules come close.** "Plant the biggest tree that fits" is within 2–3% of the optimiser. The optimiser's value is in the **trade-offs**: the balanced plan keeps ~95% of the best rule's cooling while cutting allergy/ozone risk by 29% and doubling the ecology score.
2. **Expanded soil has diminishing returns.** For the max-cooling plan, K = 0 → 30 adds 14% cooling, and 30 → 60 adds 7%. The first ~30 installations, on the hottest open frontages, are worth the most.
3. **Spatial pattern:**
   - Large trees with expanded soil go on the hot open frontages (Third Ave, E 137th–E 141st St, Lincoln Ave).
   - Small trees go in already-shaded courtyards near the housing towers.
4. **Balanced K=30 species mix:**
   - silver linden 25, Kentucky coffeetree 16, serviceberry 15, Crimean linden 11, Schubert cherry 8, American hornbeam 7, plus 20 others.
   - Genus shares after planting: Quercus 16.5%, Platanus 16.5% (existing), Tilia 10.3%.

## Field checks the plan requires (flags in the CSV)

| Flag | Count (balanced K=30) | Action |
|---|---|---|
| `flag_verify_wires` | 66 | A large species where wire status is unknown. Confirm no primary overhead wires |
| `flag_verify_wet_site` | 4 | Black gum. Confirm a persistently wet site |
| `flag_untrained_species` | 23 | Failure risk is the site median, with no species evidence (e.g. Crimean linden) |
| All sites | 121 | Utility markout, pit soil test, and confirmation the space is actually plantable |

## Limits

- **Crown sizes and the soil cap are assumptions.** Replace them with USFS Urban Tree Database growth curves when downloaded.
- **Cooling is from one hot day with a generic crown.** Species leaf density and transmissivity are not differentiated.
- **The ecology and health weights are a value judgement.** The tool shows the whole Pareto front (`pareto_K*.csv`) so planners choose the trade-off.
- **Silver linden note:** reports of bee deaths are attributed to late-season starvation (Koch & Stevenson 2017; see the species KB), not nectar toxicity. Mixing in other late-flowering forage is advisable.
- **No costs.** Add NYC Parks/DDC unit costs to turn K into dollars.
