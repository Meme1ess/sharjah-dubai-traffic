"""
Sharjah-Dubai Satellite Traffic Density Monitor — Streamlit dashboard.

This module contains ONLY UI/orchestration logic. All Earth Engine calls
live in gee_utils.py, and all temporal analysis/statistics live in
traffic_analyzer.py.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import datetime as dt

import folium
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

import config
import corridors as corridors_module
import gee_utils
import traffic_analyzer

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title=config.APP_TITLE,
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
    .block-container {padding-top: 2rem; padding-bottom: 2rem;}
    .proxy-disclaimer {
        background-color: #1a2634;
        border-left: 4px solid #4da6ff;
        padding: 0.9rem 1.1rem;
        border-radius: 6px;
        margin-bottom: 1rem;
        font-size: 0.92rem;
    }
    .status-ok {color: #2ecc71; font-weight: 600;}
    .status-nodata {color: #e67e22; font-weight: 600;}
    .status-error {color: #e74c3c; font-weight: 600;}
    div[data-testid="stMetricValue"] {font-size: 1.6rem;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Earth Engine session bootstrap
# ---------------------------------------------------------------------------


def _get_service_account_secret() -> dict | None:
    """Look up a GEE service-account key from Streamlit secrets, if present.

    Returns None (never raises) when no secrets.toml / cloud secret is
    configured — this keeps local development working unchanged, since
    local dev relies on `earthengine authenticate` instead.
    """
    try:
        if config.GEE_SECRETS_KEY in st.secrets:
            return dict(st.secrets[config.GEE_SECRETS_KEY])
    except Exception:  # noqa: BLE001 - st.secrets raises if no secrets file exists at all
        return None
    return None


@st.cache_resource(show_spinner="Connecting to Google Earth Engine...")
def _ee_session():
    """Initialize Earth Engine once per Streamlit server process.

    Tries a cloud service-account (from st.secrets) first if configured,
    then falls back to local `earthengine authenticate` credentials. Never
    raises — a failed initialization is rendered as an informative UI
    message instead of a crash.
    """
    service_account_info = _get_service_account_secret()
    return gee_utils.initialize_earth_engine(
        config.GEE_PROJECT_ID, service_account_info=service_account_info
    )


ee_ready, ee_error = _ee_session()


# ---------------------------------------------------------------------------
# Cached analysis wrapper
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner=False, ttl=3600)
def run_corridor_analysis(
    road_code: str,
    months_back: int,
    target_day: int,
    buffer_meters: int,
    date_tolerance_days: int,
    orbit_direction: str,
) -> pd.DataFrame:
    """Cached wrapper around traffic_analyzer.get_monthly_traffic_proxy.

    Only plain, hashable/serializable arguments are passed in (no ee
    objects), and the return value is a plain pandas DataFrame, so this is
    safe to cache with st.cache_data. The corridor geometry itself is
    rebuilt inside get_monthly_traffic_proxy from the road_code lookup.
    """
    corridor = corridors_module.get_corridor(road_code)
    return traffic_analyzer.get_monthly_traffic_proxy(
        corridor=corridor,
        months_back=months_back,
        target_day=target_day,
        buffer_meters=buffer_meters,
        date_tolerance_days=date_tolerance_days,
        orbit_direction=orbit_direction,
    )


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title(config.APP_TITLE)
st.caption(config.APP_SUBTITLE)

st.markdown(
    f"""
    <div class="proxy-disclaimer">
        <strong>⚠️ {config.RESOLUTION_NOTICE_TITLE}</strong><br>
        {config.RESOLUTION_NOTICE_BODY}
    </div>
    """,
    unsafe_allow_html=True,
)

if not ee_ready:
    st.error(
        "**Google Earth Engine is not available.**\n\n"
        f"{ee_error}"
    )
    st.info(
        "The app will continue to load below, but analysis and map tabs "
        "require a working Earth Engine session to function."
    )


# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------

st.sidebar.header("Analysis Parameters")

analysis_mode = st.sidebar.radio(
    "Mode",
    options=["Single Corridor", "Compare Corridors"],
    index=0,
)

available_codes = corridors_module.list_corridor_codes()

if analysis_mode == "Single Corridor":
    selected_codes = [
        st.sidebar.selectbox(
            "Highway Corridor",
            options=available_codes,
            format_func=lambda code: f"{code} — {corridors_module.get_corridor(code)['name']}",
        )
    ]
else:
    selected_codes = st.sidebar.multiselect(
        "Highway Corridors to Compare",
        options=available_codes,
        default=available_codes,
        format_func=lambda code: f"{code} — {corridors_module.get_corridor(code)['name']}",
    )

months_back = st.sidebar.slider(
    "Months of History",
    min_value=config.MIN_MONTHS_BACK,
    max_value=config.MAX_MONTHS_BACK,
    value=config.DEFAULT_MONTHS_BACK,
)

target_day = st.sidebar.slider(
    "Target Day of Month",
    min_value=1,
    max_value=31,
    value=config.DEFAULT_TARGET_DAY,
    help="Preferred day to center each month's search window on. "
    "Automatically clamped for shorter months (e.g. 31 -> 28/29/30).",
)

date_tolerance_days = st.sidebar.slider(
    "Date Tolerance (± days)",
    min_value=config.MIN_DATE_TOLERANCE_DAYS,
    max_value=config.MAX_DATE_TOLERANCE_DAYS,
    value=config.DEFAULT_DATE_TOLERANCE_DAYS,
)

buffer_meters = st.sidebar.slider(
    "Corridor Buffer Width (meters)",
    min_value=config.MIN_BUFFER_METERS,
    max_value=config.MAX_BUFFER_METERS,
    value=config.DEFAULT_BUFFER_METERS,
    step=25,
)

orbit_direction = st.sidebar.selectbox(
    "Sentinel-1 Orbit Direction",
    options=config.ORBIT_DIRECTIONS,
    index=0,
    help="Ascending and descending passes view the corridor from "
    "different look angles. Mixing them can introduce geometry-related "
    "artifacts into the time series — prefer a single direction for the "
    "most internally consistent comparison.",
)

if orbit_direction == "All":
    st.sidebar.caption(
        "⚠️ Combining ascending and descending passes may make month-to-"
        "month comparisons less reliable due to differing radar look "
        "geometry. Select a single orbit direction for stricter "
        "scientific consistency."
    )

run_clicked = st.sidebar.button("🛰️ Run Satellite Analysis", type="primary", use_container_width=True)

st.sidebar.divider()
st.sidebar.caption(
    "Data sources: Copernicus Sentinel-1 (SAR) and Sentinel-2 (optical), "
    "via Google Earth Engine."
)


# ---------------------------------------------------------------------------
# Session state: persist results across tab interactions
# ---------------------------------------------------------------------------

if "results" not in st.session_state:
    st.session_state["results"] = {}  # road_code -> DataFrame
if "last_params" not in st.session_state:
    st.session_state["last_params"] = None

if run_clicked and ee_ready:
    if not selected_codes:
        st.sidebar.warning("Select at least one corridor to analyze.")
    else:
        results = {}
        progress = st.sidebar.progress(0.0, text="Starting analysis...")
        for i, code in enumerate(selected_codes):
            progress.progress(
                i / len(selected_codes), text=f"Analyzing {code}..."
            )
            try:
                df = run_corridor_analysis(
                    road_code=code,
                    months_back=months_back,
                    target_day=target_day,
                    buffer_meters=buffer_meters,
                    date_tolerance_days=date_tolerance_days,
                    orbit_direction=orbit_direction,
                )
                results[code] = df
            except Exception as exc:  # noqa: BLE001
                st.sidebar.error(f"Analysis failed for {code}: {exc}")
        progress.progress(1.0, text="Done.")
        st.session_state["results"] = results
        st.session_state["last_params"] = {
            "months_back": months_back,
            "target_day": target_day,
            "buffer_meters": buffer_meters,
            "date_tolerance_days": date_tolerance_days,
            "orbit_direction": orbit_direction,
            "mode": analysis_mode,
        }
elif run_clicked and not ee_ready:
    st.sidebar.error("Cannot run analysis: Earth Engine is not initialized.")

results: dict = st.session_state["results"]


# ---------------------------------------------------------------------------
# Helper rendering functions
# ---------------------------------------------------------------------------

ACTIVITY_LEVEL_RANK = {level: i + 1 for i, level in enumerate(config.ACTIVITY_LEVELS)}

ACTIVITY_LEVEL_PLAIN_HOVER = {
    "Very Low": "much weaker than usual for this road",
    "Low": "a bit weaker than usual for this road",
    "Normal": "typical for this road",
    "Elevated": "a bit stronger than usual for this road",
    "High": "much stronger than usual for this road",
    "Unknown": "no reliable satellite reading this month",
}


def render_signal_strength_chart(dfs: dict) -> go.Figure:
    """Radar signal strength over time (raw Sentinel-1 mean VV, in dB)."""
    fig = go.Figure()
    for code, df in dfs.items():
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["mean_vv_db"],
                mode="lines+markers",
                name=code,
                connectgaps=False,
                marker=dict(size=8),
                hovertemplate=(
                    "%{x|%b %Y}<br>Signal strength: %{y:.1f} dB<extra>" + code + "</extra>"
                ),
            )
        )
    fig.update_layout(
        xaxis_title="Month",
        yaxis_title="Radar Signal Strength (dB)",
        hovermode="x unified",
        legend_title="Corridor",
        margin=dict(t=30, b=10),
    )
    return fig


def render_activity_level_chart(dfs: dict) -> go.Figure:
    """Plain-language 'Activity Level' chart: Very Low -> High, color coded.

    This is the primary, easy-to-read view of the traffic proxy. It shows
    the same underlying z-score classification as the technical view, but
    as labeled color bands instead of a raw statistical score, so it can be
    read at a glance without knowing what a z-score is.
    """
    fig = go.Figure()
    bar_width = 0.8 if len(dfs) == 1 else None
    for code, df in dfs.items():
        activity = df["relative_activity"].fillna("Unknown")
        ranks = activity.map(ACTIVITY_LEVEL_RANK).fillna(0)
        colors = activity.map(config.ACTIVITY_LEVEL_COLORS).fillna(
            config.ACTIVITY_LEVEL_COLORS["Unknown"]
        )
        plain_text = activity.map(ACTIVITY_LEVEL_PLAIN_HOVER).fillna(
            ACTIVITY_LEVEL_PLAIN_HOVER["Unknown"]
        )
        fig.add_trace(
            go.Bar(
                x=df["date"],
                y=ranks,
                name=code,
                width=bar_width,
                marker_color=colors,
                customdata=list(zip(activity, plain_text)),
                hovertemplate=(
                    "%{x|%b %Y}<br><b>%{customdata[0]}</b><br>"
                    "%{customdata[1]}<extra>" + code + "</extra>"
                ),
            )
        )
    fig.update_layout(
        xaxis_title="Month",
        yaxis=dict(
            title="Activity Level (compared to this road's own history)",
            tickmode="array",
            tickvals=[1, 2, 3, 4, 5],
            ticktext=config.ACTIVITY_LEVELS,
            range=[0, 5.5],
        ),
        barmode="group",
        hovermode="x unified",
        legend_title="Corridor",
        margin=dict(t=30, b=10),
        showlegend=len(dfs) > 1,
    )
    return fig


def render_proxy_index_chart(dfs: dict) -> go.Figure:
    """Technical view: normalized Traffic Proxy Index (z-score) over time.

    Kept available for users who want the underlying statistic behind the
    plain-language Activity Level chart above. Shaded bands mark the same
    Very Low / Low / Normal / Elevated / High cutoffs used there.
    """
    fig = go.Figure()

    band_edges = [
        ("Very Low", -4, config.ACTIVITY_Z_THRESHOLDS["Very Low"]),
        ("Low", config.ACTIVITY_Z_THRESHOLDS["Very Low"], config.ACTIVITY_Z_THRESHOLDS["Low"]),
        ("Normal", config.ACTIVITY_Z_THRESHOLDS["Low"], config.ACTIVITY_Z_THRESHOLDS["Normal"]),
        ("Elevated", config.ACTIVITY_Z_THRESHOLDS["Normal"], config.ACTIVITY_Z_THRESHOLDS["Elevated"]),
        ("High", config.ACTIVITY_Z_THRESHOLDS["Elevated"], 4),
    ]
    for label, y0, y1 in band_edges:
        fig.add_hrect(
            y0=y0,
            y1=y1,
            fillcolor=config.ACTIVITY_LEVEL_COLORS[label],
            opacity=0.10,
            line_width=0,
            annotation_text=label,
            annotation_position="right",
            annotation_font_size=10,
        )

    for code, df in dfs.items():
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["historical_z_score"],
                mode="lines+markers",
                name=code,
                connectgaps=False,
                marker=dict(size=8),
                hovertemplate=(
                    "%{x|%b %Y}<br>z-score: %{y:.2f}<extra>" + code + "</extra>"
                ),
            )
        )
    fig.add_hline(y=0, line_dash="dot", line_color="gray")
    fig.update_layout(
        xaxis_title="Month",
        yaxis_title="Standard deviations from this corridor's historical mean (z-score)",
        hovermode="x unified",
        legend_title="Corridor",
        margin=dict(t=30, b=10),
    )
    return fig


def render_change_chart(dfs: dict) -> go.Figure:
    """Change in radar signal strength from the previous month."""
    fig = go.Figure()
    for code, df in dfs.items():
        colors = [
            "#e74c3c" if v is not None and pd.notna(v) and v < 0 else "#2ecc71"
            for v in df["monthly_change_db"]
        ]
        fig.add_trace(
            go.Bar(
                x=df["date"],
                y=df["monthly_change_db"],
                name=code,
                marker_color=colors if len(dfs) == 1 else None,
                hovertemplate=(
                    "%{x|%b %Y}<br>Change: %{y:+.1f} dB<extra>" + code + "</extra>"
                ),
            )
        )
    fig.update_layout(
        xaxis_title="Month",
        yaxis_title="Signal Change vs. Previous Month (dB)",
        hovermode="x unified",
        legend_title="Corridor",
        barmode="group",
        margin=dict(t=30, b=10),
    )
    return fig


def render_status_badge(status: str) -> str:
    mapping = {
        "ok": '<span class="status-ok">●</span> OK',
        "no_data": '<span class="status-nodata">●</span> No Imagery',
        "error": '<span class="status-error">●</span> Error',
    }
    return mapping.get(status, status)


def build_folium_map(selected_road_codes: list, radar_overlay: bool, s2_date: str) -> folium.Map:
    """Build the interactive corridor map with Sentinel-2 basemap context,
    corridor buffers, and an optional Sentinel-1 radar overlay.

    Earth Engine imagery is added as folium TileLayers built from
    ee.Image.getMapId() (via gee_utils.get_map_id), the standard pattern for
    putting EE imagery on a server-rendered folium map in Streamlit.
    """
    fmap = folium.Map(
        location=config.MAP_CENTER,
        zoom_start=config.MAP_ZOOM_START,
        tiles="CartoDB positron",
        control_scale=True,
    )

    if ee_ready:
        # Build a combined AOI covering all selected corridors for the S2 composite.
        aoi_geoms = [
            gee_utils.build_corridor_buffer(corridors_module.get_corridor(code), buffer_meters)
            for code in selected_road_codes
        ]
        combined_aoi = aoi_geoms[0]
        for g in aoi_geoms[1:]:
            combined_aoi = combined_aoi.union(g)

        s2_image, s2_meta = gee_utils.get_sentinel2_composite(combined_aoi, s2_date)
        if s2_image is not None:
            map_id = gee_utils.get_map_id(s2_image, config.S2_VIS_PARAMS)
            folium.TileLayer(
                tiles=map_id["tile_fetcher"].url_format,
                attr="Sentinel-2 (Copernicus / ESA)",
                name=f"Sentinel-2 True Color ({s2_meta.get('scene_count', 0)} scenes)",
                overlay=True,
                control=True,
            ).add_to(fmap)
        else:
            st.caption(
                f"Sentinel-2 basemap: no cloud-free scenes found near {s2_date} "
                f"({s2_meta.get('status', 'unknown')}). Try a different date."
            )

        if radar_overlay:
            window_start = (
                dt.datetime.strptime(s2_date, "%Y-%m-%d") - dt.timedelta(days=30)
            ).strftime("%Y-%m-%d")
            window_end = s2_date
            s1_image, s1_meta = gee_utils.get_sentinel1_preview_image(
                combined_aoi, window_start, window_end, orbit_direction
            )
            if s1_image is not None:
                vv_map_id = gee_utils.get_map_id(
                    s1_image, {"bands": ["VV"], "min": -25, "max": 0}
                )
                folium.TileLayer(
                    tiles=vv_map_id["tile_fetcher"].url_format,
                    attr="Sentinel-1 (Copernicus / ESA)",
                    name=f"Sentinel-1 Mean VV ({s1_meta.get('scene_count', 0)} scenes)",
                    overlay=True,
                    control=True,
                ).add_to(fmap)

    for code in selected_road_codes:
        corridor = corridors_module.get_corridor(code)
        latlon_coords = [(lat, lon) for lon, lat in corridor["coordinates"]]
        folium.PolyLine(
            latlon_coords,
            color="#ff3333",
            weight=3,
            opacity=0.9,
            tooltip=f"{code} — {corridor['name']}",
        ).add_to(fmap)
        folium.Marker(
            latlon_coords[0],
            popup=f"{code}: {corridor['name']}",
            icon=folium.Icon(color="red", icon="road", prefix="fa"),
        ).add_to(fmap)

    folium.LayerControl(collapsed=False).add_to(fmap)
    return fmap


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_overview, tab_map, tab_compare, tab_data, tab_methodology = st.tabs(
    ["Overview", "Satellite Map", "Corridor Comparison", "Data", "Methodology"]
)

# ---- Overview tab ---------------------------------------------------------
with tab_overview:
    if not results:
        st.info(
            "Configure parameters in the sidebar and click "
            "**Run Satellite Analysis** to generate results."
        )
    else:
        primary_code = selected_codes[0] if selected_codes and selected_codes[0] in results else list(results.keys())[0]
        primary_df = results[primary_code]
        summary = traffic_analyzer.summarize_latest(primary_df)

        st.subheader(f"Summary — {corridors_module.get_corridor(primary_code)['name']}")

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric(
            "Latest Radar Signal",
            f"{summary['latest_mean_vv_db']:.1f} dB" if summary["latest_mean_vv_db"] is not None else "N/A",
        )
        col2.metric(
            "Typical Signal (Average)",
            f"{summary['historical_avg_vv_db']:.1f} dB" if summary["historical_avg_vv_db"] is not None else "N/A",
        )
        change_val = summary["change_from_previous"]
        col3.metric(
            "Change vs. Previous Month",
            f"{change_val:+.1f} dB" if change_val is not None and pd.notna(change_val) else "N/A",
        )
        col4.metric("Activity Level", summary["relative_activity"])
        col5.metric(
            "Usable Satellite Scenes",
            f"{summary['usable_scene_months']} / {summary['total_months']} months",
        )

        st.caption(
            "\"Activity Level\" compares this month's radar signal to this "
            "same corridor's own history — it is not an exact traffic "
            "congestion count."
        )

        st.divider()

        chart_data = {primary_code: primary_df}

        st.markdown("**Activity Level — is this month typical for this road?**")
        st.plotly_chart(render_activity_level_chart(chart_data), use_container_width=True)
        st.caption(
            "Each bar shows how this month's satellite radar reading "
            "compares to this corridor's own history: Normal = typical, "
            "Elevated/High = stronger signal than usual, Low/Very Low = "
            "weaker signal than usual."
        )

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Radar Signal Strength Over Time**")
            st.plotly_chart(render_signal_strength_chart(chart_data), use_container_width=True)
            st.caption("The raw satellite measurement each month (higher = stronger radar reflection).")
        with c2:
            st.markdown("**Change From Previous Month**")
            st.plotly_chart(render_change_chart(chart_data), use_container_width=True)
            st.caption("Green = signal got stronger since last month. Red = it got weaker.")

        with st.expander("🔧 Advanced: technical z-score view"):
            st.caption(
                "Same data as the Activity Level chart above, shown as the "
                "underlying statistical score (z-score) for users who want "
                "the raw numbers."
            )
            st.plotly_chart(render_proxy_index_chart(chart_data), use_container_width=True)

# ---- Satellite Map tab -----------------------------------------------------
with tab_map:
    st.subheader("Interactive Corridor Map")
    st.caption(
        "Sentinel-2 provides true-color visual context (~10 m resolution). "
        "The optional Sentinel-1 layer shows mean VV radar backscatter — "
        "a proxy signal, not a vehicle-detection layer."
    )

    map_codes = st.multiselect(
        "Corridors to display",
        options=available_codes,
        default=selected_codes if selected_codes else available_codes,
        format_func=lambda code: f"{code} — {corridors_module.get_corridor(code)['name']}",
        key="map_corridor_select",
    )

    map_col1, map_col2 = st.columns([3, 1])
    with map_col2:
        s2_date = st.date_input(
            "Sentinel-2 basemap date",
            value=dt.date.today() - dt.timedelta(days=30),
            max_value=dt.date.today(),
        ).strftime("%Y-%m-%d")
        show_radar = st.checkbox("Show Sentinel-1 radar overlay", value=False)

    with map_col1:
        if not ee_ready:
            st.warning("Map imagery requires an active Earth Engine session.")
        elif not map_codes:
            st.info("Select at least one corridor to display.")
        else:
            fmap = build_folium_map(map_codes, show_radar, s2_date)
            st_folium(fmap, use_container_width=True, height=560, returned_objects=[])

# ---- Corridor Comparison tab ----------------------------------------------
with tab_compare:
    st.subheader("E11 vs. E311 — Corridor Comparison")
    if len(results) < 2:
        st.info(
            "Run the analysis in **Compare Corridors** mode (sidebar) with "
            "two or more corridors selected to see a side-by-side comparison."
        )
    else:
        st.markdown("**Activity Level — which road is more active than usual?**")
        st.plotly_chart(render_activity_level_chart(results), use_container_width=True)
        st.caption(
            "Compares each road only to its own history, so this is the "
            "fairest way to compare two different corridors side by side."
        )

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Radar Signal Strength Over Time**")
            st.plotly_chart(render_signal_strength_chart(results), use_container_width=True)
        with c2:
            st.markdown("**Change From Previous Month**")
            st.plotly_chart(render_change_chart(results), use_container_width=True)

        with st.expander("🔧 Advanced: technical z-score view"):
            st.plotly_chart(render_proxy_index_chart(results), use_container_width=True)

        st.markdown("**Latest Comparison Snapshot**")
        rows = []
        for code, df in results.items():
            s = traffic_analyzer.summarize_latest(df)
            rows.append(
                {
                    "Corridor": code,
                    "Latest Date": s["latest_date"],
                    "Latest Signal (dB)": s["latest_mean_vv_db"],
                    "Typical Signal (dB)": s["historical_avg_vv_db"],
                    "Activity Level": s["relative_activity"],
                    "Usable Months": f"{s['usable_scene_months']}/{s['total_months']}",
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ---- Data tab ---------------------------------------------------------
with tab_data:
    st.subheader("Underlying Analysis Data")
    if not results:
        st.info("Run an analysis to populate the data table.")
    else:
        combined = pd.concat(results.values(), ignore_index=True)
        display_df = combined.copy()
        display_df["status_display"] = display_df["status"]

        st.dataframe(
            combined,
            use_container_width=True,
            hide_index=True,
            column_config={
                "date": st.column_config.DateColumn("Date"),
                "mean_vv_db": st.column_config.NumberColumn(
                    "Signal Strength (dB)", format="%.2f",
                    help="Mean radar signal strength for the month. Higher (less negative) = stronger reflection.",
                ),
                "median_vv_db": st.column_config.NumberColumn(
                    "Median Signal (dB)", format="%.2f",
                    help="Median instead of mean — less sensitive to one unusual scene.",
                ),
                "std_vv_db": st.column_config.NumberColumn(
                    "Signal Variability (dB)", format="%.2f",
                    help="How much the signal varied across scenes captured that month.",
                ),
                "mean_vh_db": st.column_config.NumberColumn(
                    "VH Signal Strength (dB)", format="%.2f",
                    help="Same idea as Signal Strength, using the secondary VH radar channel.",
                ),
                "vv_vh_ratio_db": st.column_config.NumberColumn(
                    "VV/VH Ratio (dB)", format="%.2f",
                    help="Difference between the two radar channels — can help distinguish surface types.",
                ),
                "historical_z_score": st.column_config.NumberColumn(
                    "Activity Score (z)", format="%.2f",
                    help="0 = typical for this road. Positive = stronger than usual. Negative = weaker than usual.",
                ),
                "relative_activity": st.column_config.TextColumn(
                    "Activity Level",
                    help="Plain-language version of the Activity Score: Very Low, Low, Normal, Elevated, or High.",
                ),
                "image_count": st.column_config.NumberColumn(
                    "Satellite Scenes Used",
                    help="How many Sentinel-1 radar scenes were available in that month's search window.",
                ),
            },
        )

        csv_bytes = combined.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download CSV",
            data=csv_bytes,
            file_name=config.CSV_EXPORT_FILENAME,
            mime="text/csv",
        )

        no_data_count = int((combined["status"] != "ok").sum())
        if no_data_count > 0:
            st.warning(
                f"{no_data_count} month(s) had no usable Sentinel-1 imagery "
                "or encountered an error and are marked accordingly rather "
                "than silently treated as zero."
            )

# ---- Methodology tab ---------------------------------------------------------
with tab_methodology:
    st.subheader("How does this work?")

    with st.expander("Scientific approach & limitations", expanded=True):
        st.markdown(
            """
