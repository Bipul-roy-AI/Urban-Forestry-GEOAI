"""Module 5: multi-objective species x site x soil optimiser for Area A core candidates (NSGA-II, pymoo).

Revised after the Nov 2026 audit. Usage: python optimise_planting.py [K] [generations]

SITES. Only sites whose records are consistent (plantable_status == "candidate") can receive a tree.
  Sites with conflicting records are exported as action = "defer: verify records"; privately owned spaces as
  "defer: permission". A candidate with no feasible species gets "no plant".
DECISIONS per candidate site: species (41 NYC-approved) and expanded rooting soil yes/no (budget cap K).
OBJECTIVES (four, kept separate; nothing is multiplied together across time horizons):
  cooling    sum of sidewalk m2 cooled > 10 C for an 8 m crown, ATTRIBUTED WITHOUT OVERLAP (each sidewalk pixel
             belongs to its nearest site; see benefits.py), scaled by crown area for the species' size class.
             This is an additive ESTIMATE for search only; shortlisted plans are re-simulated as a whole
             (evaluate_plans.py) and the simulated unique area is the number to report.
  health     sum of pollen-allergenicity + isoprene class (constructed ordinal index, lower is better).
  ecology    sum of native-to-NY + pollinator/3 + climate/2 (constructed index, higher is better).
  condition  mean recorded-condition risk of the chosen species at their sites (lower is better); sites or
             species without a model prediction are excluded from the mean and flagged, never imputed silently.
CONSTRAINTS:
  diversity 10-20-30 after planting, counted over existing living core trees + new trees: species <= 10%,
            genus <= 20%, family <= 30%. Policy for taxa already above a limit: they may not gain trees.
  wires     known overhead wires -> no large species (NYC Parks standards).
  narrow    sidewalk < 2.5 m -> only species NYC lists for narrow space / small pits, or small size class.
  location  Liquidambar only at lawn sites; Nyssa only at wet-proxy sites (flagged).
  soil      expanded soil <= K (a cap, not a quota); it only counts for large species.
ASSUMPTIONS: crown diameter by size class small 5 m, intermediate 6 m, medium 7 m, large 8 m (assumed sizes,
  not age predictions); a large species without expanded soil is capped at the medium crown.
Outputs: data/processed/optimiser/plan_<name>_K<K>.csv, pareto_K<K>.csv, outputs/optimiser_summary_K<K>.json
"""
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.problem import ElementwiseProblem
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM
from pymoo.operators.repair.rounding import RoundingRepair
from pymoo.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/processed/optimiser"; OUT.mkdir(parents=True, exist_ok=True)
K = int(sys.argv[1]) if len(sys.argv) > 1 else 30
GENS = int(sys.argv[2]) if len(sys.argv) > 2 else 400
rng = np.random.default_rng(42)

FAMILY = {"Ginkgo": "Ginkgoaceae", "Quercus": "Fagaceae", "Liquidambar": "Altingiaceae", "Metasequoia": "Cupressaceae",
          "Taxodium": "Cupressaceae", "Tilia": "Malvaceae", "Gymnocladus": "Fabaceae", "Gleditsia": "Fabaceae",
          "Styphnolobium": "Fabaceae", "Maackia": "Fabaceae", "Cercis": "Fabaceae", "Robinia": "Fabaceae", "Zelkova": "Ulmaceae",
          "Ulmus": "Ulmaceae", "Carpinus": "Betulaceae", "Corylus": "Betulaceae", "Ostrya": "Betulaceae", "Betula": "Betulaceae",
          "Nyssa": "Nyssaceae", "Eucommia": "Eucommiaceae", "Koelreuteria": "Sapindaceae", "Acer": "Sapindaceae",
          "Aesculus": "Sapindaceae", "Amelanchier": "Rosaceae", "Malus": "Rosaceae", "Crataegus": "Rosaceae",
          "Prunus": "Rosaceae", "Pyrus": "Rosaceae", "Sorbus": "Rosaceae", "Cornus": "Cornaceae", "Syringa": "Oleaceae",
          "Fraxinus": "Oleaceae", "Platanus": "Platanaceae", "Celtis": "Cannabaceae", "Morus": "Moraceae",
          "Ailanthus": "Simaroubaceae", "Catalpa": "Bignoniaceae", "Liriodendron": "Magnoliaceae", "Magnolia": "Magnoliaceae",
          "Pinus": "Pinaceae", "Picea": "Pinaceae", "Juniperus": "Cupressaceae", "Thuja": "Cupressaceae", "Salix": "Salicaceae",
          "Populus": "Salicaceae", "Cercidiphyllum": "Cercidiphyllaceae", "Parrotia": "Hamamelidaceae", "Halesia": "Styracaceae",
          "Cladrastis": "Fabaceae", "Phellodendron": "Rutaceae", "Paulownia": "Paulowniaceae", "Albizia": "Fabaceae"}
