# Mass Budget Tracker

Tracks component masses against system- and zone-level budgets, computes margins,
flags over-budget items, and plots budget vs. actual.

![Budget vs actual](output/budget_vs_actual_system.png)

## Features
- Reads a parts list from CSV or Excel (`component, system, zone, mass_kg, source_type, confidence`)
- Validates data (missing columns, negative or empty mass, unknown source types, duplicates)
- Aggregates by **system** and **zone** and compares with the budget
- Margin status: `OK` / `WARNING` (< 5 % or worst case over) / `OVER` / `NO BUDGET`
- Uncertainty per source type (estimate ±15 %, supplier ±5 %, measured ±1 %), scaled by confidence, giving a worst-case mass
- Charts (budget vs. actual, data maturity) and an Excel report

## Quick start
```bash
pip install -r requirements.txt
python mass_budget.py --parts data/parts.csv --budget data/budget.csv --out output
pytest -q
```

## Project structure
```
data/            sample parts list and budget
mass_budget.py   main script
tests/           unit tests (pytest)
output/          generated charts and report
```

## Example output
| System | Budget [kg] | Actual [kg] | Margin | Status |
|---|---|---|---|---|
| Powertrain | 150.0 | 153.6 | −2.4 % | OVER |
| Interior | 40.0 | 39.3 | +1.8 % | WARNING |
| Electrical | 20.0 | 18.3 | +8.5 % | WARNING (worst case over) |

## Possible extensions
- Mass growth allowance by design maturity (AIAA S-120)
- Centre of gravity (CG) per zone
- History tracking: mass trend over design iterations