- **Sentinel-1** is a synthetic aperture radar (SAR) satellite constellation
  operated by ESA/Copernicus. It measures backscattered radar energy
  (VV and VH polarizations), reported in decibels (dB), regardless of
  daylight or cloud cover.
- Metallic vehicles and roadside infrastructure can contribute to radar
  scattering, but so do buildings, guardrails, signage, road surface
  moisture, vegetation, and the satellite's acquisition geometry
  (ascending vs. descending pass, incidence angle).
- This application aggregates VV (and, where available, VH) backscatter
  over a buffered polygon around each highway corridor, for a short time
  window around a target day each month, and tracks how that aggregate
  changes over time.
- **This is an experimental, relative traffic-activity proxy — not a
  vehicle count and not a validated congestion metric.** Sentinel-1's
  resolution and revisit characteristics mean a single scene reflects a
  brief moment in time, not sustained traffic flow.
- **Sentinel-2** (optical, ~10 m/pixel at best) is used only for visual
  corridor context/basemap purposes. At 10 m/pixel, individual passenger
  vehicles (typically ~2×5 m) are far below the resolution needed for
  reliable optical detection or counting.
- If direct individual-vehicle detection were ever pursued, it would
  normally require **sub-meter commercial imagery** (e.g. Maxar, Planet
  SkySat) and specialized object-detection models — well beyond what
  freely available Sentinel/Landsat imagery can support.
            """
        )

    with st.expander("What do 'dB' and 'Activity Level' mean?"):
        st.markdown(
            """
