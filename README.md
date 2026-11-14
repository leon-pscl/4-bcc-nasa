# NASA Space Apps — harmonized burning activity calendar

A web app that turns 43 million MODIS and VIIRS fire-detection rows (2003–today)
into a harmonized burning-activity calendar for Southeast Asia and the Amazon. It
serves a server-side aggregation (DuckDB over partitioned Parquet) instead of
shipping every detection to the browser.

- **Live data**: MODIS Terra/Aqua, SNPP, NOAA-20, NOAA-21 — calibrated so MODIS
  counts are expressed in VIIRS-equivalent cell-days (shrinkage `k`, `SHRINK_M=30`).
- **Calendar**: 12 months × years matrix with per-month median, p25, p75 across
  the baseline years, anomalies, annual totals and partial-year handling.
- **Map, summary, hotspots export** over bboxes or point+radius (up to 500,000 km²).
- **Methods tab** reports the held-out 2018–2021 validation per region.

## Get a FIRMS MAP_KEY

1. Sign up free at https://firms.modaps.eosdis.nasa.gov/api/map_key (email only).
2. Copy the 32-character key into `.env` (never commit `.env`):
   ```
   FIRMS_MAP_KEY=<your key>
   DATA_RAW=data/raw
   DATA_PROCESSED=data/processed
   ```
3. The key is part of every FIRMS URL — keep it out of logs, commits, tests and
   reports (instructions.md §3, rule 8).

## Run it

```bash
docker compose up --build
```

Open http://localhost:8080. The `web` service serves the built frontend and the API;
the `updater` service runs `pipeline update --all` once a day against the shared
`./data` volume.

`docker-compose` builds two images from the same Dockerfile targets:

- `web` (Flask only) — serves the app and API. **No `rasterio`.**
- `pipeline` (updater, `add-region`, `backfill`) — additionally installs
  `rasterio==1.5.2` for reading the MCD12Q1 GeoTIFF granules in
  `data/raw/landcover/` (used to build `data/processed/cell_cover`). The
  manylinux wheel bundles GDAL; the image adds `libexpat1`, which the wheel
  links but slim images don't ship. Adding a region copies/extends the cover
  aggregation in the pipeline image, not in `web`.

Without Docker:

```bash
pip install -r requirements.txt
# pipeline-only extra, needed for add-region / cell_cover builds:
pip install rasterio==1.5.2
cd frontend && npm ci && npm run build && cd ..
python -m firecal.pipeline update --region southeast_asia   # or --all
flask --app app run --port 8000
```

## Load a region (backfill)

```bash
python -m firecal.pipeline add-region southeast_asia
```

Or draw a box in the UI and run:

```bash
python -m firecal.pipeline backfill --region <name> --bbox W,S,E,N --start YYYY-MM-DD
```

## Keep it current

```bash
python -m firecal.pipeline update --region southeast_asia   # daily
python -m firecal.pipeline update --all --recalibrate       # refit calibration
```

## How harmonization works

MODIS has higher per-cell detection rates than VIIRS for the same fire, so naive
counts are not comparable. For every (region, tile, month) we fit a factor
`k = viirs_celldays / modis_celldays`, shrunk toward the region factor. MODIS
detections are then scaled by `k` and expressed as VIIRS-equivalent cell-days. The
resulting `harmonized_daily` has one row per (cell, local date), so downstream
analytics don't care which sensor produced a detection. Validation on the held-out
years 2018–2021 is reported in the Methods tab.

## Limitations

- Only two regions ship configured: Southeast Asia and the Amazon. Other areas
  need a backfill (`add-region`) and are not in the default coverage list.
- `latest_date` is the last complete local day (both the night and day satellite
  passes). A fetch that runs before the day pass sees only the night pass, so the
  most recent day is not yet shown.
- The map and calendar are capped at 500,000 km² per query.
- NRT data is replaced by standard processing a few months later, so recent
  counts can shift slightly.
- The pipeline has one writer at a time (an OS lock); concurrent runs exit.
- The Amazon archive is not loaded by default; Amazon data must be backfilled.
EOF
echo done