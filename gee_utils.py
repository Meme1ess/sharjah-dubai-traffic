"""
Google Earth Engine interaction layer.

This module is the only place in the project that talks to the `ee` Python
package directly for imagery filtering and reduction. It is deliberately
kept separate from Streamlit (app.py) and from the temporal-analysis
orchestration (traffic_analyzer.py) so that:

  * UI code never has to know about ee.Geometry / ee.ImageCollection objects.
  * All server-side reduceRegion() calls happen here, close to the dataset
    quirks (band names, empty collections, null statistics) they need to
    guard against.

All public functions return plain Python types (dict, float, list, bool) or
ee.Image objects intended only for map display (never cached, never sent
through st.cache_data).
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Optional, Tuple

import ee

import config

# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


def initialize_earth_engine(
    project_id: Optional[str] = None,
    service_account_info: Optional[dict] = None,
) -> Tuple[bool, Optional[str]]:
    """Attempt to initialize the Earth Engine Python API.

    This never raises. It returns a (success, error_message) tuple so the
    calling UI can render a clean, actionable message instead of a raw
    traceback when credentials are missing or invalid.

    Supports two credential paths:
      * Local development: relies on credentials cached by running
        `earthengine authenticate` on this machine (standard ee.Initialize()
        / Application Default Credentials resolution).
      * Cloud deployment (e.g. Streamlit Community Cloud): pass
        `service_account_info`, a dict parsed from a GCP service-account
        JSON key (with Earth Engine access granted), typically sourced from
        st.secrets by the caller. No local `earthengine authenticate`
        session is required in this path.

    Args:
        project_id: Optional Google Cloud project ID. Falls back to
            config.GEE_PROJECT_ID, or the service account's own project_id,
            or finally to the ee library's own default resolution.
        service_account_info: Optional service-account key dict (as loaded
            from JSON) for headless/cloud authentication.

    Returns:
        (True, None) on success.
        (False, human_readable_error) on failure.
    """
    resolved_project = project_id or config.GEE_PROJECT_ID or None

    try:
        if service_account_info:
            credentials = ee.ServiceAccountCredentials(
                service_account_info["client_email"],
                key_data=_service_account_json(service_account_info),
            )
            ee.Initialize(
                credentials,
                project=resolved_project or service_account_info.get("project_id"),
            )
        elif resolved_project:
            ee.Initialize(project=resolved_project)
        else:
            ee.Initialize()
        # Cheap call to confirm the session actually works (catches stale
        # or invalid credentials that Initialize() alone won't surface).
        ee.Number(1).getInfo()
        return True, None
    except Exception as exc:  # noqa: BLE001 - we intentionally catch broadly here
        message = str(exc)
        if "credentials" in message.lower() or "not found" in message.lower() or \
                isinstance(exc, ee.EEException) or "Please authorize" in message:
            return False, config.EARTHENGINE_AUTH_HELP
        return False, (
            "Earth Engine failed to initialize with an unexpected error:\n\n"
            f"{message}\n\n{config.EARTHENGINE_AUTH_HELP}"
        )


def _service_account_json(service_account_info: dict) -> str:
    """Serialize a service-account info dict back to the JSON string that
    ee.ServiceAccountCredentials expects for key_data."""
    import json

    return json.dumps(dict(service_account_info))


# ---------------------------------------------------------------------------
# Geometry construction
# ---------------------------------------------------------------------------


def build_corridor_line(corridor: dict) -> ee.Geometry:
    """Build an ee.Geometry.LineString from a corridor's coordinate list."""
    coords = corridor["coordinates"]
    if len(coords) < 2:
        raise ValueError(
            f"Corridor '{corridor.get('road_code')}' needs at least 2 "
            "coordinates to form a LineString."
        )
    return ee.Geometry.LineString(coords)


def build_corridor_buffer(corridor: dict, buffer_meters: Optional[int] = None) -> ee.Geometry:
    """Build a buffered polygon geometry around a corridor's centerline.

    Args:
        corridor: A corridor dict as returned by corridors.get_corridor().
        buffer_meters: Overrides the corridor's default buffer width.
    """
    width = buffer_meters if buffer_meters is not None else corridor.get(
        "buffer_meters", config.DEFAULT_BUFFER_METERS
    )
    line = build_corridor_line(corridor)
    return line.buffer(width)


# ---------------------------------------------------------------------------
# Sentinel-1 SAR traffic proxy
# ---------------------------------------------------------------------------


