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
import streamlit.components.v1 as components
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

_T = config.THEME


def _themed_css() -> str:
    """Build the app's "mission control" dark theme as one CSS block.

    Kept as an f-string over config.THEME (rather than hard-coded colors)
    so the Plotly chart theme in style_plotly_fig() and this stylesheet can
    never drift apart — both read the same palette constants.
    """
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500;600&display=swap');

:root {{
    --bg-deep: {_T['bg_deep']};
    --bg-surface: {_T['bg_surface']};
    --bg-surface-alt: {_T['bg_surface_alt']};
    --bg-elevated: {_T['bg_elevated']};
    --border-subtle: {_T['border_subtle']};
    --border-accent: {_T['border_accent']};
    --text-primary: {_T['text_primary']};
    --text-secondary: {_T['text_secondary']};
    --text-muted: {_T['text_muted']};
    --accent-blue: {_T['accent_blue']};
    --accent-cyan: {_T['accent_cyan']};
    --accent-violet: {_T['accent_violet']};
    --font-display: {_T['font_display']};
    --font-body: {_T['font_body']};
    --font-mono: {_T['font_mono']};
}}

/* -- page canvas ---------------------------------------------------- */
.stApp {{
    background:
        radial-gradient(ellipse 900px 500px at 12% -8%, rgba(77,166,255,0.16), transparent 60%),
        radial-gradient(ellipse 700px 500px at 100% 0%, rgba(139,92,246,0.12), transparent 55%),
        radial-gradient(circle, rgba(255,255,255,0.035) 1px, transparent 1px) 0 0/26px 26px,
        var(--bg-deep);
}}
html, body, [class*="css"] {{ font-family: var(--font-body); }}
.block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1200px; }}
h1, h2, h3 {{ font-family: var(--font-display) !important; letter-spacing: -0.01em; }}
p, span, li, label {{ color: var(--text-secondary); }}

