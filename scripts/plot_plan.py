"""Map an optimiser plan over current afternoon Tmrt. Usage: python plot_plan.py [plan_name] [K]"""
import json
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import Affine

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
name = sys.argv[1] if len(sys.argv) > 1 else "balanced"
K = sys.argv[2] if len(sys.argv) > 2 else "30"
plan = pd.read_csv(ROOT / f"data/processed/optimiser/plan_{name}_K{K}.csv")
sites = gpd.read_file(ROOT / "data/processed/sites_area_a.gpkg").to_crs(32618)
g = sites[["ps_id", "geometry"]].merge(plan, on="ps_id")
run = json.loads((ROOT / "data/processed/solweig/_run.json").read_text()); T = Affine(*run["transform"])
fs = sorted((ROOT / "data/processed/solweig/S0_current/tmrt").glob("*.tif"))
tm = np.mean([rasterio.open(f).read(1) for f in fs if int(f.stem[-4:-2]) in (13, 14, 15, 16)], axis=0)
H, W = tm.shape; ext = (T.c, T.c + W, T.f - H, T.f)
fp = gpd.read_file(next((ROOT / "data/raw/nyc_opendata").glob("*building_footprints*.geojson"))).to_crs(32618)
core = gpd.read_file(ROOT / "data/aoi/area_a_core.geojson").to_crs(32618)

fig, ax = plt.subplots(figsize=(11, 10))
im = ax.imshow(tm, extent=ext, cmap="inferno", vmin=35, vmax=72, alpha=0.85)
plt.colorbar(im, ax=ax, fraction=0.035, label="Current Tmrt 13-16 h, 24 Jun 2025 (deg C)")
fp.boundary.plot(ax=ax, color="white", lw=0.2); core.boundary.plot(ax=ax, color="cyan", ls="--", lw=1)
sz = {"small": 30, "intermediate": 45, "medium": 65, "large": 95}
col = {"small": "#9be15d", "intermediate": "#2ecc71", "medium": "#16a085", "large": "#0b6e4f"}
for s, d in g.groupby("size_class"):
    ax.scatter(d.geometry.x, d.geometry.y, s=sz.get(s, 30), c=col.get(s, "grey"), edgecolor="k", lw=0.6, label=f"{s} ({len(d)})", zorder=3)
e = g[g.expanded_soil]
ax.scatter(e.geometry.x, e.geometry.y, s=170, facecolor="none", edgecolor="#00e5ff", lw=1.6, label=f"expanded soil ({len(e)})", zorder=4)
f = g[g.flag_verify_wires | g.flag_verify_wet_site]
ax.scatter(f.geometry.x, f.geometry.y, marker="x", s=40, c="red", label=f"verify on site ({len(f)})", zorder=5)
ax.set_xlim(*core.total_bounds[[0, 2]] + np.array([-60, 60])); ax.set_ylim(*core.total_bounds[[1, 3]] + np.array([-60, 60]))
ax.set_xticks([]); ax.set_yticks([]); ax.legend(loc="lower right", fontsize=8, framealpha=0.9)
ax.set_title(f"Mott Haven pilot: '{name}' planting plan (expanded-soil budget K={K})\n"
             f"{g.species.nunique()} species; marker size = NYC size class")
plt.tight_layout(); out = ROOT / f"outputs/plan_{name}_K{K}.png"; plt.savefig(out, dpi=120); print(out)