def _filter_s1_collection(
    geometry: ee.Geometry,
    start_date: str,
    end_date: str,
    orbit_direction: str = "All",
    relative_orbit: Optional[int] = None,
) -> ee.ImageCollection:
    """Build a filtered Sentinel-1 GRD collection for one time window.

    Filters applied:
      * geographic bounds (intersects the corridor buffer)
      * acquisition date range
      * instrumentMode == 'IW' (Interferometric Wide Swath, the standard
        land-imaging mode)
      * contains VV band (VH is optional and checked separately)
      * orbit direction, if a specific one is requested
      * relative orbit number, if provided (reserved for future use to
        pin down a single repeat-pass geometry for maximum comparability)
    """
    collection = (
        ee.ImageCollection(config.S1_COLLECTION_ID)
        .filterBounds(geometry)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.eq("instrumentMode", config.S1_INSTRUMENT_MODE))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
    )

    if orbit_direction and orbit_direction != "All":
        collection = collection.filter(
            ee.Filter.eq("orbitProperties_pass", orbit_direction.upper())
        )

    if relative_orbit is not None:
        collection = collection.filter(
            ee.Filter.eq("relativeOrbitNumber_start", relative_orbit)
        )

    return collection


def compute_s1_corridor_stats(
    geometry: ee.Geometry,
    start_date: str,
    end_date: str,
    orbit_direction: str = "All",
    relative_orbit: Optional[int] = None,
    scale: int = config.S1_REDUCE_SCALE_METERS,
) -> dict:
    """Compute aggregated Sentinel-1 backscatter statistics over a corridor.

    All reduction happens server-side in Earth Engine; only the final
    scalar results cross the client/server boundary via a single getInfo().

    Returns a dict with keys:
        mean_vv_db, median_vv_db, std_vv_db, mean_vh_db, vv_vh_ratio_db,
        image_count, window_start, window_end, has_vh (bool), status

    `status` is one of: 'ok', 'no_data', 'error'. Callers should treat any
    numeric field as potentially NaN when status != 'ok'.
    """
    nan_result = {
        "mean_vv_db": float("nan"),
        "median_vv_db": float("nan"),
        "std_vv_db": float("nan"),
        "mean_vh_db": float("nan"),
        "vv_vh_ratio_db": float("nan"),
        "image_count": 0,
        "window_start": None,
        "window_end": None,
        "has_vh": False,
        "status": "no_data",
    }

    try:
        collection = _filter_s1_collection(
            geometry, start_date, end_date, orbit_direction, relative_orbit
        )
        image_count = collection.size().getInfo()

        if not image_count or image_count == 0:
            return nan_result

        # Determine whether VH is consistently available in this window.
        has_vh = collection.first().bandNames().contains("VH").getInfo()
        bands = ["VV", "VH"] if has_vh else ["VV"]
        collection = collection.select(bands)

        mean_image = collection.mean()
        median_image = collection.median()
        # Temporal standard deviation per pixel, then spatially averaged
        # over the corridor buffer below. This describes how variable the
        # backscatter was across the acquisitions found in the window, not
        # spatial texture within a single scene.
        std_image = collection.reduce(ee.Reducer.stdDev())

        combined = mean_image.rename(
            [f"{b}_mean" for b in bands]
        ).addBands(
            median_image.rename([f"{b}_median" for b in bands])
        ).addBands(
            std_image.rename([f"{b}_std" for b in bands])
        )

        reduced = combined.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=scale,
            maxPixels=config.S1_MAX_PIXELS,
            bestEffort=True,
            tileScale=4,
        )

        dates = collection.aggregate_array("system:time_start").getInfo()

        stats = reduced.getInfo()

        mean_vv = _safe_float(stats.get("VV_mean"))
        median_vv = _safe_float(stats.get("VV_median"))
        std_vv = _safe_float(stats.get("VV_std"))
        mean_vh = _safe_float(stats.get("VH_mean")) if has_vh else float("nan")

        # VV/VH ratio expressed in dB: since both bands are already in dB
        # (log scale), the ratio in linear units equals the *difference*
        # in dB. This is NOT a further log transform of already-log data.
        vv_vh_ratio_db = (
            mean_vv - mean_vh
            if has_vh and not math.isnan(mean_vv) and not math.isnan(mean_vh)
            else float("nan")
        )

        window_start_actual = (
            dt.datetime.utcfromtimestamp(min(dates) / 1000).strftime("%Y-%m-%d")
            if dates
            else None
        )
        window_end_actual = (
            dt.datetime.utcfromtimestamp(max(dates) / 1000).strftime("%Y-%m-%d")
            if dates
            else None
        )

        return {
            "mean_vv_db": mean_vv,
            "median_vv_db": median_vv,
            "std_vv_db": std_vv,
            "mean_vh_db": mean_vh,
            "vv_vh_ratio_db": vv_vh_ratio_db,
            "image_count": int(image_count),
            "window_start": window_start_actual,
            "window_end": window_end_actual,
            "has_vh": has_vh,
            "status": "ok",
        }

    except ee.EEException as exc:
        result = dict(nan_result)
        result["status"] = "error"
        result["error_message"] = str(exc)
        return result
    except Exception as exc:  # noqa: BLE001
        result = dict(nan_result)
        result["status"] = "error"
        result["error_message"] = str(exc)
        return result