/* -- hero header ------------------------------------------------------ */
.hero-wrap {{ margin-top: 0.4rem; margin-bottom: 1.4rem; }}
.hero-badge {{
    display: inline-flex; align-items: center; gap: 0.45rem;
    background: rgba(77,166,255,0.10); border: 1px solid var(--border-accent);
    color: var(--accent-cyan); font-family: var(--font-mono); font-size: 0.72rem;
    letter-spacing: 0.08em; text-transform: uppercase;
    padding: 0.3rem 0.7rem; border-radius: 999px; margin-bottom: 0.9rem;
}}
.hero-badge .dot {{
    width: 7px; height: 7px; border-radius: 50%; background: var(--accent-cyan);
    box-shadow: 0 0 0 rgba(34,211,238,0.6); animation: pulse-dot 2s infinite;
}}
@keyframes pulse-dot {{
    0% {{ box-shadow: 0 0 0 0 rgba(34,211,238,0.55); }}
    70% {{ box-shadow: 0 0 0 8px rgba(34,211,238,0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(34,211,238,0); }}
}}
.hero-title {{
    font-family: var(--font-display); font-weight: 700; font-size: 2.6rem;
    line-height: 1.12; margin: 0.6rem 0 0.5rem 0;
    background: linear-gradient(100deg, #ffffff 10%, var(--accent-cyan) 55%, var(--accent-violet) 95%);
    -webkit-background-clip: text; background-clip: text;
    color: transparent !important; -webkit-text-fill-color: transparent !important;
}}
.hero-subtitle {{ color: var(--text-secondary); font-size: 1.02rem; margin: 0; max-width: 62ch; }}

/* -- resolution notice -------------------------------------------------- */
.proxy-disclaimer {{
    display: flex; gap: 0.85rem; align-items: flex-start;
    background: linear-gradient(135deg, rgba(77,166,255,0.09), rgba(139,92,246,0.05));
    border: 1px solid var(--border-accent);
    border-radius: 12px; padding: 1rem 1.15rem; margin: 1.1rem 0 1.4rem 0;
}}
.proxy-disclaimer .icon {{
    flex-shrink: 0; width: 34px; height: 34px; border-radius: 9px;
    background: rgba(77,166,255,0.16); display: flex; align-items: center;
    justify-content: center; font-size: 1.1rem;
}}
.proxy-disclaimer strong {{ color: var(--text-primary); font-family: var(--font-display); font-size: 0.95rem; }}
.proxy-disclaimer p {{ margin: 0.25rem 0 0 0; font-size: 0.9rem; line-height: 1.5; color: var(--text-secondary); }}

/* -- section eyebrow labels ------------------------------------------ */
.eyebrow {{
    display: inline-flex; align-items: center; gap: 0.4rem;
    font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--accent-cyan); margin-bottom: 0.35rem;
}}
.eyebrow::before {{ content: "◆"; font-size: 0.6rem; }}

/* -- metric / stat cards ---------------------------------------------- */
div[data-testid="stMetric"] {{
    background: linear-gradient(160deg, var(--bg-surface), var(--bg-surface-alt));
    border: 1px solid var(--border-subtle);
    border-top: 2px solid var(--accent-blue);
    border-radius: 12px; padding: 0.9rem 1rem 0.7rem 1rem;
    transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}}
div[data-testid="stMetric"]:hover {{
    transform: translateY(-2px);
    border-color: var(--border-accent);
    box-shadow: 0 8px 24px rgba(77,166,255,0.12);
}}
div[data-testid="stMetricValue"] {{
    font-family: var(--font-mono) !important; font-size: 1.5rem !important;
    color: var(--text-primary) !important;
}}
div[data-testid="stMetricLabel"] {{
    font-size: 0.76rem !important; text-transform: uppercase; letter-spacing: 0.05em;
    color: var(--text-muted) !important;
}}

/* -- buttons ------------------------------------------------------------ */
.stButton > button, .stDownloadButton > button {{
    background: linear-gradient(100deg, var(--accent-blue), var(--accent-violet)) !important;
    color: #ffffff !important; border: none !important; border-radius: 10px !important;
    font-family: var(--font-display) !important; font-weight: 600 !important;
    letter-spacing: 0.01em; box-shadow: 0 4px 18px rgba(77,166,255,0.25);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
    transform: translateY(-1px); box-shadow: 0 8px 26px rgba(77,166,255,0.4);
}}

/* -- sidebar -------------------------------------------------------- */
section[data-testid="stSidebar"] {{
    background: var(--bg-surface-alt); border-right: 1px solid var(--border-subtle);
}}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {{ font-family: var(--font-display) !important; }}

/* -- tabs ---------------------------------------------------------------- */
.stTabs [data-baseweb="tab-list"] {{ gap: 0.3rem; border-bottom: 1px solid var(--border-subtle); }}
.stTabs [data-baseweb="tab"] {{
    font-family: var(--font-display); font-weight: 500; color: var(--text-muted);
    padding: 0.6rem 1rem;
}}
.stTabs [aria-selected="true"] {{ color: var(--text-primary) !important; }}
.stTabs [data-baseweb="tab-highlight"] {{
    background: linear-gradient(90deg, var(--accent-blue), var(--accent-cyan)) !important;
    height: 3px !important; border-radius: 3px;
}}

/* -- expanders ------------------------------------------------------- */
details[data-testid="stExpander"] {{
    background: var(--bg-surface); border: 1px solid var(--border-subtle) !important;
    border-radius: 10px !important;
}}

/* -- dataframe / captions ------------------------------------------------ */
[data-testid="stDataFrame"] {{ border-radius: 10px; overflow: hidden; border: 1px solid var(--border-subtle); }}
[data-testid="stCaptionContainer"] {{ color: var(--text-muted) !important; }}
hr {{ border-color: var(--border-subtle) !important; }}

/* -- entrance animations -------------------------------------------------
   Cards and charts fade+lift in as they render, staggered per column so a
   row of metrics cascades in left-to-right instead of popping in at once.
   Pure CSS (no JS), so it replays reliably on every Streamlit rerun since
   these are freshly-inserted DOM nodes each time. */
@keyframes fadeInUp {{
    from {{ opacity: 0; transform: translateY(10px); }}
    to {{ opacity: 1; transform: translateY(0); }}
}}
div[data-testid="stMetric"],
div[data-testid="stPlotlyChart"],
details[data-testid="stExpander"],
[data-testid="stDataFrame"] {{
    animation: fadeInUp 0.45s ease both;
}}
div[data-testid="column"]:nth-of-type(1) div[data-testid="stMetric"] {{ animation-delay: 0.02s; }}
div[data-testid="column"]:nth-of-type(2) div[data-testid="stMetric"] {{ animation-delay: 0.08s; }}
div[data-testid="column"]:nth-of-type(3) div[data-testid="stMetric"] {{ animation-delay: 0.14s; }}
div[data-testid="column"]:nth-of-type(4) div[data-testid="stMetric"] {{ animation-delay: 0.20s; }}
div[data-testid="column"]:nth-of-type(5) div[data-testid="stMetric"] {{ animation-delay: 0.26s; }}

/* CTA pulse: gently draws the eye to the primary action before the first
   run only (Python adds/omits the "cta-idle" class based on whether
   results exist yet), so it stops calling attention to itself once used. */
@keyframes ctaPulse {{
    0%, 100% {{ box-shadow: 0 4px 18px rgba(77,166,255,0.25); }}
    50% {{ box-shadow: 0 4px 28px rgba(77,166,255,0.55), 0 0 0 4px rgba(77,166,255,0.08); }}
}}
.st-key-run_button_container_idle .stButton > button {{ animation: ctaPulse 2.4s ease-in-out infinite; }}
</style>
"""


st.markdown(_themed_css(), unsafe_allow_html=True)

# Number count-up animation for metric cards. st.markdown's <script> tags
# never execute in Streamlit (HTML is inserted via innerHTML, which the
# browser never runs embedded scripts for), so this needs a real
# components.html() iframe instead, reaching into window.parent.document
# (same-origin, so this is allowed) to touch the actual app DOM. Installs
# ONE persistent pair of MutationObservers the first time the page loads in
# the browser tab; from then on it reacts to every future Streamlit rerun
# without needing to re-run itself. Fully wrapped in try/catch and no-ops
# safely if anything about this iframe/DOM access ever stops working —
# worst case the numbers just render statically, same as before.
components.html(
    """
    <script>
    (function() {
      try {
        var doc = window.parent.document;
        function animateValue(el) {
          var text = el.textContent.trim();
          if (el._cuRunning || el._cuLastText === text) return;
          var m = text.match(/-?\\d+\\.?\\d*/);
          if (!m) { el._cuLastText = text; return; }
          var target = parseFloat(m[0]);
          var idx = text.indexOf(m[0]);
          var prefix = text.slice(0, idx);
          var suffix = text.slice(idx + m[0].length);
          var decimals = (m[0].split('.')[1] || '').length;
          el._cuRunning = true;
          if (el._cuObserver) el._cuObserver.disconnect();
          var duration = 650, start = null;
          function step(ts) {
            if (start === null) start = ts;
            var p = Math.min((ts - start) / duration, 1);
            var eased = 1 - Math.pow(1 - p, 3);
            el.textContent = prefix + (target * eased).toFixed(decimals) + suffix;
            if (p < 1) {
              requestAnimationFrame(step);
            } else {
              el.textContent = text;
              el._cuLastText = text;
              el._cuRunning = false;
              if (el._cuObserver) {
                el._cuObserver.observe(el, {childList: true, characterData: true, subtree: true});
              }
            }
          }
          requestAnimationFrame(step);
        }
        function scan() {
          doc.querySelectorAll('[data-testid="stMetricValue"]').forEach(function (el) {
            if (!el._cuSetup) {
              el._cuSetup = true;
              el._cuLastText = null;
              var obs = new MutationObserver(function () { animateValue(el); });
              el._cuObserver = obs;
              obs.observe(el, {childList: true, characterData: true, subtree: true});
              animateValue(el);
            }
          });
        }
        new MutationObserver(scan).observe(doc.body, {childList: true, subtree: true});
        scan();
      } catch (e) { /* animation is a nice-to-have; never break the app over it */ }
    })();
    </script>
    """,
    height=0,
)


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


@st.cache_resource(show_spinner="🛰️ Establishing satellite uplink...")
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

st.markdown(
    f"""
    <div class="hero-wrap">
        <div class="hero-badge"><span class="dot"></span>LIVE SATELLITE FEED</div>
        <h1 class="hero-title">{config.APP_TITLE}</h1>
        <p class="hero-subtitle">{config.APP_SUBTITLE}</p>
    </div>
    <div class="proxy-disclaimer">
        <div class="icon">📡</div>
        <div>
            <strong>{config.RESOLUTION_NOTICE_TITLE}</strong>
            <p>{config.RESOLUTION_NOTICE_BODY}</p>
        </div>
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
    options=["Single Highway", "Compare Highways"],
    index=0,
)