**dB (decibels)** is the unit Sentinel-1 radar measurements are reported
in. It's a logarithmic scale — small differences represent real, non-trivial
changes. Values are normally negative (e.g. -8 to -20 dB); **less negative
(closer to zero) means a stronger radar return**. Smooth surfaces like plain
asphalt scatter radar away from the satellite (weaker return), while
angular, metallic objects — vehicles, guardrails, signage, buildings —
reflect more of it straight back (stronger return).

**Activity Level** (Very Low → High) takes that raw dB value and compares
it only to *this same corridor's own history*. It answers "is this month
unusual for this specific road?" rather than giving an absolute number.
Under the hood it's a z-score (how many standard deviations from this
corridor's own historical average) — see the "Advanced: technical z-score
view" expander on the Overview and Comparison tabs if you want the raw
statistic instead of the plain-language label.
            """
        )

    with st.expander("Traffic Proxy Index methodology"):
        st.markdown(
            """
The **Traffic Proxy Index** is a z-score:

```
z = (mean_VV_month − historical_mean_VV) / historical_std_VV
```

computed relative to the corridor's own historical mean and standard
deviation across the analyzed period. A positive z-score means this
month's radar backscatter was above the corridor's typical historical
level; a negative z-score means it was below.

We also report **percentage deviation** from the full-period average and a
**3-month rolling mean** to smooth short-term acquisition noise.

