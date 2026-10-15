#!/usr/bin/env python3
"""
Estimate the liquid temperature from the chamber air temperature.

Prior model (not fitted to the curve): while the cooler is off, the air is
warmed mainly by the liquid, following Newton's law

    dT_air/dt = (T_liquid - T_air) / TAU

so the liquid temperature can be read directly from the air temperature and
its slope:

    T_liquid = T_air + TAU * dT_air/dt

- TAU (air <-> liquid exchange time constant) is the only parameter, a prior
  of 3 min.  An error of d_tau changes the estimate by d_tau * slope: near the
  target the slope is ~0.1 C/min, so 1 min of error is only ~0.1 C.
- The slope is a straight-line fit over the last 2 minutes (12 samples), which
  averages out the 0.0625 C sensor steps.
- Only used from 5 min after the cooler switches off: before that the cold
  heat sink still pulls the air down.
- One value per cooler-off period: the median of its per-sample estimates.
  An ongoing off period gives the live estimate.
- Room heat leaking in is ignored, so with a warm room the estimate reads a
  little high.

computer_server.py implements the same procedure in pure Python.

Usage:

    python estimate_liquid_temperature.py temperature.db --brew-id 3
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams["font.sans-serif"] = [
    "PingFang SC",
    "Heiti SC",
    "Arial Unicode MS",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

TAU_MIN = 3.0  # Prior air <-> liquid time constant.
ESTIMATE_FROM_MIN = 5.0  # Skip the first minutes after switch-off.
SLOPE_WINDOW_MIN = 2.0
GAP_SECONDS = 35


def load_temperature(db_path: Path, brew_id: int | None) -> pd.DataFrame:
    query = """
        SELECT received_at, temperature, cooler_on, brew_id
        FROM temperature WHERE sensor_ok = 1 ORDER BY received_at
    """
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(query, conn)
    if brew_id is not None:
        df = df[df["brew_id"] == brew_id]
    if df.empty:
        raise ValueError(f"没有找到 brew_id={brew_id} 的有效温度数据")
    df = df.copy()
    df["received_at"] = pd.to_datetime(df["received_at"], utc=True)
    df["cooler_on"] = df["cooler_on"].astype(bool)
    return df.reset_index(drop=True)


def off_periods(df: pd.DataFrame) -> list[pd.DataFrame]:
    """Cooler-off runs that start right after an ON sample (so the off time is known)."""
    gap = df["received_at"].diff().dt.total_seconds().fillna(0) > GAP_SECONDS
    run_id = (df["cooler_on"].ne(df["cooler_on"].shift()) | gap).cumsum()
    periods = []
    for _, run in df[~df["cooler_on"]].groupby(run_id[~df["cooler_on"]]):
        first = run.index[0]
        if first == 0 or not df.loc[first - 1, "cooler_on"] or gap[first]:
            continue
        run = run.copy()
        run["off_min"] = (run["received_at"] - run["received_at"].iloc[0]).dt.total_seconds() / 60
        run["complete"] = run.index[-1] + 1 < len(df) and bool(df.loc[run.index[-1] + 1, "cooler_on"])
        periods.append(run)
    return periods


def estimate_period(run: pd.DataFrame) -> pd.Series:
    """Per-sample liquid estimate T_air + TAU * slope (NaN before ESTIMATE_FROM_MIN)."""
    t, y = run["off_min"].to_numpy(), run["temperature"].to_numpy()
    out = np.full(len(t), np.nan)
    for k in np.flatnonzero(t >= ESTIMATE_FROM_MIN):
        m = (t > t[k] - SLOPE_WINDOW_MIN) & (t <= t[k])
        slope, intercept = np.polyfit(t[m], y[m], 1)
        out[k] = slope * t[k] + intercept + TAU_MIN * slope
    return pd.Series(out, index=run.index)


def make_plots(df, periods, results, output_dir: Path, label: str) -> None:
    fig, ax = plt.subplots(figsize=(15, 7))
    ax.plot(df["received_at"], df["temperature"], color="#6b7280", linewidth=1, alpha=0.6, label="空气温度")
    for index, (run, est) in enumerate(periods):
        ax.plot(run["received_at"], est, color="tab:orange", linewidth=1, alpha=0.6,
                label="逐点估计" if index == 0 else None)
    res = pd.DataFrame(results)
    ax.plot(res["time"], res["liquid"], color="tab:red", linewidth=2, marker="o", markersize=5,
            label="每次停机的液温估计（中位数）")
    ax.set_title(f"液温估计：T液 = T气 + τ·dT气/dt，τ = {TAU_MIN:g} min（{label}）")
    ax.set_xlabel("时间（UTC）")
    ax.set_ylabel("温度 / °C")
    ax.grid(alpha=0.25)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output_dir / "temperature_estimate_timeline.png", dpi=160)
    plt.close(fig)

    # Consistency check: if the prior model is right, each curve is flat over the off time.
    fig, ax = plt.subplots(figsize=(12, 6))
    colors = plt.cm.viridis(np.linspace(0, 1, len(periods)))
    for color, (run, est) in zip(colors, periods):
        ax.plot(run["off_min"], est, color=color, linewidth=1.5)
    ax.set_title("一致性检查：同一次停机内的逐点估计（模型合理时应接近水平线）")
    ax.set_xlabel("制冷关闭后时间 / min")
    ax.set_ylabel("估计液温 / °C")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "temperature_estimate_cycles.png", dpi=160)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="temperature.db 路径")
    parser.add_argument("--brew-id", type=int, default=None, help="只分析指定 brew_id")
    parser.add_argument("--output-dir", type=Path, default=Path("temperature_estimation_output"),
                        help="图片和 CSV 输出目录")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    df = load_temperature(args.database, args.brew_id)
    periods, results = [], []
    for run in off_periods(df):
        est = estimate_period(run)
        if est.notna().any():
            periods.append((run, est))
            valid = est.dropna()
            results.append({
                "off_start": run["received_at"].iloc[0],
                "time": run.loc[valid.index[-1], "received_at"],
                "off_minutes": run["off_min"].iloc[-1],
                "complete": run["complete"].iloc[0],
                "air_at_end": run["temperature"].iloc[-1],
                "liquid": float(valid.median()),
                "liquid_min": float(valid.min()),
                "liquid_max": float(valid.max()),
            })
    if not results:
        raise SystemExit("没有找到制冷关闭超过 5 分钟的时段")

    res = pd.DataFrame(results)
    res.to_csv(args.output_dir / "temperature_cycle_estimates.csv", index=False)
    make_plots(df, periods, results, args.output_dir, f"brew {args.brew_id}" if args.brew_id else "all brews")
    shown = res.assign(off_start=(res["off_start"] + pd.Timedelta(hours=8)).dt.strftime("%m-%d %H:%M"))
    print(f"T_liquid = T_air + {TAU_MIN:g} * slope（停机 {ESTIMATE_FROM_MIN:g} 分钟后，斜率窗口 {SLOPE_WINDOW_MIN:g} 分钟）；时间为北京时间\n")
    print(shown.drop(columns="time").to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    print(f"\n输出目录: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()