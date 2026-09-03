# Sharjah–Dubai Satellite Traffic Density Monitor

A prototype Streamlit dashboard that estimates a **satellite-derived traffic
activity proxy** along major Dubai–Sharjah highway corridors, using
Copernicus **Sentinel-1 SAR** and **Sentinel-2** optical imagery processed
server-side in **Google Earth Engine (GEE)**.

> **This system does not count vehicles.** It measures aggregated radar
> backscatter changes along a defined highway corridor over time and
> expresses them as a relative, normalized index. See
> [Scientific Limitations](#scientific-limitations) below.

---

## What this application does

- Defines highway corridors (**E311 – Sheikh Mohammed Bin Zayed Road**,
  **E11 – Al Ittihad Road**, and **E611 – Emirates Road**) as buffered line
  geometries in `corridors.py`.
- For each of the last *N* months, queries Sentinel-1 GRD (`IW` mode, VV/VH)
  over the corridor buffer within a configurable date window, and computes
  mean/median/std backscatter server-side in Earth Engine.
- Normalizes the resulting time series into a **Traffic Proxy Index**
  (z-score relative to the corridor's own historical distribution) and a
  plain-language **Activity Level** classification (Very Low → High), shown
  as a color-coded chart so it's readable without knowing what a z-score is.
- Renders an interactive Sentinel-2 true-color map of each corridor for
  visual context, with an optional Sentinel-1 backscatter overlay.
- Lets you compare corridors side-by-side, inspect the underlying data
  table, and export results as CSV.
- Documents its own methodology and limitations directly in the UI
  (Methodology tab), including a plain-language explainer of dB and
  Activity Level for first-time users.

## Scientific Limitations

**Read this before interpreting any output.**

- **Sentinel-2** (optical) has ~10 m/pixel resolution at best. A passenger
  vehicle is roughly 2×5 m — well below what Sentinel-2 (or Landsat 8/9,
  ~15–30 m) can reliably resolve. This application uses Sentinel-2 only for
  **visual corridor context**, never for detection or counting.
- **Sentinel-1** (SAR) is the primary analytical signal. Metallic vehicles
  and roadside infrastructure can contribute to radar backscatter, but so do
  buildings, road moisture, vegetation, and the satellite's acquisition
  geometry. A change in aggregated corridor backscatter **may correlate**
  with traffic activity but is also affected by weather, infrastructure
  changes, and orbit geometry. Treat all output as an **experimental proxy
  signal**, not ground truth.
- If individual-vehicle detection is ever desired, it would require
  **sub-meter commercial imagery** (e.g. Maxar, Planet SkySat) and dedicated
  object-detection models — a fundamentally different (and licensed) data
  source, not included here.
- No output from this application should be used as authoritative evidence
  of traffic congestion without independent validation against ground-truth
  sources (RTA sensors, loop detectors, road cameras, floating-car/GPS
  data). See `traffic_analyzer.GroundTruthSource` for the intended future
  integration point.

## Terminology used throughout the app

Uses: *Satellite Traffic Proxy*, *Radar Activity Index*, *Activity Level*,
*SAR Backscatter Anomaly*, *Relative Traffic Proxy*.

Avoids: *Cars Detected*, *Exact Vehicle Count*, *Actual Congestion Count*,
*Vehicles Seen by Sentinel* — these claims are not scientifically supported
by the underlying imagery and are never made by this application.

---

## Project structure

```
sharjah_dubai_traffic/
├── app.py                          # Streamlit UI only — no direct EE calls
├── traffic_analyzer.py             # Month arithmetic, proxy index, classification, ground-truth interface
├── gee_utils.py                    # All Earth Engine calls (init, filtering, reduceRegion, composites)
├── corridors.py                    # Corridor configuration (pure data, no EE dependency at import)
├── config.py                       # Constants, dataset IDs, thresholds, defaults
├── requirements.txt
├── README.md
├── .gitignore
├── .streamlit/
│   └── secrets.toml.example        # Template for cloud-deployment credentials (see Cloud Deployment below)
└── data/                           # Local scratch space for exports (CSV exports are git-ignored)
```

## Installation

```bash
python -m venv .venv
```

**macOS / Linux:**
```bash
source .venv/bin/activate
```

**Windows:**
```bash
.venv\Scripts\activate
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

## Authenticate Google Earth Engine (local development)

This app requires a Google Earth Engine account (free for research/
non-commercial use — sign up at https://earthengine.google.com/).

```bash
earthengine authenticate
```

Follow the browser prompt to sign in and authorize. This stores local
credentials that the `earthengine-api` Python package (and this app) will
reuse automatically on subsequent runs.

If a machine's Python installation is missing root CA certificates (common
with python.org macOS installs, surfaced as `CERTIFICATE_VERIFY_FAILED`),
either run `/Applications/Python <version>/Install Certificates.command`,
or set `SSL_CERT_FILE` to the `certifi` package's bundle for the one-off
`earthengine authenticate` step:
```bash
SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())") earthengine authenticate
```

### Google Cloud project configuration (if required)

Since November 2024, Earth Engine requires most accounts to associate a
Google Cloud project with API calls. If `earthengine authenticate` or the
app's startup fails with a project-related error:

1. Create or choose a Google Cloud project with the Earth Engine API
   enabled (see https://console.cloud.google.com/).
2. Set it for this app via either:
   - Environment variable: `export EE_PROJECT_ID=your-project-id`
   - Or edit `GEE_PROJECT_ID` directly in `config.py`.

If Earth Engine is not authenticated, the app will **not crash** — it
displays an in-app message explaining how to run `earthengine authenticate`
and reload.

## Run the app locally

```bash
streamlit run app.py
```

Then, in the browser dashboard:

1. Choose **Single Highway** or **Compare Highways** mode.
2. Select any of E11, E311, or E611.
3. Set months of history (3–24), target day of month (default 25), date
   tolerance, measurement zone width, and Sentinel-1 orbit direction.
4. Click **Run Satellite Analysis**.
5. Explore the **Overview**, **Satellite Map**, **Road Comparison**,
   **Data**, and **Methodology** tabs.
6. Download the results table as
   `sharjah_dubai_satellite_traffic_proxy.csv` from the Data tab.

The app is safe to load **before** running any analysis — all tabs render
placeholder/informational states until you click **Run Satellite Analysis**.

---

## Cloud Deployment (Streamlit Community Cloud)

Local development relies on `earthengine authenticate`, which caches
credentials in your home directory — that doesn't exist on a fresh cloud
container. For cloud deployment, this app supports a **Google Cloud service
account** instead, configured via Streamlit's Secrets manager. No code
changes are needed to switch between the two — `gee_utils.initialize_earth_engine()`
tries a service account from `st.secrets` first, then falls back to local
credentials.

### 1. Create a Google Cloud service account with Earth Engine access

1. In [Google Cloud Console](https://console.cloud.google.com/), select or
   create a project, and enable the **Earth Engine API** for it.
2. Go to **IAM & Admin → Service Accounts → Create Service Account**.
3. Register the service account for Earth Engine at
   https://signup.earthengine.google.com/#!/service_accounts (required
   once per service account before it can call the Earth Engine API).
4. Open the new service account → **Keys → Add Key → Create new key →
   JSON**, and download it. Treat this file like a password — never commit
   it to git.

### 2. Push this project to GitHub

Streamlit Community Cloud deploys directly from a GitHub repository:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

(`.gitignore` already excludes `.venv/`, `.streamlit/secrets.toml`, and any
local credentials — only source files are pushed.)

### 3. Deploy on Streamlit Community Cloud

1. Go to https://share.streamlit.io and sign in with your GitHub account.
2. Click **New app**, select your repository, branch `main`, and main file
   `app.py`.
3. Under **Advanced settings**, you can set a **custom app URL** (subdomain)
   — e.g. entering `sharjahxdubai` gives you
   `https://sharjahxdubai.streamlit.app` (subject to the name being
   available).
