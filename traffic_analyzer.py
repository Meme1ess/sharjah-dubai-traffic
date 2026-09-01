"""
Temporal analysis orchestration: turns raw Sentinel-1 corridor statistics
(from gee_utils) into a chronologically sorted Pandas DataFrame, a
normalized "Traffic Proxy Index", and a relative activity classification.

Scientific framing
-------------------
Nothing in this module claims to count vehicles. It measures month-over-
month CHANGE in aggregated Sentinel-1 backscatter along a highway corridor
relative to that corridor's own historical distribution. Interpret results
as "Relative Corridor Activity" (a radar anomaly signal), not as ground
truth traffic volume. See the Methodology tab in app.py and README.md for
the full set of confounders (weather, road moisture, acquisition geometry,
infrastructure changes, etc.) that can also move this signal.
"""

from __future__ import annotations

import calendar
import datetime as dt
from typing import List, Optional

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

import config
import gee_utils

DATAFRAME_COLUMNS = [
    "date",
    "corridor",
    "road_code",
    "mean_vv_db",
    "median_vv_db",
    "std_vv_db",
    "mean_vh_db",
    "vv_vh_ratio_db",
    "image_count",
    "window_start",
    "window_end",
    "orbit_direction",
    "buffer_meters",
    "day_of_week",
    "month",
    "status",
]


def _clamp_target_day(year: int, month: int, target_day: int) -> int:
    """Clamp a requested day-of-month to the last valid day of that month.

    Handles cases like target_day=31 in a 30-day month, or Feb 29/30/31 in
    non-leap years, without raising ValueError.
    """
    last_day = calendar.monthrange(year, month)[1]
    return min(max(target_day, 1), last_day)


def _build_month_targets(
    months_back: int, target_day: int, end_date: Optional[dt.date] = None
) -> List[dt.date]:
    """Compute the target date for each of the last `months_back` months.

    Uses dateutil.relativedelta for correct calendar-aware month
    subtraction (NOT `timedelta(days=30*i)`, which drifts because months
    have different lengths). Returned oldest-to-newest.
    """
    anchor = end_date or dt.date.today()
    targets = []
    for i in range(months_back - 1, -1, -1):
        month_anchor = anchor - relativedelta(months=i)
        safe_day = _clamp_target_day(month_anchor.year, month_anchor.month, target_day)
        targets.append(dt.date(month_anchor.year, month_anchor.month, safe_day))
    return targets