available_codes = corridors_module.list_corridor_codes()

if analysis_mode == "Single Highway":
    selected_codes = [
        st.sidebar.selectbox(
            "Highway",
            options=available_codes,
            format_func=lambda code: f"{code} — {corridors_module.get_corridor(code)['name']}",
        )
    ]
else:
    selected_codes = st.sidebar.multiselect(
        "Highways to Compare",
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
    "Measurement Zone Width (meters)",
    min_value=config.MIN_BUFFER_METERS,
    max_value=config.MAX_BUFFER_METERS,
    value=config.DEFAULT_BUFFER_METERS,
    step=25,
    help="How wide an area around the highway to include in each reading.",
)

orbit_direction = st.sidebar.selectbox(
    "Sentinel-1 Orbit Direction",
    options=config.ORBIT_DIRECTIONS,
    index=0,
    help="Ascending and descending passes view the road from "
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

_has_results = bool(st.session_state.get("results"))
with st.sidebar.container(key="run_button_container" if _has_results else "run_button_container_idle"):
    run_clicked = st.button("🛰️ Run Satellite Analysis", type="primary", use_container_width=True)

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

SCAN_MESSAGES = [
    "📡 Pinging {code} via Sentinel-1...",
    "🔭 Scanning {code} for radar echoes...",
    "🛰️ Downlinking {code}'s signal...",
    "📶 Tuning into {code}'s radar backscatter...",
]

if run_clicked and ee_ready:
    if not selected_codes:
        st.sidebar.warning("Select at least one highway to analyze.")
    else:
        results = {}
        had_error = False
        progress = st.sidebar.progress(0.0, text="🛰️ Powering up the satellite uplink...")
        for i, code in enumerate(selected_codes):
            progress.progress(
                i / len(selected_codes),
                text=SCAN_MESSAGES[i % len(SCAN_MESSAGES)].format(code=code),
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
                had_error = True
                st.sidebar.error(f"Analysis failed for {code}: {exc}")
        progress.progress(1.0, text="✅ Downlink complete!")
        if results and not had_error:
            st.balloons()
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


def style_plotly_fig(fig: go.Figure) -> go.Figure:
    """Apply the app's shared chart theme so every figure sits flush with
    the surrounding dark-themed cards instead of showing Plotly's default
    white chrome. Called once at the end of each render_* function.
    """
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=_T["bg_surface"],
        font=dict(family=_T["font_body"], color=_T["text_secondary"], size=13),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=_T["text_secondary"])),
        hoverlabel=dict(
            bgcolor=_T["bg_elevated"],
            bordercolor=_T["border_subtle"],
            font=dict(family=_T["font_body"], color=_T["text_primary"]),
        ),
        margin=dict(t=fig.layout.margin.t or 30, b=fig.layout.margin.b or 10, l=40, r=20),
    )
    fig.update_xaxes(
        gridcolor=_T["border_subtle"], zerolinecolor=_T["border_subtle"],
        linecolor=_T["border_subtle"], tickfont=dict(color=_T["text_muted"]),
        title_font=dict(color=_T["text_muted"]),
    )
    fig.update_yaxes(
        gridcolor=_T["border_subtle"], zerolinecolor=_T["border_subtle"],
        linecolor=_T["border_subtle"], tickfont=dict(color=_T["text_muted"]),
        title_font=dict(color=_T["text_muted"]),
    )
    return fig