fam = lambda g: FAMILY.get(g, "family of " + g)  # noqa: E731  unknown genus -> its own group (never merged)

# ---------------- data ----------------
sites = gpd.read_file(ROOT / "data/processed/sites_area_a.gpkg")
core_all = sites[sites.in_core.astype(str) == "True"]
cand = core_all[core_all.plantable_status == "candidate"].reset_index(drop=True)
review = core_all[core_all.plantable_status == "review"]
private = (cand.jurisdiction.astype(str) == "Private").values
ben = pd.read_csv(ROOT / "data/processed/area_a_site_benefits.csv").set_index("ps_id")
cand["cool8"] = cand.ps_id.map(ben["cooled_m2_crown8m"]).fillna(0).values
no_sidewalk = cand.ps_id.map(ben["no_sidewalk_benefit"]).fillna(True).astype(bool).values
kb = pd.read_csv(ROOT / "data/species/species_kb.csv")
sp = kb[kb.nyc_approved.astype(str) == "True"].reset_index(drop=True)
S = len(sp); N = len(cand)

risk = pd.read_csv(ROOT / "data/processed/area_a_species_condition_risk.csv")
P = risk.pivot_table(index="ps_id", columns="taxon", values="p_poor")
trained = risk.groupby("taxon").species_in_training.first()
has_pred = cand.ps_id.isin(P.index).values
site_med = P[[c for c in P.columns if trained.get(c, False)]].median(axis=1)
prisk = np.full((N, S), np.nan)
for j, t in enumerate(sp.taxon):
    src = P[t] if (t in P and trained.get(t, False)) else site_med      # untrained species: site median (flagged)
    prisk[:, j] = cand.ps_id.map(src).values                            # NaN where the site has no prediction

ORD = {"none": 0, "none_reported": 0, "low": 1, "low-moderate": 1.5, "moderate": 2, "medium": 2, "high": 3}
size = sp.size_class.values
CROWN_D = {"small": 5.0, "intermediate": 6.0, "medium": 7.0, "large": 8.0}
allergy_known = sp.pollen_allergenicity.notna().values; iso_known = sp.bvoc_isoprene_class.notna().values
allergy = sp.pollen_allergenicity.map(ORD).fillna(2).values            # unknown -> moderate; flagged in the plan
isoprene = sp.bvoc_isoprene_class.map(ORD).fillna(2).values
native = sp.native_NY_region.map({"yes": 1, "cultivar-of-native": 1}).fillna(0).values
pollin = sp.pollinator_value.map(ORD).fillna(0).values
climate = sp.climate_suitability_2070_2099.map({"likely suitable": 1, "uncertain": 0, "likely reduced": -1}).fillna(0).values
narrow_ok = ((sp.loc_narrow_space.astype(str) == "True") | (sp.loc_small_pit_lt3ft.astype(str) == "True") | (sp.size_class == "small")).values
taxon = sp.taxon.values
genus = sp.taxon.str.split().str[0].values
family = np.array([fam(g) for g in genus])
IS_LARGE = size == "large"

wired = ((pd.to_numeric(cand.overheadutilities, errors="coerce") == 1) | (cand.wo_wire_conflict.astype(str) == "True")).values
wire_unknown = (pd.to_numeric(cand.overheadutilities, errors="coerce").isna() & (cand.wo_wire_conflict.astype(str) != "True")).values
narrow = (cand.sidewalk_width_m.fillna(0) < 2.5).values
lawn = (cand.pssite.astype(str) == "Park").values
wet_proxy = (cand.soil_substratum.astype(str) == "tidal marsh").values

feasible = np.ones((N, S), bool)
feasible[wired[:, None] & IS_LARGE[None, :]] = False
feasible[narrow[:, None] & ~narrow_ok[None, :]] = False
for t, ok_sites in [("Liquidambar styraciflua", lawn), ("Nyssa sylvatica", wet_proxy)]:
    feasible[~ok_sites, int(np.where(taxon == t)[0][0])] = False
feasible[private, :] = False                                           # no permission evidence -> defer
plantable = feasible.any(axis=1)