def get_monthly_traffic_proxy(
    corridor: dict,
    months_back: int = config.DEFAULT_MONTHS_BACK,
    target_day: int = config.DEFAULT_TARGET_DAY,
    buffer_meters: int = config.DEFAULT_BUFFER_METERS,
    date_tolerance_days: int = config.DEFAULT_DATE_TOLERANCE_DAYS,
    orbit_direction: str = "All",
    end_date: Optional[dt.date] = None,
) -> pd.DataFrame:
    """Build a monthly Sentinel-1 SAR traffic-proxy time series for one corridor.

    For each of the last `months_back` months, this targets `target_day`
    (clamped to a valid day for that month), searches a
    +/- `date_tolerance_days` window around it, and queries Earth Engine for
    aggregated VV/VH backscatter statistics over the corridor buffer.

    Months with no available Sentinel-1 imagery do NOT crash the analysis:
    they are recorded with status='no_data' and NaN metric values.

    Args:
        corridor: Corridor dict (see corridors.get_corridor()).
        months_back: Number of months of history to analyze (3-24 typical).
        target_day: Preferred day-of-month to center each search window on.
        buffer_meters: Corridor buffer width in meters (overrides the
            corridor's own default for this run).
        date_tolerance_days: +/- days around the target date to search.
        orbit_direction: 'All', 'Ascending', or 'Descending'. Mixing orbit
            geometries can introduce acquisition-angle artifacts into the
            comparison; prefer a single orbit direction for the most
            scientifically consistent time series.
        end_date: Optional override for "today" (mainly for testing).

    Returns:
        A pandas DataFrame sorted chronologically with one row per month,
        matching DATAFRAME_COLUMNS.
    """
    geometry = gee_utils.build_corridor_buffer(corridor, buffer_meters)
    targets = _build_month_targets(months_back, target_day, end_date)

    rows = []
    for target in targets:
        window_start = (target - dt.timedelta(days=date_tolerance_days)).strftime("%Y-%m-%d")
        # Earth Engine filterDate() end bound is exclusive, so add one day
        # to make the tolerance window inclusive of the end date.
        window_end = (
            target + dt.timedelta(days=date_tolerance_days + 1)
        ).strftime("%Y-%m-%d")

        stats = gee_utils.compute_s1_corridor_stats(
            geometry=geometry,
            start_date=window_start,
            end_date=window_end,
            orbit_direction=orbit_direction,
        )

        rows.append(
            {
                "date": target.strftime("%Y-%m-%d"),
                "corridor": corridor["name"],
                "road_code": corridor["road_code"],
                "mean_vv_db": stats["mean_vv_db"],
                "median_vv_db": stats["median_vv_db"],
                "std_vv_db": stats["std_vv_db"],
                "mean_vh_db": stats["mean_vh_db"],
                "vv_vh_ratio_db": stats["vv_vh_ratio_db"],
                "image_count": stats["image_count"],
                "window_start": stats.get("window_start") or window_start,
                "window_end": stats.get("window_end") or window_end,
                "orbit_direction": orbit_direction,
                "buffer_meters": buffer_meters,
                "day_of_week": target.strftime("%A"),
                "month": target.strftime("%Y-%m"),
                "status": stats["status"],
            }
        )

    df = pd.DataFrame(rows, columns=DATAFRAME_COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df = compute_traffic_proxy_index(df)
    return df


def compute_traffic_proxy_index(df: pd.DataFrame) -> pd.DataFrame:
    """Add normalized proxy-index, change, and classification columns.

    Adds:
        historical_z_score: z-score of mean_vv_db relative to this
            corridor run's own historical mean/std (the "Traffic Proxy
            Index"). NaN-safe: months with missing data do not corrupt the
            baseline statistics.
        pct_deviation: percentage deviation of mean_vv_db from the
            full-period average.
        rolling_3m_mean: 3-month rolling mean of mean_vv_db (min_periods=1).
        monthly_change_db: change in mean_vv_db from the previous available
            month (dB difference, i.e. linear ratio in log form).
        monthly_change_pct: same change expressed as a percentage of the
            previous month's value.
        relative_activity: categorical label derived from historical_z_score
            (see config.ACTIVITY_Z_THRESHOLDS). Labeled "Relative Corridor
            Activity" in the UI, not an exact traffic level.

    This function operates on already-fetched values only — it performs no
    Earth Engine calls, so it is safe to re-run cheaply (e.g. after the user
    tweaks a chart option) without hitting the API again.
    """
    out = df.copy()
    valid = out["mean_vv_db"].replace([np.inf, -np.inf], np.nan)

    baseline_mean = valid.mean(skipna=True)
    baseline_std = valid.std(skipna=True)

    if pd.isna(baseline_std) or baseline_std == 0:
        out["historical_z_score"] = np.nan
    else:
        out["historical_z_score"] = (valid - baseline_mean) / baseline_std

    if pd.isna(baseline_mean) or baseline_mean == 0:
        out["pct_deviation"] = np.nan
    else:
        out["pct_deviation"] = (valid - baseline_mean) / abs(baseline_mean) * 100.0

    out["rolling_3m_mean"] = valid.rolling(window=3, min_periods=1).mean()

    prev = valid.shift(1)
    out["monthly_change_db"] = valid - prev
    safe_prev = prev.replace(0, np.nan)
    out["monthly_change_pct"] = (valid - prev) / safe_prev.abs() * 100.0

    out["relative_activity"] = out["historical_z_score"].apply(classify_activity)

    return out


def classify_activity(z_score: float) -> str:
    """Classify a z-score into a "Relative Corridor Activity" bucket.

    This is explicitly a radar-anomaly classification, not a congestion
    level. Thresholds come from config.ACTIVITY_Z_THRESHOLDS.
    """
    if z_score is None or (isinstance(z_score, float) and np.isnan(z_score)):
        return "Unknown"

    t = config.ACTIVITY_Z_THRESHOLDS
    if z_score < t["Very Low"]:
        return "Very Low"
    if z_score < t["Low"]:
        return "Low"
    if z_score < t["Normal"]:
        return "Normal"
    if z_score < t["Elevated"]:
        return "Elevated"
    return "High"


def summarize_latest(df: pd.DataFrame) -> dict:
    """Produce summary-card metrics for the most recent usable observation.

    Falls back gracefully (returns None values) if the entire series is
    missing data, so the UI can render "No data available" instead of
    crashing on an empty DataFrame.
    """
    usable = df[df["status"] == "ok"].copy()
    if usable.empty:
        return {
            "latest_date": None,
            "latest_mean_vv_db": None,
            "historical_avg_vv_db": None,
            "change_from_previous": None,
            "relative_activity": "Unknown",
            "usable_scene_months": 0,
            "total_months": len(df),
        }

    latest = usable.iloc[-1]
    return {
        "latest_date": latest["date"],
        "latest_mean_vv_db": latest["mean_vv_db"],
        "historical_avg_vv_db": usable["mean_vv_db"].mean(),
        "change_from_previous": latest["monthly_change_db"],
        "relative_activity": latest["relative_activity"],
        "usable_scene_months": int(len(usable)),
        "total_months": int(len(df)),
    }


# ---------------------------------------------------------------------------
# Ground-truth integration architecture (future work)
# ---------------------------------------------------------------------------
# The classes below define the abstraction future modules should implement
# to validate the satellite proxy against real traffic measurements (RTA
# sensors, Google/HERE/TomTom traffic speeds, floating-car data, etc.). No
# concrete ground-truth data source is wired in yet — DO NOT fabricate or
# simulate ground-truth values. GroundTruthSource implementations should
# raise NotImplementedError until a real, credentialed data feed is
# connected.


class GroundTruthSource:
    """Abstract interface for a real-world traffic data source.

    Implementations (e.g. RTATrafficSource, HereTrafficSource) should query
    their respective APIs and return a DataFrame with at least the columns
    ['date', 'road_code', 'ground_truth_value']. This lets future work
    statistically test whether the Sentinel-1 proxy correlates with actual
    traffic counts/speeds, without altering the core SAR analysis pipeline.
    """

    name: str = "unimplemented"

    def fetch(self, road_code: str, start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
        raise NotImplementedError(
            f"{self.__class__.__name__} has no live data connection configured. "
            "Implement fetch() against a real ground-truth API before use."
        )


def merge_with_ground_truth(
    proxy_df: pd.DataFrame, ground_truth_df: pd.DataFrame
) -> pd.DataFrame:
    """Left-join satellite proxy features with ground-truth observations.

    Produces a DataFrame suitable as a machine-learning training set once a
    real ground_truth_value column is available (see module docstring).
    Performs no modeling itself — training a correlation/regression model
    without validated ground truth would produce meaningless results.
    """
    merged = proxy_df.merge(
        ground_truth_df,
        left_on=["date", "road_code"],
        right_on=["date", "road_code"],
        how="left",
    )
    return merged
