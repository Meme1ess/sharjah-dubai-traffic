"""
Central configuration for the Sharjah-Dubai Satellite Traffic Density Monitor.

All tunable defaults, dataset identifiers, and app-wide constants live here so
that the rest of the codebase (gee_utils, traffic_analyzer, app) can import a
single source of truth instead of hard-coding values.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Google Earth Engine configuration
# ---------------------------------------------------------------------------
# Some GEE accounts (particularly newer ones created after the Nov 2024
# migration to Cloud-project-based access) require a Cloud project ID to be
# passed to ee.Initialize(project=...). Leave this blank to let the Earth
# Engine Python API fall back to its default behavior.
#
# Configure via (in order of precedence):
#   1. Environment variable EE_PROJECT_ID
#   2. The GEE_PROJECT_ID constant below
GEE_PROJECT_ID: str = os.environ.get("EE_PROJECT_ID", "")

# Key under which a service-account credential JSON may be stored in
# st.secrets for cloud deployments (Streamlit Community Cloud, etc.), where
# there is no local `earthengine authenticate` session to rely on. See
# README.md "Cloud Deployment" section for setup instructions.
GEE_SECRETS_KEY = "gee_service_account"

EARTHENGINE_AUTH_HELP = (
    "Google Earth Engine is not authenticated for this machine.\n\n"
    "Run the following command in a terminal, then reload this app:\n\n"
    "    earthengine authenticate\n\n"
    "If your account requires a Cloud project (Earth Engine's Nov 2024 "
    "access model), also set the EE_PROJECT_ID environment variable, or "
    "edit GEE_PROJECT_ID in config.py, to a valid Google Cloud project "
    "that has the Earth Engine API enabled.\n\n"
    "Deploying to the cloud instead? Add a Earth Engine service-account "
    "key to your app's Secrets under the key 'gee_service_account' — see "
    "README.md for the exact format."
)

# ---------------------------------------------------------------------------
# Earth Engine dataset identifiers
# ---------------------------------------------------------------------------
S1_COLLECTION_ID = "COPERNICUS/S1_GRD"
S2_COLLECTION_ID = "COPERNICUS/S2_SR_HARMONIZED"

# Reserved for future modules (see README "Future Extensions"). Not yet wired
# into the analysis pipeline.
VIIRS_COLLECTION_ID = "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG"
LANDSAT_THERMAL_COLLECTION_ID = "LANDSAT/LC09/C02/T1_L2"

# ---------------------------------------------------------------------------
# Temporal analysis defaults
# ---------------------------------------------------------------------------
DEFAULT_MONTHS_BACK = 6
MIN_MONTHS_BACK = 3
MAX_MONTHS_BACK = 24

DEFAULT_TARGET_DAY = 25
DEFAULT_DATE_TOLERANCE_DAYS = 3
MIN_DATE_TOLERANCE_DAYS = 1
MAX_DATE_TOLERANCE_DAYS = 10

# ---------------------------------------------------------------------------
# Corridor geometry defaults
# ---------------------------------------------------------------------------
DEFAULT_BUFFER_METERS = 100
MIN_BUFFER_METERS = 25
MAX_BUFFER_METERS = 500

# ---------------------------------------------------------------------------
# Sentinel-1 processing parameters
# ---------------------------------------------------------------------------
S1_INSTRUMENT_MODE = "IW"
S1_REDUCE_SCALE_METERS = 10  # native GRD resolution after terrain correction
S1_MAX_PIXELS = 1_000_000_000
ORBIT_DIRECTIONS = ["All", "Ascending", "Descending"]

# ---------------------------------------------------------------------------
# Sentinel-2 optical composite parameters
# ---------------------------------------------------------------------------
S2_CLOUD_PROPERTY = "CLOUDY_PIXEL_PERCENTAGE"
S2_MAX_CLOUD_PERCENT = 30
S2_SEARCH_WINDOW_DAYS = 20  # window searched around the requested date
S2_TRUE_COLOR_BANDS = ["B4", "B3", "B2"]
S2_VIS_PARAMS = {
    "bands": S2_TRUE_COLOR_BANDS,
    "min": 0,
    "max": 2800,
    "gamma": 1.2,
}

# ---------------------------------------------------------------------------
# Trend classification thresholds (z-score based)
# ---------------------------------------------------------------------------
# These bins define "Relative Corridor Activity", NOT a literal congestion
# level. They describe how far the current radar proxy sits from the
# corridor's own historical distribution.
ACTIVITY_Z_THRESHOLDS = {
    "Very Low": -1.5,
    "Low": -0.5,
    "Normal": 0.5,
    "Elevated": 1.5,
    # anything above the "Elevated" threshold is classified "High"
}

# Plain-language ordering and colors for the simplified "Activity Level"
# chart (see app.py render_activity_level_chart). Kept here so the chart's
# color scheme stays consistent everywhere it's used.
ACTIVITY_LEVELS = ["Very Low", "Low", "Normal", "Elevated", "High"]
ACTIVITY_LEVEL_COLORS = {
    "Very Low": "#4da6ff",
    "Low": "#5fd1c0",
    "Normal": "#8bc34a",
    "Elevated": "#f4a300",
    "High": "#e74c3c",
    "Unknown": "#7f8c8d",
}

# Below this absolute dB change, the simplified "Change From Previous Month"
# chart describes the month as "About the same" rather than stronger/weaker,
# so tiny acquisition-noise fluctuations aren't over-narrated as a change.
CHANGE_ABOUT_SAME_THRESHOLD_DB = 0.15

# ---------------------------------------------------------------------------
# Map / UI defaults
# ---------------------------------------------------------------------------
MAP_CENTER = [25.31, 55.37]  # approx. midpoint between Dubai and Sharjah
MAP_ZOOM_START = 11

APP_TITLE = "Sharjah–Dubai Satellite Traffic Monitor"
APP_SUBTITLE = (
    "Remote-sensing traffic proxy using Copernicus Sentinel-1 SAR and "
    "Sentinel-2 imagery"
)

RESOLUTION_NOTICE_TITLE = "Satellite Resolution Notice"
RESOLUTION_NOTICE_BODY = (
    "Open-source Sentinel imagery cannot reliably identify individual "
    "passenger vehicles. This system analyzes road-level satellite "
    "signals to detect relative temporal changes that may correlate with "
    "traffic activity. Values shown are proxy indicators, not vehicle counts."
)

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CSV_EXPORT_FILENAME = "sharjah_dubai_satellite_traffic_proxy.csv"
