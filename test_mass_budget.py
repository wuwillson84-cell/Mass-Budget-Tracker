import pandas as pd
from mass_budget import compare

def make_parts():
    return pd.DataFrame({
        "component": ["a", "b", "c"],
        "system": ["S1", "S1", "S2"],
        "zone": ["Front", "Rear", "Rear"],
        "mass_kg": [10.0, 5.0, 30.0],
        "mass_max_kg": [11.0, 5.5, 31.0],
        "source_type": ["measured", "estimate", "supplier"],
    })

def make_budget():
    return pd.DataFrame({
        "level": ["system", "system"],
        "name": ["S1", "S2"],
        "budget_kg": [20.0, 25.0],
    })

def test_margin_and_status():
    res = compare(make_parts(), make_budget(), "system")
    assert res.loc["S1", "actual_kg"] == 15.0
    assert res.loc["S1", "margin_kg"] == 5.0
    assert res.loc["S1", "status"] == "OK"
    assert res.loc["S2", "status"] == "OVER"

def test_missing_budget_flagged():
    budget = make_budget().iloc[:1]          # only S1 has a budget
    res = compare(make_parts(), budget, "system")
    assert res.loc["S2", "status"] == "NO BUDGET"