The resulting classification — **Activity Level** — bins the z-score into:
Very Low, Low, Normal, Elevated, High. This describes a **radar anomaly
relative to historical values for that specific corridor**, not an
absolute or cross-corridor congestion measurement.
            """
        )

    with st.expander("Known confounding factors"):
        st.markdown(
            """
- Rainfall and road-surface moisture change radar reflectivity independent
  of traffic.
- Construction, new infrastructure, or roadside changes alter the
  scattering environment over time.
- Orbit/acquisition geometry (ascending vs. descending, incidence angle,
  relative orbit) affects backscatter values — mixing geometries can look
  like a "change" that isn't traffic-related. Use the orbit-direction
  filter for stricter consistency.
- Sentinel-1's revisit interval means each monthly value is built from a
  handful of scenes near the target date, not continuous monitoring.
            """
        )

    with st.expander("Ground-truth validation (future work)"):
        st.markdown(
            """
To validate whether this satellite proxy actually correlates with real
traffic conditions, results should be compared against independent
ground-truth sources such as:

- RTA (Roads and Transport Authority) traffic sensors / loop detectors
- Road-side traffic cameras
- GPS-based floating-car / probe-vehicle datasets
- Third-party traffic-speed APIs (Google, HERE, TomTom)

`traffic_analyzer.py` defines a `GroundTruthSource` abstraction and a
`merge_with_ground_truth()` helper so a future module can plug in a real
data feed and statistically test the correlation, without modifying the
core SAR analysis pipeline. No ground-truth data is fabricated or
simulated anywhere in this application.
            """
        )

    with st.expander("Dataset & processing reference"):
        st.markdown(
            f"""
| Item | Value |
|---|---|
| SAR collection | `{config.S1_COLLECTION_ID}` |
| Optical collection | `{config.S2_COLLECTION_ID}` |
| SAR instrument mode | `{config.S1_INSTRUMENT_MODE}` |
| SAR reduction scale | {config.S1_REDUCE_SCALE_METERS} m |
| Optical composite | Median of least-cloudy scenes, cloud filter < {config.S2_MAX_CLOUD_PERCENT}% |
| Default corridor buffer | {config.DEFAULT_BUFFER_METERS} m |
| Default history window | {config.DEFAULT_MONTHS_BACK} months |
| Default target day | {config.DEFAULT_TARGET_DAY} |
            """
        )