# existing composition (living core trees, incl. critical) for the diversity rule
ex = core_all[core_all.plantable_status == "retain"].tree_species.dropna().str.split(" - ").str[0]
ex_sp = ex.value_counts(); ex_gen = ex.str.split().str[0].value_counts()
ex_fam = ex.str.split().str[0].map(fam).value_counts()
n_exist = len(ex)
# Diversity rule on integer codes (review fix: no pandas inside the search loop)
LEVELS = []
for name, lim, existing, labels in (("species", 0.10, ex_sp, taxon), ("genus", 0.20, ex_gen, genus), ("family", 0.30, ex_fam, family)):
    keys = sorted(set(existing.index) | set(labels))
    code = {k: i for i, k in enumerate(keys)}
    ex_n = np.array([existing.get(k, 0) for k in keys], dtype=float)
    LEVELS.append((name, lim, np.array(keys, dtype=object), np.array([code[l] for l in labels]), ex_n, ex_n / max(n_exist, 1) > lim))

CF = np.array([[(CROWN_D["medium" if (size[j] == "large" and not e) else size[j]] / 8.0) ** 2 for j in range(S)] for e in (0, 1)])
gain = cand.cool8.values[:, None] * np.ones((1, S))


def diversity_violation(j_planted):
    total = n_exist + len(j_planted); v = 0.0; worst = {}
    for name, lim, keys, codes, ex_n, over_before in LEVELS:
        new = np.bincount(codes[j_planted], minlength=len(keys)).astype(float)
        share = (ex_n + new) / total
        v += new[over_before].sum()                                  # already over the limit: may not gain trees
        v += (np.clip(share - lim, 0, None)[~over_before]).sum() * 100
        k = int(np.argmax(share)); worst[name] = (str(keys[k]), round(float(share[k]), 3))
    return v, worst


def evaluate(x):
    s = x[:N].astype(int); e = x[N:].astype(int)
    planted = s > 0; j = s - 1
    e = e * (planted & IS_LARGE[np.clip(j, 0, S - 1)])
    ii = np.where(planted)[0]; jj = j[planted]
    f_cool = -(gain[ii, jj] * CF[e[ii], jj]).sum()
    f_health = (allergy[jj] + isoprene[jj]).sum()
    f_eco = -(native[jj] + pollin[jj] / 3 + climate[jj] / 2).sum()
    r = prisk[ii, jj]; f_risk = float(np.nanmean(r)) if np.isfinite(r).any() else 0.0
    viol = (~feasible[ii, jj]).sum() * 10 + (plantable & ~planted).sum() * 1.0 + max(0, e.sum() - K) * 1.0
    viol += diversity_violation(jj)[0]
    return np.array([f_cool, f_health, f_eco, f_risk]), viol


class Plan(ElementwiseProblem):
    def __init__(self):
        super().__init__(n_var=2 * N, n_obj=4, n_ieq_constr=1, xl=np.zeros(2 * N), xu=np.r_[np.full(N, S), np.ones(N)], vtype=int)

    def _evaluate(self, x, out, *a, **k):
        f, v = evaluate(np.round(x))
        out["F"] = f; out["G"] = [v]


def give_soil(x):
    large_sites = [i for i in np.argsort(-cand.cool8.values) if x[i] > 0 and IS_LARGE[int(x[i]) - 1]][:K]
    x[N + np.array(large_sites, dtype=int)] = 1
    return x


def seed():
    x = np.zeros(2 * N)
    for i in np.where(plantable)[0]:
        x[i] = rng.choice(np.where(feasible[i])[0]) + 1
    return give_soil(x)


def baseline_x(rule):
    x = np.zeros(2 * N)
    common = [int(np.where(taxon == t)[0][0]) for t in ["Gleditsia triacanthos var. inermis", "Quercus palustris", "Zelkova serrata",
                                                           "Tilia cordata", "Ginkgo biloba", "Styphnolobium japonicum"]]
    for i in np.where(plantable)[0]:
        ok_j = np.where(feasible[i])[0]
        if rule == "random":
            x[i] = rng.choice(ok_j) + 1
        elif rule == "largest_feasible":
            big = ok_j[np.argsort([-CROWN_D[size[k]] for k in ok_j], kind="stable")]
            x[i] = big[i % min(len(big), 6)] + 1
        else:
            choice = [k for k in common if feasible[i, k]] or list(ok_j)
            x[i] = choice[i % len(choice)] + 1
    return give_soil(x)


BASE = {b: baseline_x(b) for b in ("random", "largest_feasible", "nyc_common_mix")}
pop0 = np.array([BASE["largest_feasible"], BASE["nyc_common_mix"]] + [seed() for _ in range(198)])
alg = NSGA2(pop_size=200, sampling=pop0, crossover=SBX(prob=0.9, eta=15, vtype=float, repair=RoundingRepair()),
            mutation=PM(eta=20, vtype=float, repair=RoundingRepair()), eliminate_duplicates=True)
res = minimize(Plan(), alg, ("n_gen", GENS), seed=42, verbose=False)
F = np.atleast_2d(res.F); X = np.atleast_2d(res.X)


