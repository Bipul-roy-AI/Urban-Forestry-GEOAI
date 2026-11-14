"""Empirical local performance per species in the Bronx, 2015 Street Tree Census (server-side aggregates).

Per species (Bronx):
  all trees   : c15_n, % Good/Poor (of alive), % sidewalk damage, % root problem, mean DBH
  young trees : DBH <= 3 in (recently planted, ~<5 yr): c15y_n, % Good, % Poor
Young-tree health is a cross-sectional establishment proxy, NOT measured survival.
Dead trees and stumps have no species in the 2015 census, so per-species mortality cannot be computed.
Sidewalk damage / root problems rise with tree size: compare species at similar mean DBH.

Why not true survival? (checked 14 Nov 2026)
- 2005 census coordinates are address-geocoded (45% of trees share a point; median 8.6 m from 2015 trees
  in ZIP 10454), so 2005->2015 tree matching is not possible.
- Forestry Tree Points `createddate` is a record date, not a planting date (Norway maple and green ash
  appear as "new"); planting work orders start in 2024 and carry no tree link.
- Trees Count 2025 (tree-level GPS like 2015) will allow real 10-year survival once released.
Output: data/species/bronx_census2015_by_species.csv
"""
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/species"; OUT.mkdir(parents=True, exist_ok=True)


def soql(**p):
    r = requests.get("https://data.cityofnewyork.us/resource/uvpi-gqnh.json", params={"$limit": 50000, **p}, timeout=600)
    r.raise_for_status()
    return pd.DataFrame(r.json())


grp = "spc_latin, status, health, sidewalk, root_stone, root_grate, root_other"
c = soql(**{"$select": f"{grp}, count(*) as n", "$where": "boroname='Bronx'", "$group": grp})
y = soql(**{"$select": "spc_latin, status, health, count(*) as n", "$where": "boroname='Bronx' AND tree_dbh <= 3",
            "$group": "spc_latin, status, health"})
dbh = soql(**{"$select": "spc_latin, avg(tree_dbh) as c15_mean_dbh_in", "$where": "boroname='Bronx' AND status='Alive'", "$group": "spc_latin"})
for d in (c, y):
    d["n"] = d.n.astype(int)
c["root"] = c[["root_stone", "root_grate", "root_other"]].eq("Yes").any(axis=1)


def pct(part, whole):
    return round(100 * part / whole, 1) if whole else None


rows = []
for sp, g in c[c.spc_latin.notna()].groupby("spc_latin"):
    alive = g[g.status == "Alive"]; na = alive.n.sum(); n = g.n.sum()
    gy = y[y.spc_latin == sp]; ny = gy.n.sum(); ay = gy[gy.status == "Alive"]; nay = ay.n.sum()
    rows.append({
        "census_name": sp, "c15_n": n,
        "c15_pct_good": pct(alive.loc[alive.health == "Good", "n"].sum(), na),
        "c15_pct_poor": pct(alive.loc[alive.health == "Poor", "n"].sum(), na),
        "c15_pct_sidewalk_damage": pct(alive.loc[alive.sidewalk == "Damage", "n"].sum(), na),
        "c15_pct_root_problem": pct(alive.loc[alive.root, "n"].sum(), na),
        "c15y_n": ny,
        "c15y_pct_good": pct(ay.loc[ay.health == "Good", "n"].sum(), nay),
        "c15y_pct_poor": pct(ay.loc[ay.health == "Poor", "n"].sum(), nay),
    })
out = pd.DataFrame(rows).merge(dbh.rename(columns={"spc_latin": "census_name"}), on="census_name", how="left")
out["c15_mean_dbh_in"] = pd.to_numeric(out.c15_mean_dbh_in).round(1)
out.to_csv(OUT / "bronx_census2015_by_species.csv", index=False)
print(len(out), "species; Bronx trees", out.c15_n.sum(), "; young trees", out.c15y_n.sum())
print(out[out.c15y_n >= 50].sort_values("c15y_n", ascending=False).to_string(index=False))