def eyebrow(text: str) -> None:
    """Render a small uppercase accent-colored label above a section, for
    the dashboard-style "mission control" visual language used throughout.
    """
    st.markdown(f'<div class="eyebrow">{text}</div>', unsafe_allow_html=True)


def activity_badge(level: str) -> str:
    """Prefix an Activity Level label with its small badge icon, e.g.
    'Low' -> '🔹 Low'. Icon is always paired with the text (never replaces
    it), consistent with the "never color/icon alone" rule this app
    already follows for the Activity Level color ramp.
    """
    icon = config.ACTIVITY_LEVEL_BADGES.get(level, config.ACTIVITY_LEVEL_BADGES["Unknown"])
    return f"{icon} {level}"


def render_signal_strength_chart(dfs: dict) -> go.Figure:
    """Plain-language signal-trend chart: shape only, no dB numbers shown.

    The underlying values are still raw Sentinel-1 mean VV backscatter (dB),
    but the axis is deliberately unitless here — first-time visitors get the
    trend (rising/falling), while the exact dB values live in the "Advanced"
    z-score view for anyone who wants them.
    """
    fig = go.Figure()
    all_values = pd.concat([df["mean_vv_db"] for df in dfs.values()]).dropna()

    for code, df in dfs.items():
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["mean_vv_db"],
                mode="lines+markers",
                name=code,
                connectgaps=False,
                line=dict(width=3),
                marker=dict(size=9),
                hovertemplate="%{x|%b %Y}<extra>" + code + "</extra>",
            )
        )

    yaxis_config = dict(title=None, showgrid=False, zeroline=False)
    if not all_values.empty:
        span = all_values.max() - all_values.min()
        pad = span * 0.15 if span > 0 else 1.0
        y0, y1 = all_values.min() - pad, all_values.max() + pad
        yaxis_config.update(
            range=[y0, y1],
            tickmode="array",
            tickvals=[y0, y1],
            ticktext=["Weaker", "Stronger"],
        )

    fig.update_layout(
        xaxis_title="Month",
        yaxis=yaxis_config,
        hovermode="x unified",
        legend_title="Highway",
        margin=dict(t=30, b=10),
        showlegend=len(dfs) > 1,
    )
    return style_plotly_fig(fig)