def describe(x, name):
    s = np.round(x[:N]).astype(int); e = np.round(x[N:]).astype(int); j = np.clip(s - 1, 0, S - 1)
    planted = s > 0
    e = e * (planted & IS_LARGE[j])
    df = cand[["ps_id", "streetname", "buildingnumber", "site_class", "lot_landuse_name", "sidewalk_width_m"]].copy()
    df["action"] = np.where(planted, "plant", np.where(private, "defer: permission (private)", "no plant: no feasible species"))
    df["species"] = np.where(planted, taxon[j], "")
    df["size_class"] = np.where(planted, size[j], "")
    df["expanded_soil"] = e.astype(bool)
    df["condition_risk"] = np.where(planted, prisk[np.arange(N), j], np.nan).round(3)
    df["cooling_potential_m2"] = np.where(planted, gain[np.arange(N), j] * CF[e, j], 0).round(1)
    df["flag_no_risk_prediction"] = planted & ~has_pred
    df["flag_untrained_species"] = planted & ~pd.Series(df.species).map(trained).fillna(False).astype(bool).values
    df["flag_verify_wires"] = planted & wire_unknown & (df.size_class == "large").values
    df["flag_verify_wet_site"] = (df.species == "Nyssa sylvatica").values
    df["flag_trait_unknown"] = planted & ~(allergy_known[j] & iso_known[j])
    df["flag_verify_jurisdiction"] = planted & cand.jurisdiction.isna().values
    df["flag_no_sidewalk_benefit"] = planted & no_sidewalk
    rv = review[["ps_id", "streetname", "buildingnumber", "site_class", "lot_landuse_name", "sidewalk_width_m"]].copy()
    rv["action"] = "defer: verify records"
    pd.concat([df, rv], ignore_index=True).to_csv(OUT / f"plan_{name}_K{K}.csv", index=False)
    f, v = evaluate(np.round(x))
    dv, worst = diversity_violation(j[planted])
    return {"cooling_potential_m2_additive_estimate": round(-f[0], 1), "allergy_isoprene_index": round(f[1], 1),
            "ecology_index": round(-f[2], 1), "mean_condition_risk": round(f[3], 4), "violation": round(v, 3),
            "n_planted": int(planted.sum()), "n_species": int(pd.Series(df.species[planted]).nunique()),
            "n_expanded_soil": int(e.sum()), "max_share_after": worst,
            "flags": {c: int(df[c].sum()) for c in df.columns if c.startswith("flag_")}}


ok = np.array([evaluate(np.round(x))[1] for x in X]) < 1e-9
Fn = (F - F.min(0)) / np.ptp(F, 0).clip(1e-9)
pick = lambda v: int(np.argmin(np.where(ok, v, np.inf)))  # noqa: E731
picks = {"max_cooling": pick(F[:, 0]), "health_first": pick(F[:, 1]), "ecology_first": pick(F[:, 2]),
         "lowest_risk": pick(F[:, 3]), "balanced": pick((Fn ** 2).sum(1))}
summary = {"K_expanded_soil_cap": K, "generations": GENS, "pareto_size": int(len(F)), "feasible_pareto": int(ok.sum()),
           "candidate_sites": N, "plantable_sites": int(plantable.sum()), "deferred_review_sites": int(len(review)),
           "deferred_private_sites": int(private.sum()), "sites_without_risk_prediction": int((~has_pred).sum()),
           "known_wired_sites": int(wired.sum()), "narrow_sites": int(narrow.sum()), "existing_core_trees": int(n_exist),
           "plans": {n: describe(X[i], n) for n, i in picks.items()},
           "baselines": {b: describe(BASE[b], "baseline_" + b) for b in BASE}}
pd.DataFrame(F, columns=["neg_cooling", "allergy_isoprene", "neg_ecology", "condition_risk"]).assign(feasible=ok).to_csv(OUT / f"pareto_K{K}.csv", index=False)
(ROOT / f"outputs/optimiser_summary_K{K}.json").write_text(json.dumps(summary, indent=2, default=str))
print(json.dumps({k: v for k, v in summary.items() if k not in ("plans", "baselines")}, indent=1))
for grp in ("plans", "baselines"):
    for n, d in summary[grp].items():
        print(f"{grp[:-1]:9s} {n:17s} cool={d['cooling_potential_m2_additive_estimate']:7.1f} health={d['allergy_isoprene_index']:6.1f} "
              f"eco={d['ecology_index']:6.1f} risk={d['mean_condition_risk']:.3f} viol={d['violation']:5.2f} nsp={d['n_species']:2d} "
              f"soil={d['n_expanded_soil']:2d} max={d['max_share_after']}")
