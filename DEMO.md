# How to Show the Trial (5–10 minutes)

## Ways to show it

| Audience | Best way |
|---|---|
| Someone with a Claude account | Share the planner page from its **Share** menu in Claude, so they can use the "Ask about this plan" box too |
| Anyone else | Send this GitHub repository; the README tells the story with figures |
| A live meeting | Run the interface locally and share your screen (below) |

Run locally:
```bash
python -m http.server 8765 --directory interface
```
Open <http://localhost:8765>.

## Suggested walkthrough

1. **The question (30 s).** "Which tree should go where, to cool streets and still survive?" Point at the README's first image.
2. **The heat map (1 min).** On the planner map, yellow is about 70 °C radiant heat on the sidewalk; purple is shade. Existing trees cut it from 60 °C to 45 °C.
3. **A single site (1 min).** Click a large ringed marker on Lincoln Avenue or Third Avenue (or open `#site-19`). Show the species, the cooling at 10 and 20 years, the 5-year failure risk, and the red "verify wires" check.
4. **Compare plans (2 min).** Switch between *Balanced*, *Maximum cooling* and *Rule: biggest tree that fits*. The table shows the trade-off: about the same cooling, but much lower allergy/ozone risk and twice the ecological value.
5. **Soil budget (1 min).** Change expanded soil from 0 → 30 → 60. The first 30 installations add the most cooling.
6. **Ask a question (1 min, inside Claude).** Use a ready-made question, such as "Which sites need a wire check before planting?"
7. **Honesty slide (1 min).** Scroll to "What these numbers can and cannot tell you". It is a pilot: crown sizes are assumptions, survival is a proxy, and field checks are needed.

## Three numbers to remember

- **−4.8 °C**: typical local cooling of sidewalk radiant heat from one new tree after 20 years (up to −13 °C at the best sites).
- **0.78 AUC**: survival model accuracy on unseen neighbourhoods; site conditions matter more than species.
- **~95% cooling, −29% risk, 2× ecology**: the balanced plan versus "plant the biggest tree that fits".