def _safe_float(value) -> float:
    """Coerce an Earth Engine reduceRegion scalar result to float, handling
    None (returned when a region has no valid pixels for a band)."""
    if value is None:
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


# ---------------------------------------------------------------------------
# Sentinel-2 optical composite (visual context only)
# ---------------------------------------------------------------------------


def get_sentinel2_composite(
    geometry: ee.Geometry,
    center_date: str,
    search_window_days: int = config.S2_SEARCH_WINDOW_DAYS,
    max_cloud_percent: float = config.S2_MAX_CLOUD_PERCENT,
) -> Tuple[Optional[ee.Image], dict]:
    """Build a cloud-filtered Sentinel-2 true-color composite near a date.

    Rather than blindly calling `.first()`, this filters by cloud cover,
    sorts by cloudiness, and takes a median composite of the least-cloudy
    scenes within the search window so the result is a reasonable
    representative view of the corridor rather than an arbitrary image.

    Args:
        geometry: Area of interest (typically the corridor buffer, or a
            wider bounding region for basemap context).
        center_date: 'YYYY-MM-DD' date to search around.
        search_window_days: +/- days around center_date to search.
        max_cloud_percent: Maximum CLOUDY_PIXEL_PERCENTAGE to include.

    Returns:
        (image_or_none, metadata) where metadata describes what was found
        (scene_count, date_range, status) so the UI can explain gaps.
    """
    try:
        center = dt.datetime.strptime(center_date, "%Y-%m-%d")
    except ValueError as exc:
        return None, {"status": "error", "error_message": f"Invalid date: {exc}"}

    start = (center - dt.timedelta(days=search_window_days)).strftime("%Y-%m-%d")
    end = (center + dt.timedelta(days=search_window_days)).strftime("%Y-%m-%d")

    try:
        collection = (
            ee.ImageCollection(config.S2_COLLECTION_ID)
            .filterBounds(geometry)
            .filterDate(start, end)
            .filter(ee.Filter.lt(config.S2_CLOUD_PROPERTY, max_cloud_percent))
            .sort(config.S2_CLOUD_PROPERTY)
        )

        count = collection.size().getInfo()
        if not count or count == 0:
            return None, {
                "status": "no_data",
                "scene_count": 0,
                "search_start": start,
                "search_end": end,
            }

        # Median-composite the 5 least-cloudy scenes for a cleaner mosaic.
        best_scenes = collection.limit(5)
        composite = best_scenes.median().clip(geometry)

        return composite, {
            "status": "ok",
            "scene_count": int(count),
            "search_start": start,
            "search_end": end,
        }
    except ee.EEException as exc:
        return None, {"status": "error", "error_message": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return None, {"status": "error", "error_message": str(exc)}


def get_sentinel1_preview_image(
    geometry: ee.Geometry,
    start_date: str,
    end_date: str,
    orbit_direction: str = "All",
) -> Tuple[Optional[ee.Image], dict]:
    """Build a simple mean-VV backscatter image for map overlay purposes.

    Used for the optional radar layer on the interactive map — a visual
    aid only, distinct from the numeric corridor statistics.
    """
    try:
        collection = _filter_s1_collection(geometry, start_date, end_date, orbit_direction)
        count = collection.size().getInfo()
        if not count or count == 0:
            return None, {"status": "no_data", "scene_count": 0}
        image = collection.select("VV").mean().clip(geometry)
        return image, {"status": "ok", "scene_count": int(count)}
    except ee.EEException as exc:
        return None, {"status": "error", "error_message": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return None, {"status": "error", "error_message": str(exc)}


# ---------------------------------------------------------------------------
# Map tile helpers (for folium display)
# ---------------------------------------------------------------------------


def get_map_id(image: ee.Image, vis_params: dict) -> dict:
    """Wrap ee.Image.getMapId so callers don't need to import ee directly.

    Returns the dict produced by ee.Image.getMapId (contains 'tile_fetcher'
    with a url_format usable as a folium TileLayer source). This is the
    standard, dependency-light pattern for putting Earth Engine imagery on a
    folium map without requiring geemap's heavier ipyleaflet/ipywidgets
    stack (not needed for a server-rendered Streamlit map).
    """
    return image.getMapId(vis_params)