def render_activity_level_chart(dfs: dict) -> go.Figure:
    """Plain-language 'Activity Level' chart: Very Low -> High, color coded.

    This is the primary, easy-to-read view of the traffic proxy. It shows
    the same underlying z-score classification as the technical view, but
    as labeled color bands instead of a raw statistical score, so it can be
    read at a glance without knowing what a z-score is.
    """
    fig = go.Figure()
    # NOTE: no explicit bar `width` is set. Plotly bar width is interpreted
    # in axis units on a date x-axis — a value like 0.8 means 0.8
    # *milliseconds* wide (an invisible sliver), which was the cause of the
    # "thin lines" look. Leaving width unset lets Plotly auto-size bars to
    # fill the space between months sensibly, for both one and many series.
    for code, df in dfs.items():
        activity = df["relative_activity"].fillna("Unknown")
        ranks = activity.map(ACTIVITY_LEVEL_RANK).fillna(0)
        colors = activity.map(config.ACTIVITY_LEVEL_COLORS).fillna(
            config.ACTIVITY_LEVEL_COLORS["Unknown"]
        )
        plain_text = activity.map(ACTIVITY_LEVEL_PLAIN_HOVER).fillna(
            ACTIVITY_LEVEL_PLAIN_HOVER["Unknown"]
        )
        # On-bar text labels only render for a single highway. With two or
        # more highways grouped side by side, the bars get narrow enough
        # that outside-positioned labels collide and overlap illegibly —
        # the legend + color + hover tooltip already identify each bar in
        # that view, so the label is redundant there anyway. Also suppress
        # it for "Unknown" (zero-height bars have nothing to attach a
        # label to); the hover tooltip still explains it.
        show_labels = len(dfs) == 1
        bar_labels = activity.where(show_labels & (activity != "Unknown"), "")
        fig.add_trace(
            go.Bar(
                x=df["date"],
                y=ranks,
                name=code,
                marker_color=colors,
                marker_line_width=0,
                text=bar_labels,
                textposition="outside",
                textfont=dict(size=13, weight="bold"),
                cliponaxis=False,
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
            title=None,
            tickmode="array",
            tickvals=[1, 2, 3, 4, 5],
            ticktext=config.ACTIVITY_LEVELS,
            range=[0, 6.2],
        ),
        barmode="group",
        bargap=0.25,
        hovermode="x unified",
        legend_title="Highway",
        margin=dict(t=30, b=10),
        height=380,
        showlegend=len(dfs) > 1,
    )
    return style_plotly_fig(fig)


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
    fig.add_hline(y=0, line_dash="dot", line_color=_T["text_muted"])
    fig.update_layout(
        xaxis_title="Month",
        yaxis_title="Standard deviations from this road's historical mean (z-score)",
        hovermode="x unified",
        legend_title="Highway",
        margin=dict(t=30, b=10),
    )
    return style_plotly_fig(fig)


