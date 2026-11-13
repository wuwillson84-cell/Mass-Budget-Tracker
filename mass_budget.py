"""
Mass Budget Tracker
-------------------
讀取零件清單 (parts list) 與預算表 (budget)，依 system / zone 加總，
計算 margin，超出預算或 margin 過低時發出警告，並輸出圖表與 Excel 報表。

Usage:
    python mass_budget.py --parts data/parts.csv --budget data/budget.csv --out output
"""
import argparse
import logging
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------- settings
REQUIRED_COLS = ["component", "system", "zone", "mass_kg", "source_type", "confidence"]
VALID_SOURCES = {"estimate", "supplier", "measured"}

# 不確定度 (uncertainty)：依資料來源給一個 ± 百分比，可依專案自行調整
UNCERTAINTY = {"estimate": 0.15, "supplier": 0.05, "measured": 0.01}
CONF_FACTOR = {"low": 1.5, "medium": 1.0, "high": 0.7}  # 信心低 → 放大不確定度

WARN_MARGIN = 0.05  # margin < 5% → WARNING；< 0 → OVER

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
log = logging.getLogger("mass_budget")


# ---------------------------------------------------------------- 1. load
def load_parts(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path) if path.suffix in (".xlsx", ".xls") else pd.read_csv(path)
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    missing = set(REQUIRED_COLS) - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    for col in ["system", "zone", "source_type", "confidence"]:
        df[col] = df[col].astype(str).str.strip()
    df["source_type"] = df["source_type"].str.lower()
    df["confidence"] = df["confidence"].str.lower()
    df["mass_kg"] = pd.to_numeric(df["mass_kg"], errors="coerce")

    # data validation 資料檢查
    bad_mass = df["mass_kg"].isna() | (df["mass_kg"] < 0)
    if bad_mass.any():
        log.warning("Invalid mass for: %s", df.loc[bad_mass, "component"].tolist())
    bad_src = ~df["source_type"].isin(VALID_SOURCES)
    if bad_src.any():
        log.warning("Unknown source_type for: %s", df.loc[bad_src, "component"].tolist())
    dup = df["component"].duplicated(keep=False)
    if dup.any():
        log.warning("Duplicate components: %s", df.loc[dup, "component"].unique().tolist())

    df = df[~bad_mass].copy()

    # uncertainty → upper-bound mass (worst case)
    unc = df["source_type"].map(UNCERTAINTY).fillna(0.20) * df["confidence"].map(CONF_FACTOR).fillna(1.0)
    df["uncertainty_kg"] = df["mass_kg"] * unc
    df["mass_max_kg"] = df["mass_kg"] + df["uncertainty_kg"]
    return df


def load_budget(path: Path) -> pd.DataFrame:
    b = pd.read_excel(path) if path.suffix in (".xlsx", ".xls") else pd.read_csv(path)
    b.columns = b.columns.str.strip().str.lower()
    b["level"] = b["level"].str.strip().str.lower()
    b["name"] = b["name"].str.strip()
    return b


# ---------------------------------------------------------------- 2. aggregate + compare
def compare(parts: pd.DataFrame, budget: pd.DataFrame, level: str) -> pd.DataFrame:
    actual = (
        parts.groupby(level)
        .agg(actual_kg=("mass_kg", "sum"),
             max_kg=("mass_max_kg", "sum"),
             n_parts=("component", "count"),
             measured_share=("source_type", lambda s: (s == "measured").mean()))
    )
    bud = budget.loc[budget["level"] == level].set_index("name")["budget_kg"]
    res = actual.join(bud, how="outer")  # outer: 找出沒有預算或沒有零件的項目

    for name in res.index[res["budget_kg"].isna()]:
        log.warning("[%s] '%s' has parts but NO budget", level, name)
    for name in res.index[res["actual_kg"].isna()]:
        log.warning("[%s] '%s' has budget but NO parts", level, name)

    res["actual_kg"] = res["actual_kg"].fillna(0)
    res["margin_kg"] = res["budget_kg"] - res["actual_kg"]
    res["margin_pct"] = res["margin_kg"] / res["budget_kg"]
    res["worst_margin_kg"] = res["budget_kg"] - res["max_kg"]

    def status(r):
        if pd.isna(r.budget_kg):
            return "NO BUDGET"
        if r.margin_kg < 0:
            return "OVER"
        if r.margin_pct < WARN_MARGIN or r.worst_margin_kg < 0:
            return "WARNING"
        return "OK"

    res["status"] = res.apply(status, axis=1)
    res.index.name = level
    return res.round(3)


