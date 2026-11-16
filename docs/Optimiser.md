# Planting Optimiser (Module 5)

**Revised:** 16 Nov 2026, after an external audit and a code review. Earlier numbers are superseded.
**Scripts:** `optimise_planting.py [K] [generations]`, `evaluate_plans.py`, `plot_plan.py [plan] [K]`
**Outputs:**
- `data/processed/optimiser/plan_<name>_K<K>.csv`: one row per site, with action, species, soil, scores and flags
- `pareto_K<K>.csv`, `outputs/optimiser_summary_K<K>.json`
- `outputs/plan_evaluation.csv`: whole-plan simulation results
- Map: `outputs/plan_balanced_K30.png`

## Problem

In the Area A core, **98 planting spaces** have consistent records. The optimiser chooses, for each:
- **a species** from the 41 NYC-approved species, and
- **whether to install expanded rooting soil**, up to a cap of **K installations**. K is a cap, not a quota, and no costs are assumed.

Other sites are not planted:
- **23 sites with conflicting records** → action `defer: verify records`.
- **1 privately owned space** → action `defer: permission`.

The method is NSGA-II (pymoo), 200 plans × 400 generations, seeded with the rule-based plans so the result can only match or beat them.

| Goal (kept separate) | Definition |
|---|---|
| ↑ Cooling | Sidewalk m² cooled by more than 10 °C for an 8 m crown, attributed **without overlap**, scaled by crown area for the size class. An additive estimate used for search only |
| ↓ Health index | Σ pollen allergenicity + isoprene class (0–3 each). A constructed index, not a health outcome |
| ↑ Ecology index | Σ native to NY + pollinator value/3 + climate suitability/2. A constructed index, not measured biodiversity |
| ↓ Condition risk | Mean relative recorded-condition score. Sites or species without a model value are left out and flagged |

Cooling is **not** multiplied by the risk score any more: the two describe different time horizons.

| Constraint | Rule |
|---|---|
| Diversity (10-20-30) | After planting, counting the 473 existing core trees: each species ≤10%, genus ≤20%, **family ≤30%** |
| Taxa already over a limit | They may not gain trees. London planetree (15.6% after planting) is existing only |
| Overhead wires | Known wires (9 sites) → no large species |
| Narrow sidewalks | Under 2.5 m (12 sites) → narrow-space, small-pit or small species only |
| NYC location notes | Sweetgum only at lawn sites; black gum only at wet-proxy sites (flagged) |
| Soil cap | Expanded soil ≤ K; it only counts for large species |

**Assumptions:** crown diameter by size class is small 5 m, intermediate 6 m, medium 7 m, large 8 m. These are assumed sizes, not growth predictions. A large species without expanded soil is capped at the medium crown.

## Results at K = 30 (whole-plan simulation)

Every plan below was re-simulated in SOLWEIG as a whole, with each tree at its own crown size. Cooled area counts each sidewalk square metre once.

| Plan | Cooled sidewalk m² (simulated) | Search estimate m² | Health index ↓ | Ecology index ↑ | Condition risk ↓ | Species | Soil sites |
|---|---|---|---|---|---|---|---|
| Optimiser: max cooling | **2,004** | 1,962 | 348 | 76 | 0.117 | 23 | 30 |
| **Optimiser: balanced** | 1,739 | 1,617 | 249 | 132 | 0.121 | 29 | 23 |
| Optimiser: health first | 1,478 | 1,266 | **184** | 106 | 0.120 | 21 | 8 |
| Optimiser: ecology first | 1,684 | 1,512 | 267 | **157** | 0.165 | 21 | 20 |
| Optimiser: lowest risk | 1,859 | 1,752 | 311 | 84 | **0.064** | 30 | 26 |
| Rule: biggest tree that fits | **2,004** | 1,962 | 351 | 67 | 0.133 | 16 | 30 |
| Rule: NYC's commonly planted mix | 1,989 | 1,929 | 342 | 72 | 0.108 | 15 | 30 |
| Random approved species | 1,588 | 1,406 | 299 | 95 | 0.118 | 38 | 26 |

All plans plant 97 trees and satisfy every constraint. Core sidewalk mean Tmrt is 58.7 °C now and 57.9–58.1 °C under these plans.

**Findings:**
1. **On cooling alone, the optimiser adds nothing.** Its max-cooling plan ties the one-line rule "plant the biggest tree that fits" at 2,004 m². Cooling here depends on crown size, and the rule already maximises that.
2. **The optimiser's value is the trade-off.** The balanced plan keeps **87%** of the maximum cooling while its health index is **29% lower** and its ecology index is about **double** the rule's (132 vs 67). These are index values, not measured outcomes.
3. **The additive estimate is conservative.** It runs 2–14% below the simulated value, because shade also falls on sidewalk assigned to a neighbouring site. Plan rankings by estimate and by simulation agree.
4. **Expanded soil** (max-cooling plan, search estimate): K = 0 → 1,659 m², K = 30 → 1,962 m² (+18%), K = 60 → 2,110 m² (+8% more). Diminishing returns. These follow directly from the assumed crown cap.

**Balanced plan, K = 30:** 44 large, 7 medium, 5 intermediate and 41 small trees. Most planted: serviceberry 12, silver linden 10, Kentucky coffeetree 9, American linden 7, littleleaf linden 6, Schubert cherry 6.

## Field checks the balanced plan still needs

| Flag | Sites | Meaning |
|---|---|---|
| `flag_verify_jurisdiction` | 83 | No ownership on record |
| `flag_verify_wires` | 44 | Large species where wire status is unknown |
| `flag_no_risk_prediction` | 18 | No condition-risk value for the site |
| `flag_untrained_species` | 12 | Species absent from the model's training data |
| `flag_no_sidewalk_benefit` | 7 | No sidewalk nearby to shade; chosen for the other goals |
| `flag_verify_wet_site` | 1 | Black gum: confirm a persistently wet site |
| `flag_trait_unknown` | 1 | Allergy or isoprene class unknown (treated as moderate) |
| Deferred | 24 | 23 conflicting records + 1 private space |

Pit width and length are unrecorded at every site, and underground utilities are not public. Every site needs a markout and a pit and soil survey.

## Limits

- **Crown sizes and the soil cap are assumptions.** Finding 4 is a consequence of them, not evidence about soil.
- **The health and ecology weights are a value judgement.** The full Pareto set is saved so planners can choose a different balance.
- **K is not a cost.** Sites differ in excavation and utility work.
- **Whole-plan simulation was run for K = 30 only.** K = 0 and K = 60 show search estimates.
- **Not yet done:** a mathematical-programming benchmark for the additive problem, and repeated random baselines.