def _describe_change(value: float) -> str:
    """Classify a dB change into a plain-language description.

    A small band around zero is called "About the same" rather than
    stronger/weaker, so ordinary acquisition-to-acquisition noise isn't
    over-narrated as a meaningful change. See
    config.CHANGE_ABOUT_SAME_THRESHOLD_DB for the cutoff.
    """
    if value is None or pd.isna(value):
        return "No comparison available"
    if abs(value) < config.CHANGE_ABOUT_SAME_THRESHOLD_DB:
        return "About the same as last month"
    return "Stronger than last month" if value > 0 else "Weaker than last month"


def render_change_chart(dfs: dict) -> go.Figure:
    """Plain-language month-to-month change: direction and color only.

    No dB numbers are shown on the axis or in the hover text — bar
    direction (up/down) plus color (green/red) carry the meaning, backed by
    a plain-language description on hover. Exact values remain available in
    the Advanced z-score view and the Data tab.
    """
    fig = go.Figure()
    all_values = pd.concat([df["monthly_change_db"] for df in dfs.values()]).dropna()

    for code, df in dfs.items():
        colors = [
            "#e74c3c" if v is not None and pd.notna(v) and v < 0 else "#2ecc71"
            for v in df["monthly_change_db"]
        ]
        descriptions = df["monthly_change_db"].apply(_describe_change)
        fig.add_trace(
            go.Bar(
                x=df["date"],
                y=df["monthly_change_db"],
                name=code,
                marker_color=colors if len(dfs) == 1 else None,
                customdata=descriptions,
                hovertemplate=(
                    "%{x|%b %Y}<br>%{customdata}<extra>" + code + "</extra>"
                ),
            )
        )

    yaxis_config = dict(title=None, showgrid=False, zeroline=True, zerolinecolor="gray")
    if not all_values.empty:
        span = max(abs(all_values.min()), abs(all_values.max()))
        pad = span * 0.25 if span > 0 else 1.0
        bound = span + pad
        yaxis_config.update(
            range=[-bound, bound],
            tickmode="array",
            tickvals=[-bound, 0, bound],
            ticktext=["Weaker", "No change", "Stronger"],
        )

    fig.update_layout(
        xaxis_title="Month",
        yaxis=yaxis_config,
        hovermode="x unified",
        legend_title="Highway",
        barmode="group",
        margin=dict(t=30, b=10),
    )
    return style_plotly_fig(fig)


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
    ["🛰️ Overview", "🗺️ Satellite Map", "⚖️ Road Comparison", "📊 Data", "📘 Methodology"]
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

        eyebrow("Live Summary")
        st.subheader(f"{corridors_module.get_corridor(primary_code)['name']}")

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
        col4.metric("Activity Level", activity_badge(summary["relative_activity"]))
        col5.metric(
            "Usable Satellite Scenes",
            f"{summary['usable_scene_months']} / {summary['total_months']} months",
        )

        st.caption(
            "\"Activity Level\" compares this month's radar signal to this "
            "same road's own history — it is not an exact traffic "
            "congestion count."
        )

        st.divider()

        chart_data = {primary_code: primary_df}

        eyebrow("Traffic Activity")
        st.markdown("#### Is this month typical for this road?")
        st.plotly_chart(render_activity_level_chart(chart_data), use_container_width=True)
        st.caption(
            "Each bar shows how this month's satellite radar reading "
            "compares to this road's own history: Normal = typical, "
            "Elevated/High = stronger signal than usual, Low/Very Low = "
            "weaker signal than usual."
        )

        c1, c2 = st.columns(2)
        with c1:
            eyebrow("Trend")
            st.markdown("#### Signal Over Time")
            st.plotly_chart(render_signal_strength_chart(chart_data), use_container_width=True)
            st.caption("Shows whether the satellite reading has been getting stronger or weaker each month.")
        with c2:
            eyebrow("Momentum")
            st.markdown("#### Change From Previous Month")
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
    eyebrow("Ground Truth")
    st.subheader("Interactive Highway Map")
    st.caption(
        "Sentinel-2 provides true-color visual context (~10 m resolution). "
        "The optional Sentinel-1 layer shows mean VV radar backscatter — "
        "a proxy signal, not a vehicle-detection layer."
    )

    map_codes = st.multiselect(
        "Highways to display",
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
            st.info("Select at least one highway to display.")
        else:
            fmap = build_folium_map(map_codes, show_radar, s2_date)
            st_folium(fmap, use_container_width=True, height=560, returned_objects=[])

# ---- Road Comparison tab ----------------------------------------------
with tab_compare:
    eyebrow("Head to Head")
    compare_title = " vs. ".join(results.keys()) if len(results) >= 2 else " vs. ".join(available_codes)
    st.subheader(compare_title)
    if len(results) < 2:
        st.info(
            "Run the analysis in **Compare Highways** mode (sidebar) with "
            "two or more highways selected to see a side-by-side comparison."
        )
    else:
        st.markdown("#### Which road is more active than usual?")
        st.plotly_chart(render_activity_level_chart(results), use_container_width=True)
        st.caption(
            "Compares each road only to its own history, so this is the "
            "fairest way to compare two different roads side by side."
        )

        c1, c2 = st.columns(2)
        with c1:
            eyebrow("Trend")
            st.markdown("#### Signal Over Time")
            st.plotly_chart(render_signal_strength_chart(results), use_container_width=True)
            st.caption("Shows whether each road's satellite reading has been getting stronger or weaker.")
        with c2:
            eyebrow("Momentum")
            st.markdown("#### Change From Previous Month")
            st.plotly_chart(render_change_chart(results), use_container_width=True)
            st.caption("Green = signal got stronger since last month. Red = it got weaker.")

        with st.expander("🔧 Advanced: technical z-score view"):
            st.plotly_chart(render_proxy_index_chart(results), use_container_width=True)

        eyebrow("Snapshot")
        st.markdown("#### Latest Comparison")
        rows = []
        for code, df in results.items():
            s = traffic_analyzer.summarize_latest(df)
            rows.append(
                {
                    "Highway": code,
                    "Latest Date": s["latest_date"],
                    "Activity Level": activity_badge(s["relative_activity"]),
                    "Usable Months": f"{s['usable_scene_months']}/{s['total_months']}",
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ---- Data tab ---------------------------------------------------------
with tab_data:
    eyebrow("Raw Feed")
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
    eyebrow("Under the Hood")
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
  over a measurement zone around each highway, for a short time window
  around a target day each month, and tracks how that aggregate changes
  over time.
- **This is an experimental, relative traffic-activity proxy — not a
  vehicle count and not a validated congestion metric.** Sentinel-1's
  resolution and revisit characteristics mean a single scene reflects a
  brief moment in time, not sustained traffic flow.
- **Sentinel-2** (optical, ~10 m/pixel at best) is used only for visual
  road context/basemap purposes. At 10 m/pixel, individual passenger
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
it only to *this same road's own history*. It answers "is this month
unusual for this specific road?" rather than giving an absolute number.
Under the hood it's a z-score (how many standard deviations from this
road's own historical average) — see the "Advanced: technical z-score
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

computed relative to the road's own historical mean and standard
deviation across the analyzed period. A positive z-score means this
month's radar backscatter was above the road's typical historical
level; a negative z-score means it was below.

We also report **percentage deviation** from the full-period average and a
**3-month rolling mean** to smooth short-term acquisition noise.

The resulting classification — **Activity Level** — bins the z-score into:
Very Low, Low, Normal, Elevated, High. This describes a **radar anomaly
relative to historical values for that specific road**, not an
absolute or cross-road congestion measurement.
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
| Default measurement zone width | {config.DEFAULT_BUFFER_METERS} m |
| Default history window | {config.DEFAULT_MONTHS_BACK} months |
| Default target day | {config.DEFAULT_TARGET_DAY} |
            """
        )