def report_warnings(res: pd.DataFrame, level: str) -> None:
    for name, r in res.iterrows():
        if r.status == "OVER":
            log.error("[%s] %s OVER budget by %.1f kg (%.1f%%)",
                      level, name, -r.margin_kg, -100 * r.margin_pct)
        elif r.status == "WARNING":
            log.warning("[%s] %s low margin: %.1f kg (%.1f%%), worst case %.1f kg",
                        level, name, r.margin_kg, 100 * r.margin_pct, r.worst_margin_kg)


# ---------------------------------------------------------------- 3. plots
COLORS = {"OK": "#2a9d8f", "WARNING": "#e9c46a", "OVER": "#e76f51", "NO BUDGET": "#999999"}


def plot_budget_vs_actual(res: pd.DataFrame, level: str, out: Path) -> None:
    res = res.sort_values("budget_kg", ascending=False)
    x = range(len(res))
    w = 0.38
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar([i - w / 2 for i in x], res["budget_kg"], w, label="Budget", color="#cfd8dc")
    bars = ax.bar([i + w / 2 for i in x], res["actual_kg"], w,
                  color=[COLORS[s] for s in res["status"]], label="Actual")
    # error bar = uncertainty (worst case)
    ax.errorbar([i + w / 2 for i in x], res["actual_kg"],
                yerr=[[0] * len(res), (res["max_kg"] - res["actual_kg"]).fillna(0)],
                fmt="none", ecolor="black", capsize=4, lw=1)
    for b, m, top in zip(bars, res["margin_pct"], res["max_kg"].fillna(0)):
        if pd.notna(m):
            ax.annotate(f"{m:+.1%}", (b.get_x() + b.get_width() / 2, max(top, b.get_height())),
                        xytext=(0, 4), textcoords="offset points", ha="center", fontsize=9)
    ax.set_xticks(list(x), res.index)
    ax.set_ylabel("Mass [kg]")
    ax.set_title(f"Budget vs. Actual by {level}  (label = margin, whisker = uncertainty)")
    handles = [plt.Rectangle((0, 0), 1, 1, color="#cfd8dc")] + \
              [plt.Rectangle((0, 0), 1, 1, color=c) for c in ["#2a9d8f", "#e9c46a", "#e76f51"]]
    ax.legend(handles, ["Budget", "Actual – OK", "Actual – WARNING", "Actual – OVER"], frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / f"budget_vs_actual_{level}.png", dpi=150)
    plt.close(fig)


def plot_source_maturity(parts: pd.DataFrame, out: Path) -> None:
    """各系統的質量來源組成 (estimate / supplier / measured) — 顯示資料成熟度。"""
    pivot = parts.pivot_table(index="system", columns="source_type", values="mass_kg",
                              aggfunc="sum", fill_value=0)
    pivot = pivot.reindex(columns=["measured", "supplier", "estimate"], fill_value=0)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    pivot.plot(kind="barh", stacked=True, ax=ax,
               color=["#264653", "#2a9d8f", "#e9c46a"], width=0.6)
    ax.set_xlabel("Mass [kg]")
    ax.set_ylabel("")
    ax.set_title("Mass by source type (data maturity)")
    ax.legend(frameon=False, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "source_maturity.png", dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Mass Budget Tracker")
    ap.add_argument("--parts", default="data/parts.csv", type=Path)
    ap.add_argument("--budget", default="data/budget.csv", type=Path)
    ap.add_argument("--out", default="output", type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    parts = load_parts(args.parts)
    budget = load_budget(args.budget)

    results = {}
    for level in ["system", "zone"]:
        res = compare(parts, budget, level)
        report_warnings(res, level)
        plot_budget_vs_actual(res, level, args.out)
        results[level] = res
        print(f"\n=== by {level} ===")
        print(res[["budget_kg", "actual_kg", "margin_kg", "margin_pct", "status"]].to_string())

    plot_source_maturity(parts, args.out)

    total_actual = parts["mass_kg"].sum()
    total_budget = budget.loc[budget["level"] == "system", "budget_kg"].sum()
    print(f"\nTOTAL: {total_actual:.1f} kg / budget {total_budget:.1f} kg "
          f"→ margin {total_budget - total_actual:+.1f} kg")

    with pd.ExcelWriter(args.out / "mass_report.xlsx") as xw:
        parts.to_excel(xw, sheet_name="parts", index=False)
        for level, res in results.items():
            res.to_excel(xw, sheet_name=f"by_{level}")
    log.info("Report + charts written to %s/", args.out)


if __name__ == "__main__":
    main()