4. Before (or right after) the first deploy, open **App settings → Secrets**
   and paste the contents of `.streamlit/secrets.toml.example`, filled in
   with the real values from your downloaded service-account JSON key (see
   that file for the exact field mapping). Save.
5. Click **Deploy**. The app will install `requirements.txt` and start;
   watch the build log for errors.

### 4. Redeploying after changes

Streamlit Community Cloud auto-redeploys on every push to the connected
branch. For local iteration, just keep using `streamlit run app.py` — the
service-account path only activates when `st.secrets["gee_service_account"]`
is present, so local dev keeps using your `earthengine authenticate` session
unchanged.

---

## Adding a new corridor

Edit `corridors.py` and either add a new `Corridor(...)` entry to the
`CORRIDORS` registry, or call `corridors.add_corridor(...)` at runtime. Each
corridor needs: `road_code`, `name`, `coordinates` (a list of `[lon, lat]`
points), `buffer_meters`, and an optional `description`. No other file needs
to change — the sidebar selector, comparison mode, and map layers all read
from this registry automatically.

## Future extensions (designed for, not yet implemented)

- **VIIRS nighttime lights / radiance** and **Landsat 8/9 thermal infrared**
  dataset IDs are already reserved in `config.py` for a future contextual
  module.
- **Ground-truth validation**: `traffic_analyzer.GroundTruthSource` is an
  abstract interface for plugging in RTA sensors, HERE/TomTom/Google traffic
  APIs, or floating-car data, plus a `merge_with_ground_truth()` helper to
  build a combined dataset. No ground truth is fabricated anywhere in this
  app.
- **ML-ready dataset**: the analysis DataFrame already includes engineered
  features (`mean_vv_db`, `std_vv_db`, `vv_vh_ratio_db`, `historical_z_score`,
  `monthly_change_pct`, `month`, `day_of_week`, `orbit_direction`,
  `buffer_meters`, ...) suitable as ML input once a real
  `ground_truth_vehicle_count` (or similar) target is available. No model is
  trained without validated ground truth.
- **Corridor segmentation / SAR anomaly heatmap**: splitting each corridor
  into shorter segments (e.g. 1 km) and mapping per-segment anomalies is a
  natural next step, described as *radar activity anomaly*, not guaranteed
  congestion — not yet implemented in this version.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Earth Engine is not available" banner | Not authenticated, or missing Cloud project | Run `earthengine authenticate`; set `EE_PROJECT_ID` |
| `CERTIFICATE_VERIFY_FAILED` during `earthengine authenticate` | Python missing root CA certs (common on python.org macOS installs) | See "Authenticate Google Earth Engine" above |
| A month shows `status = no_data` | No Sentinel-1 scene in that ± window | Widen "Date Tolerance" in the sidebar |
| Sentinel-2 map is blank | No cloud-free scene near the chosen date | Pick a different basemap date |
| Slow first run | Earth Engine session + cold cache | Subsequent runs are cached for up to 1 hour (`st.cache_data`) |
| Deployed app shows "Earth Engine is not available" | Missing/incorrect `gee_service_account` secret | Re-check Secrets against `.streamlit/secrets.toml.example`; confirm the service account is Earth-Engine-registered |

## License / data attribution

Contains modified Copernicus Sentinel data, processed via Google Earth
Engine. Sentinel-1/Sentinel-2 data are provided by ESA/Copernicus under
their open data policy.
