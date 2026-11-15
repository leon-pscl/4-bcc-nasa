# NASA Space Apps Challenge — Harmonized Burning Activity Calendar

A high-performance Earth Observation (EO) web application that turns **43+ million MODIS and VIIRS satellite active fire detections (2003–today)** into a unified, harmonized burning activity calendar for **Southeast Asia**.

Instead of streaming tens of gigabytes of raw detection points to the client, the application performs sub-25ms server-side spatiotemporal analytics using **embedded DuckDB over partitioned Apache Parquet**, delivering instant historical heatmaps, seasonal distributions, and real-time anomaly tracking.

---

## Key Features

- **Multi-Sensor Harmonization (2003–Present):**
  Harmonizes **Terra and Aqua MODIS (Collection 6.1)** with **Suomi-NPP, NOAA-20, and NOAA-21 VIIRS (375m, Collection 2)**. Uses Empirical Bayes shrinkage ($m = 30$) to calibrate sensor differences, achieving **Pearson correlation $r = 0.997$** and **$-2.7\%$ bias** on independent validation years.
- **Burning Activity Calendar:**
  A 24-year matrix (2003–2026) displaying monthly fire activity, baseline percentiles (p25, median, p75), and real-time anomaly percentage comparisons against historical records.
- **Interactive Geospatial Map:**
  Dynamic $0.05^\circ$ (~5.5 km) fire density heatmaps with starter presets (Central Kalimantan, Northern Thailand, Luzon) and custom bounding-box drag-to-draw tools.
- **Compass Coordinates Layout:**
  Intuitive directional boundary inputs (North, South, East, West) synchronized with on-map edge badges.
- **Actionable Analytics & Export:**
  Instant comparisons of current burning activity against historical baselines, land cover breakdown (Forest, Farmland, Other), and one-click downloads for harmonized CSV tables and high-resolution chart PNGs.

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│ NASA Earthdata FIRMS Archives (43M+ Hotspot Detections)│
│ • MODIS C6.1 (2003–2026)                               │
│ • VIIRS S-NPP / NOAA-20 / NOAA-21 (2012–2026)          │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Data Processing Pipeline                               │
│ 1. Ingest: CSV -> Hive-partitioned detections.parquet  │
│ 2. Cell-Days: 0.05° spatial binning                    │
│ 3. Harmonize: Empirical Bayes shrinkage (m=30)         │
│               Outputs harmonized_daily/ Parquet        │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Backend API (Python / Flask + DuckDB)                  │
│ • In-memory columnar analytics (<25ms queries)         │
│ • Zero heavy database dependencies (no PostgreSQL)     │
└───────────────────────────┬────────────────────────────┘
                            │ REST API (/api/calendar, /api/map)
                            ▼
┌────────────────────────────────────────────────────────┐
│ Frontend (React 18 + Vite + TypeScript)                │
│ • Leaflet Geospatial Heatmap Layers                    │
│ • Accessible ColorBrewer YlOrRd / RdBu color ramps     │
│ • Full WCAG AA accessibility compliance                │
└────────────────────────────────────────────────────────┘
```

---

## Quickstart (Local Setup Without Docker)

### Prerequisites
* **Python 3.10+** (Python 3.12 recommended)
* **Node.js 18+** & **npm**

---

### 1. Clone the Repository
```bash
git clone https://github.com/leon-pscl/4-bcc-nasa.git
cd 4-bcc-nasa
```

---

### 2. Backend Setup

1. Create and activate a Python virtual environment:
   ```bash
   # Windows (PowerShell)
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables (optional for local data):
   Create a `.env` file in the project root:
   ```env
   DATA_RAW=data/raw
   DATA_PROCESSED=data/processed
   ```

---

### 3. Frontend Setup

1. Navigate to the `frontend` directory and install dependencies:
   ```bash
   cd frontend
   npm install
   ```

2. Build the production frontend distribution:
   ```bash
   npm run build
   cd ..
   ```

---

### 4. Run the Application

You can run the web server in either of two modes:

#### Option A: Production Mode (Recommended)
Flask serves the compiled frontend and API on port `8000`:
```bash
# Windows
$env:FLASK_APP = "app"
python -m flask run --port 8000 --host 0.0.0.0

# Linux / macOS
export FLASK_APP=app
python3 -m flask run --port 8000 --host 0.0.0.0
```
Open **http://localhost:8000** in your browser.

#### Option B: Development Mode (Hot-Reload)
Run Flask on port `8000` in one terminal, and the Vite dev server in another:
```bash
# Terminal 1 (Backend)
python -m flask run --port 8000

# Terminal 2 (Frontend)
cd frontend
npm run dev
```
Open **http://localhost:5173** in your browser (Vite automatically proxies API requests to Flask).

---

## Run it on the cloud (Render)

The same app runs on [Render](https://render.com) on the Standard plan (1 CPU, 2 GB).

- **Build command** — download the release archive and extract it, turning
  Windows backslash entry names into folders:

  ```bash
  curl -fL https://github.com/leon-pscl/4-bcc-nasa/releases/download/v2.0.1/processed_data.zip -o /tmp/processed_data.zip
  python - <<'EOF'
  import pathlib, zipfile
  z = zipfile.ZipFile("/tmp/processed_data.zip")
  for m in z.infolist():
      n = m.filename.replace("\\", "/").strip("/")
      if not n:
          continue
      p = pathlib.Path("/tmp/firecal_data") / n
      if m.is_dir() or m.filename.endswith(("/", "\\")):
          p.mkdir(parents=True, exist_ok=True)
      else:
          p.parent.mkdir(parents=True, exist_ok=True)
          p.write_bytes(z.read(m))
  EOF
  ```

- **Start command**:

  ```bash
  gunicorn -w 1 --threads 4 --timeout 120 -b 0.0.0.0:$PORT app:app
  ```

- **Env**: `DATA_ZIP_URL` (release archive URL) so the app self-provisions the
  data into `/tmp/firecal_data` when the filesystem mount is empty;
  `DATA_PROCESSED=/app/data/processed`; `DUCKDB_WEB_MEMORY_LIMIT=1GB`.

---

## Dataset Ingestion Pipeline

To process raw FIRMS CSV downloads into harmonized Parquet partitions:

1. **Ingest raw CSVs:**
   ```bash
   python -m firecal.ingest.cli --region southeast_asia --files sample-data/*/*.csv
   ```
2. **Aggregate to $0.05^\circ$ cell-days:**
   ```bash
   python -m firecal.cells.cli --region southeast_asia
   ```
3. **Calibrate and Harmonize:**
   ```bash
   python -m firecal.harmonize.cli --region southeast_asia
   ```

---

## Running Automated Tests

* **Backend Unit & Regression Tests (Pytest):**
  ```bash
  pytest tests/
  ```
* **Frontend Component Tests (Vitest):**
  ```bash
  npm --prefix frontend test
  ```

---

## Team & Attribution
Developed for the **NASA International Space Apps Challenge 2026** under the challenge *“MODIS and VIIRS Hot Spots”*.
Data courtesy of NASA Earthdata FIRMS (LANCE) and the MODIS/VIIRS Science Teams.
