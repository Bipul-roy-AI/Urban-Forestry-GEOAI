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

1. **The question (30 s).** "Which tree should go where, to cool the street, and what must be checked first?"
2. **The heat map (1 min).** Yellow is about 70 °C radiant heat on the sidewalk; purple is shade. Under existing trees the model gives about 45 °C against 62 °C in the open.
3. **A single site (1 min).** Click a large ringed marker (or open `#site-5`). Show the species, the cooling for a 5 m and an 8 m crown, and the list of checks that site still needs.
4. **A deferred site (30 s).** Click a grey square. The city's records disagree there, so the tool refuses to recommend a tree until someone checks.
5. **Compare plans (2 min).** Switch between *Balanced*, *Maximum cooling* and *Rule: biggest tree that fits*. The simple rule ties the optimiser on cooling; the balanced plan gives up some cooling for lower allergy/ozone and higher ecology scores.
6. **Soil cap (30 s).** Change the expanded-soil cap from 0 → 30 → 60. The gain shrinks.
7. **Ask a question (1 min, inside Claude).** For example, "Which sites are deferred, and what needs checking?"
8. **Limits (1 min).** Scroll to "What these numbers can and cannot tell you". It is a simulation study: crown sizes are assumed, the risk score is relative, and nothing has been measured in the field.

## Three numbers to remember

- **−4.8 °C**: median modelled cooling of sidewalk radiant heat next to one new tree with an 8 m crown.
- **87% / −29% / 2×**: the balanced plan keeps 87% of the maximum cooling, with a 29% lower allergy/isoprene index and about double the ecology index.
- **24 of 121**: sites the tool defers because records conflict or ownership is private. Knowing what not to plant yet is part of the result.
