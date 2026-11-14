"""Module 5: multi-objective species x site x soil optimiser for Area A core candidates (NSGA-II, pymoo).

DECISIONS per candidate site i (121): species s_i in {0 = do not plant, 1..41 NYC-approved species}
                                       expand_i in {0, 1}: expanded rooting soil (structural soil / connected trench)
OBJECTIVES (all minimised internally):
  f1  -expected cooling  = sum_i cooled_m2_20yr(i) x crown_factor(s,expand) x (1 - p_fail(i,s))
  f2  health/air risk    = sum_i [allergy(s) + isoprene(s)] (0..3 each; KB values, conservative max of sources)
  f3  -ecology           = sum_i [native_NY(s) + pollinator(s)/3 + climate(s)/2]
CONSTRAINTS:
  diversity  after planting (incl. 473 existing core trees): species <= 10%, genus <= 20% (genus already above
             20% may not grow: London planetree is not plantable; Quercus at 19.2% capped at 20%)
  wires      known overhead wires (planting-space record or work-order wire conflict) -> no large species
  narrow     sidewalk width < 2.5 m -> only species NYC lists for narrow space / small pits, or small size class
  soil budget  sum(expand) <= K  (K = number of expanded-soil installations; costs are NOT assumed)
  must plant  every feasible site gets a tree (sites are existing city planting spaces)
ASSUMPTIONS (flagged in outputs):
  crown diameter at 20 yr by NYC size class: small 5 m, intermediate 6 m, medium 7 m, large 8 m;
  a large species without expanded soil is capped at medium crown (7 m) [soil volume 76.5 m3 vs ~5 m3 pit].
  cooling scales with crown area relative to the 8 m SOLWEIG scenario crown.
  sites without a survival-model score use the species' median across scored sites.
Outputs: data/processed/optimiser/plan_<name>.csv, pareto.csv, outputs/optimiser_summary.json, outputs/optimiser_plans.png
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
from pymoo.operators.sampling.rnd import IntegerRandomSampling
from pymoo.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/processed/optimiser"; OUT.mkdir(parents=True, exist_ok=True)
K = int(sys.argv[1]) if len(sys.argv) > 1 else 30          # expanded-soil budget
GENS = int(sys.argv[2]) if len(sys.argv) > 2 else 400
rng = np.random.default_rng(42)

# ---------------- data ----------------
sites = gpd.read_file(ROOT / "data/processed/sites_area_a.gpkg")
cand = sites[(sites.in_core.astype(str) == "True") & (sites.site_class != "living_tree")].reset_index(drop=True)
ben = pd.read_csv(ROOT / "data/processed/area_a_site_benefits.csv").set_index("ps_id")
cand["cool20"] = cand.ps_id.map(ben["cooled_sidewalk_m2_gt10c_S2_plant_20yr"]).fillna(0).values
kb = pd.read_csv(ROOT / "data/species/species_kb.csv")
sp = kb[kb.nyc_approved.astype(str) == "True"].reset_index(drop=True)
S = len(sp); N = len(cand)
risk = pd.read_csv(ROOT / "data/processed/area_a_species_failure_risk.csv")
P = risk.pivot_table(index="ps_id", columns="taxon", values="p_fail_5yr")
trained = risk.groupby("taxon").species_in_training.first()
pfail = np.zeros((N, S))
for j, t in enumerate(sp.taxon):
    med = float(P[t].median()) if t in P else float(P.stack().median())
    col = cand.ps_id.map(P[t]) if t in P else pd.Series(np.nan, index=cand.index)
    pfail[:, j] = col.fillna(med).values
    if not trained.get(t, False):  # untrained species: use site median across trained species (no species signal)
        pfail[:, j] = cand.ps_id.map(P[[c for c in P.columns if trained.get(c, False)]].median(axis=1)).fillna(med).values

ORD = {"none": 0, "none_reported": 0, "low": 1, "low-moderate": 1.5, "moderate": 2, "medium": 2, "high": 3}
size = sp.size_class.values
crown20 = {"small": 5.0, "intermediate": 6.0, "medium": 7.0, "large": 8.0}
allergy = sp.pollen_allergenicity.map(ORD).fillna(2).values           # unknown -> moderate (flagged)
isoprene = sp.bvoc_isoprene_class.map(ORD).fillna(2).values
native = sp.native_NY_region.map({"yes": 1, "cultivar-of-native": 1}).fillna(0).values
pollin = sp.pollinator_value.map(ORD).fillna(0).values
climate = sp.climate_suitability_2070_2099.map({"likely suitable": 1, "uncertain": 0, "likely reduced": -1}).fillna(0).values
narrow_ok = ((sp.loc_narrow_space.astype(str) == "True") | (sp.loc_small_pit_lt3ft.astype(str) == "True") | (sp.size_class == "small")).values
genus = sp.taxon.str.split().str[0].values

wired = ((pd.to_numeric(cand.overheadutilities, errors="coerce") == 1) | (cand.wo_wire_conflict.astype(str) == "True")).values
wire_unknown = (pd.to_numeric(cand.overheadutilities, errors="coerce").isna() & (cand.wo_wire_conflict.astype(str) != "True")).values
narrow = (cand.sidewalk_width_m.fillna(0) < 2.5).values

# existing core composition
core_trees = sites[(sites.in_core.astype(str) == "True") & (sites.site_class == "living_tree")]
ex_sp = core_trees.tree_species.str.split(" - ").str[0].value_counts()
ex_gen = core_trees.tree_species.str.split().str[0].value_counts()
n_exist = len(core_trees)

feasible = np.ones((N, S), bool)
feasible[wired[:, None] & (size == "large")[None, :]] = False
feasible[narrow[:, None] & ~narrow_ok[None, :]] = False
# NYC Parks approved-list location notes (hard rules):
#   Liquidambar styraciflua "lawn pits only" -> park/lawn sites (pssite == 'Park')
#   Nyssa sylvatica "should only be planted in extremely wet sites" -> proxy: SSURGO tidal-marsh substratum (flag: verify wet)
lawn = (cand.pssite.astype(str) == "Park").values
wet_proxy = (cand.soil_substratum.astype(str) == "tidal marsh").values
for t, ok_sites in [("Liquidambar styraciflua", lawn), ("Nyssa sylvatica", wet_proxy)]:
    jx = int(np.where(sp.taxon.values == t)[0][0])
    feasible[~ok_sites, jx] = False


def crown_factor(j, e):
    d = crown20[size[j]]
    if size[j] == "large" and not e:
        d = crown20["medium"]
    return (d / 8.0) ** 2


CF = np.array([[crown_factor(j, e) for j in range(S)] for e in (0, 1)])  # (2, S)
gain = cand.cool20.values[:, None] * (1 - pfail)                          # (N, S) before crown factor


IS_LARGE = (size == "large")


def evaluate(x):
    s = x[:N].astype(int); e = x[N:].astype(int)
    planted = s > 0; j = s - 1
    e = e * (planted & IS_LARGE[np.clip(j, 0, S - 1)])  # expanded soil only counts (and costs) for large species
    f1 = f2 = f3 = 0.0; viol = 0.0
    if planted.any():
        jj = j[planted]; ii = np.where(planted)[0]
        f1 = -(gain[ii, jj] * CF[e[ii], jj]).sum()
        f2 = (allergy[jj] + isoprene[jj]).sum()
        f3 = -(native[jj] + pollin[jj] / 3 + climate[jj] / 2).sum()
        viol += (~feasible[ii, jj]).sum() * 10
    viol += (N - planted.sum()) * 1.0                       # must plant every site
    viol += max(0, e.sum() - K) * 1.0                       # soil budget
    total = n_exist + planted.sum()
    if planted.any():
        sc = pd.Series(sp.taxon.values[j[planted]]).value_counts()
        gc = pd.Series(genus[j[planted]]).value_counts()
        for t, c in sc.items():
            share = (c + ex_sp.get(t, 0)) / total
            viol += max(0, share - 0.10) * 100 if share > 0.10 + 1e-12 else 0
        for g, c in gc.items():
            share = (c + ex_gen.get(g, 0)) / total
            viol += max(0, share - 0.20) * 100
    return np.array([f1, f2, f3]), viol


class Plan(ElementwiseProblem):
    def __init__(self):
        super().__init__(n_var=2 * N, n_obj=3, n_ieq_constr=1, xl=np.zeros(2 * N), xu=np.r_[np.full(N, S), np.ones(N)], vtype=int)

    def _evaluate(self, x, out, *a, **k):
        f, v = evaluate(np.round(x))
        out["F"] = f; out["G"] = [v]


# seed: random feasible species per site, soil expansion on top-K cooling sites
def seed():
    x = np.zeros(2 * N)
    for i in range(N):
        ok = np.where(feasible[i])[0]
        x[i] = rng.choice(ok) + 1 if len(ok) else 0
    x[N + np.argsort(-cand.cool20.values)[:K]] = 1
    return x


def baseline_x(rule):
    x = np.zeros(2 * N)
    for i in range(N):
        ok_j = np.where(feasible[i])[0]
        if rule == "random":
            x[i] = rng.choice(ok_j) + 1
        elif rule == "largest_feasible":       # "plant the biggest tree that fits"
            big = ok_j[np.argsort([-crown20[size[k]] for k in ok_j])]
            x[i] = big[i % min(len(big), 6)] + 1
        elif rule == "nyc_common_mix":        # most-planted approved species in Bronx young trees, round-robin
            common = [t for t in ["Gleditsia triacanthos var. inermis", "Quercus palustris", "Zelkova serrata", "Tilia cordata", "Ginkgo biloba", "Styphnolobium japonicum"]]
            cand_j = [int(np.where(sp.taxon.values == t)[0][0]) for t in common]
            choice = [k for k in cand_j if feasible[i, k]] or list(ok_j)
            x[i] = choice[i % len(choice)] + 1
    # give the K expanded-soil installations to the highest-cooling sites that received a large species
    large_sites = [i for i in np.argsort(-cand.cool20.values) if IS_LARGE[int(x[i]) - 1]][:K]
    x[N + np.array(large_sites, dtype=int)] = 1
    return x



BASE = {b: baseline_x(b) for b in ("random", "largest_feasible", "nyc_common_mix")}
# seed population: the rule-based plans (so the Pareto front can only match or beat them) + random feasible plans
pop0 = np.array([BASE["largest_feasible"], BASE["nyc_common_mix"]] + [seed() for _ in range(198)])
alg = NSGA2(pop_size=200, sampling=pop0, crossover=SBX(prob=0.9, eta=15, vtype=float, repair=RoundingRepair()),
            mutation=PM(eta=20, vtype=float, repair=RoundingRepair()), eliminate_duplicates=True)
res = minimize(Plan(), alg, ("n_gen", GENS), seed=42, verbose=False)
F = np.atleast_2d(res.F); X = np.atleast_2d(res.X)
print(f"Pareto solutions: {len(F)} | K={K} | gens={GENS}")


def describe(x, name):
    s = np.round(x[:N]).astype(int); e = np.round(x[N:]).astype(int); j = s - 1
    e = e * ((s > 0) & IS_LARGE[np.clip(j, 0, S - 1)])
    df = cand[["ps_id", "streetname", "buildingnumber", "site_class", "lot_landuse_name", "sidewalk_width_m"]].copy()
    df["species"] = np.where(s > 0, sp.taxon.values[np.clip(j, 0, S - 1)], "")
    df["size_class"] = np.where(s > 0, size[np.clip(j, 0, S - 1)], "")
    df["expanded_soil"] = e.astype(bool)
    df["p_fail_5yr"] = pfail[np.arange(N), np.clip(j, 0, S - 1)].round(3)
    df["exp_cooled_m2"] = (gain[np.arange(N), np.clip(j, 0, S - 1)] * CF[e, np.clip(j, 0, S - 1)]).round(1)
    df["flag_verify_wires"] = wire_unknown & (df.size_class == "large")
    df["flag_untrained_species"] = ~df.species.map(trained).fillna(False).astype(bool)
    df["flag_verify_wet_site"] = df.species == "Nyssa sylvatica"
    df["flag_untrained_species"] &= df.species != ""
    df.to_csv(OUT / f"plan_{name}_K{K}.csv", index=False)
    f, v = evaluate(np.round(x))
    gen_share = (pd.Series(genus[j[s > 0]]).value_counts().add(ex_gen, fill_value=0) / (n_exist + (s > 0).sum())).sort_values(ascending=False)
    return {"exp_cooled_m2": round(-f[0], 1), "allergy_isoprene_score": round(f[1], 1), "ecology_score": round(-f[2], 1),
            "violation": round(v, 3), "n_species": int(df.species[df.species != ""].nunique()),
            "n_expanded_soil": int(e.sum()), "top_genus_share_after": {k: round(float(v_), 3) for k, v_ in gen_share.head(3).items()},
            "verify_wires_sites": int(df.flag_verify_wires.sum()), "species_mix_top5": df.species.value_counts().head(5).to_dict()}


ok = np.array([evaluate(np.round(x))[1] for x in X]) < 1e-9
Fn = (F - F.min(0)) / np.ptp(F, 0).clip(1e-9)
picks = {"max_cooling": int(np.argmin(np.where(ok, F[:, 0], np.inf))),
         "health_first": int(np.argmin(np.where(ok, F[:, 1], np.inf))),
         "ecology_first": int(np.argmin(np.where(ok, F[:, 2], np.inf))),
         "balanced": int(np.argmin(np.where(ok, (Fn ** 2).sum(1), np.inf)))}
summary = {"K_expanded_soil": K, "generations": GENS, "pareto_size": int(len(F)), "feasible_pareto": int(ok.sum()),
           "sites": N, "known_wired_sites": int(wired.sum()), "narrow_sites": int(narrow.sum()),
           "plans": {n: describe(X[i], n) for n, i in picks.items()}}
pd.DataFrame(F, columns=["neg_cooling", "allergy_isoprene", "neg_ecology"]).assign(feasible=ok).to_csv(OUT / f"pareto_K{K}.csv", index=False)

# ---------------- baselines (same sites, same K, same diversity/feasibility checks) ----------------
summary["baselines"] = {b: describe(BASE[b], "baseline_" + b) for b in BASE}
(ROOT / f"outputs/optimiser_summary_K{K}.json").write_text(json.dumps(summary, indent=2, default=str))
print(json.dumps({k: v for k, v in summary.items() if k not in ("plans", "baselines")}, indent=1))
for grp in ("plans", "baselines"):
    for n, d in summary[grp].items():
        print(f"{grp[:-1]:9s} {n:18s} cool={d['exp_cooled_m2']:7.1f} risk={d['allergy_isoprene_score']:6.1f} eco={d['ecology_score']:6.1f} "
              f"viol={d['violation']:6.2f} nsp={d['n_species']:2d} soil={d['n_expanded_soil']:2d} topgen={d['top_genus_share_after']}")
