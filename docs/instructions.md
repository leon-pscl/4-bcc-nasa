# Instructions for the coding agent

Read this whole file before writing any code. It explains what we are building, how the
code is split into modules, and the order in which to build them. Work **one stage at a
time** and stop at the end of each stage for review.

Read it together with:

- `docs/frontend-tasks.md`: what each UI element looks like and how it behaves.
- `docs/ui_settings.md`: fonts, colors and style, applied as `frontend-tasks.md` section 2
  describes.

**Which file wins when they disagree:** `frontend-tasks.md` wins on the UI's layout, look and
behavior. This file wins on everything else: contracts, approved dependencies, the working
agreement, tests and the backend.

**Next stage to build:** Stage 0 (section 7).

---

## 1. What we are building

NASA Space Apps challenge: **a harmonized burning activity calendar, based on active fire
hotspots, in a web application**.

The challenge has two parts:

1. **Harmonize MODIS and VIIRS hotspots** from NASA FIRMS into one consistent time series
   from the early 2000s to today. MODIS (Terra/Aqua, ~1 km pixels, since Nov 2000) has the
   long history but is near end of life. VIIRS (375 m pixels, since Jan 2012) has more detail
   and continuity. After harmonization the sensor of origin must no longer matter. The focus
   is on patterns, trends and anomalies.
2. **A web app** that takes the harmonized data as input. A user selects a region and a
   date range, then views and downloads analytics and visualizations of fire activity.

What the web app must provide (from the challenge brief):

- A **burning calendar**: the number of hotspots per month (columns) and year (rows), from
  the early 2000s to today, using **color ramps** (accessible ones) plus the numbers.
- Answers at a glance: which months of the year have more fire, which years had more fire,
  and how the **current month compares with the historical median**.
- **Anomalies** against multi-year averages or medians.
- **Region selection**: draw an area on a map, or type latitude/longitude.
- **Downloads**: a **CSV of the hotspots** found by a search, plus the analytics and
  visualizations.
- Audience: emergency managers, early warning and response teams, scientists, land managers
  and firefighters.

---

## 2. Where the repo is today

### 2.1 A fresh start

Branch `pascual` was reset on 13 Nov 2026 (commit `a5e4cfb`) to start from scratch. The
earlier attempt is still in the history at commit `82a4528`. Use it **for reference only**:
don't restore its files, except `sample-data/` (Stage 0).

What the repo contains now:

| Path | What it is |
|---|---|
| `docs/instructions.md` | This file |
| `docs/frontend-tasks.md` | UI spec: layout, components, behavior, frontend task list |
| `docs/ui_settings.md` | Fonts, colors, style, icon and animation options |
| `docs/dashboard.jpg`, `docs/refs/*.png` | Screenshots of the UI draft |
| `frontend/` | Vite + React 18 + TypeScript (`strict`) app with one component, `MapCard` (below) |
| `Dockerfile`, `docker-compose.yml` | Written for the target layout (section 4). `docker build` fails until `firecal/`, `app.py` and `requirements.txt` exist |
| `.env.example`, `.dockerignore` | Already set up for the target layout |
| `.gitignore` | Covers `.env`, `data/raw/` and `data/processed/`, but **not** `frontend/node_modules/` or `frontend/dist/` (that rule was in a `frontend/.gitignore` the reset deleted). Add them in 6a |

There is **no backend**: no `firecal/`, no `app.py`, no `requirements.txt`, no tests, no data.

**`frontend/` today** (part of Stage 6b, built early):

- `MapCard`: an OpenStreetMap map with a top-left toolbar (zoom in, zoom out, "Draw area",
  "Delete area"), a hand-written drag-to-draw handler (no Leaflet.draw), four N/S/E/W text
  fields kept as strings, and a live km² readout.
- `lib/geo.ts`: `parseEdges`, `areaKm2` (sphere, R = 6371 km), `wrapLon`, `round4`, with
  tests in `lib/geo.test.ts`.
- Still missing: the 6a plumbing (no lint, typecheck or `check` scripts, no API code, no
  tokens), and the rest of 6b (see section 7, Stage 6).
- Styles are inline. They move to CSS Modules when the tokens arrive (6a).
- The current UI doesn't show the 500,000 km² limit message (see section 5, `MAX_AREA_KM2`).

### 2.2 Lessons from the first attempt (don't repeat these)

Backend:

- The old app sent **every detection row** to the browser (853 KB for 2,919 rows). Twenty
  years would be hundreds of MB. Aggregate on the server; only the paged `/api/hotspots`
  returns rows as JSON.
- The old app used **module-level mutable state**, so one user's upload changed the data for
  everyone, and it rewrote a shared `outputs/` folder on every request.
- `app.run(host="0.0.0.0", debug=True)` exposed the Werkzeug debugger, which can run code, to
  the network. Debug mode comes from `FLASK_DEBUG` (default off).
- **Partial-month bug:** the calendar marked the end month as "in progress" for almost every
  end date (it tested `end.month < 12 or end.day < 28`). See Stage 4.
- `/api/summary` skipped the coverage check that `/api/calendar` ran. Every area endpoint
  runs it (Stage 5).
- "This month" depended on the server clock, so results shifted with time zones. See
  section 5, "Which day is today".
- The API had no tests, and the mock files didn't match the contract (the calendar mock had
  no `query.bbox`). See Stage 5.

Frontend:

- Data values went into `innerHTML` unescaped (an XSS risk). Never use
  `dangerouslySetInnerHTML`.
- `Number("-")` is `NaN`, which made Leaflet throw and blanked the page; clearing a field
  turned it into `0`. Keep field values as strings and parse them only to validate.
- There was no Vite proxy, so `/api/*` returned `index.html` in development.
- The API client never checked `res.ok`, and the zod schemas covered only part of each
  response.

### 2.3 How the team gets data by hand (Stage 1a automates this)

The manual process, from the team's data-access guide:

1. Get a free FIRMS `MAP_KEY` at <https://firms.modaps.eosdis.nasa.gov/api/map_key/>. It
   arrives by email. The limit is 5,000 transactions per 10 minutes.
2. Draw a box on <https://bboxfinder.com> with **Coordinate Format = Lng / Lat**. The "Box"
   value is then `W,S,E,N`, which is exactly the order FIRMS expects. With "Lat / Lng"
   selected the order is wrong, and the query silently returns the wrong area.
3. Call the area API once per sensor and save each response as a CSV:
   - `https://firms.modaps.eosdis.nasa.gov/api/area/csv/KEY/MODIS_NRT/121.116028,14.583583,121.643372,15.445738/5`
   - `https://firms.modaps.eosdis.nasa.gov/api/area/csv/KEY/VIIRS_SNPP_NRT/121.116028,14.583583,121.643372,15.445738/5`

With no date at the end of the URL, this returns only **the last 5 days**. The calendar needs
2003 to today, so Stage 1a automates the same call and extends it:

- Use the **standard processing sources** (`MODIS_SP`, `VIIRS_SNPP_SP`) for history.
- Add the optional date: `/api/area/csv/KEY/SOURCE/W,S,E,N/DAY_RANGE/YYYY-MM-DD` returns
  `DATE .. DATE + DAY_RANGE - 1`, and `DAY_RANGE` is **1 to 10**.
- Use the NRT sources only for recent days that standard processing doesn't cover yet. Check
  where each source starts and ends with `/api/data_availability/`.
- Loop over 10-day chunks, stay under the transaction limit, cache every response and resume
  after interruptions.

**In the app, the map's box never triggers a FIRMS download.** Fetching runs offline, once
per area (Stage 1a, then the pipeline in Stage 7). A full 2003-to-today backfill is about
14,000 transactions, or about 35 minutes. The web app only reads the processed files, and a
box outside the fetched areas gets a 422 with the list of covered areas. The browser never
calls FIRMS: the key is part of every FIRMS URL.

### 2.4 Processing rules from the first prototype

The first prototype (`compare.py`, now deleted) got these rules right, and its results were
checked against hand-made reference numbers. Implement them as described here.

**FIRMS CSV columns.**

- MODIS: `latitude, longitude, brightness, scan, track, acq_date, acq_time, satellite,
  instrument, confidence, version, bright_t31, frp, daynight`. `confidence` is a number from
  0 to 100.
- VIIRS: the same, except `bright_ti4` and `bright_ti5` replace `brightness` and `bright_t31`
  (rename them), and `confidence` is a letter: `l`, `n` or `h`.
- Archive (SP) files also have a `type` column (section 5, `KEEP_TYPES`).

**UTC time.** `acq_time` is HHMM as an integer: `18` is 00:18 and `1947` is 19:47. The UTC
datetime is `acq_date` plus those hours and minutes.

**Local solar time.** `local = utc + longitude / 15` hours. The local date is the row's day
(`date_local`).

**Confidence.** Keep the original value in `confidence_raw`, and map it to
`confidence_class`:

| MODIS | VIIRS | Class |
|---|---|---|
| 0–29 | `l` | `low` |
| 30–79 | `n` | `nominal` |
| 80–100 | `h` | `high` |

**Grid cells.** `cell = (floor(lat / GRID_DEG), floor(lon / GRID_DEG))`. Use `floor`, never
truncate: `floor(-17.8757 / 0.05)` is `-358`, but `int()` gives `-357`.

**Reference numbers.** `sample-data/` (restored in Stage 0) holds two FIRMS NRT CSVs for the
East Bolivia box (W −64, S −18, E −60, N −14): `modis.csv` from `MODIS_NRT` and `viirs.csv`
from `VIIRS_SNPP_NRT`. They cover UTC 2026-09-26 00:18 to 2026-10-01 05:55, which is local
days 2026-09-25 to 2026-10-01. With the rules above, and with no confidence or type filters,
they give:

| Check | Value |
|---|---|
| Rows | MODIS 654 (Terra 377, Aqua 277); VIIRS 2,265 (all `N`, i.e. S-NPP); total 2,919 |
| `version` | MODIS `6.1NRT`, VIIRS `2.0NRT` (all NRT) |
| Mean pixel area (`scan × track`) | MODIS 2.33 km², VIIRS 0.21 km² |
| MODIS confidence | low 7, nominal 383, high 264 (1.1% / 58.6% / 40.4%) |
| VIIRS confidence | low 237, nominal 1,971, high 57 (10.5% / 87.0% / 2.5%) |
| Cells, local day 2026-09-27 | MODIS 104, VIIRS 268, both 73, MODIS only 31, VIIRS only 195 |
| Cells, local day 2026-09-28 | MODIS 110, VIIRS 251, both 54, MODIS only 56, VIIRS only 197 |
| 27–28 Sep combined | 59.3% of MODIS cells are also seen by VIIRS |

VIIRS produces about 3.5 times as many rows as MODIS for the same fires, because its pixels
are smaller. That's why the series counts cells, not rows (Stage 2).

---

## 3. Working agreement (follow on every stage)

1. **One stage per session, in order.** Frontend sub-stages (6a–6i) can each be their own
   session.
2. **Start of a stage:** restate the stage goal and list the files you will create or change.
3. **End of a stage:** run `pytest` (and `npm run check` in `frontend/` for Stage 6) and paste
   the summary. Report what changed, any deviations from this file, and open questions.
   **Then stop and wait for approval.** Do not start the next stage on your own.
4. **Contracts (section 6) are the interface between stages.** A stage may only read the
   outputs of earlier stages through their contracts. A stage never imports from a later
   stage. To change a contract, update this file and the tests in the same change, and ask
   first.
5. **Ask before** you:
   - change any default in section 5 (Decisions)
   - add a Python dependency not listed in Stage 0
   - add a frontend dependency that isn't on the approved list (section 4), or switch
     frameworks (for example to Next.js)
   - delete files, other than the ones a stage tells you to delete
   - restore files from the old commit `82a4528`, other than `sample-data/`
6. **Code style:** the repo owner is learning. Use small, well-commented functions, type
   hints, and pure functions where possible. Put CLI wrappers in separate `cli.py` files.
7. **Tests:** use `pytest`. Tests never touch the network. Test inputs are small fixtures in
   `tests/fixtures/` (plus `sample-data/`). Every function that takes a date must accept
   `today` as a parameter, so tests don't depend on the clock.
8. **Git:** use one branch per stage (`stage-0-groundwork`, `stage-1a-fetch`, and so on) with
   small commits. Never commit `data/raw/`, `data/processed/`, `.env` or a FIRMS `MAP_KEY`.
   The key is part of every FIRMS URL, so **never print, log or raise a full URL**. Replace
   the key with `***` everywhere: logs, exceptions, the manifest and test output.
9. **Synthetic data must always be labeled.** Any dataset made by `firecal/devdata.py` sets
   `synthetic: true` in `coverage.json`, and the UI shows a visible "SYNTHETIC DATA" banner
   whenever it is used.

---

## 4. Tech stack and target layout

| Layer | Choice |
|---|---|
| Data pipeline + API | Python 3.12, Flask, pandas, DuckDB, pyarrow, requests, matplotlib (calendar PNG), gunicorn (production server) |
| Data storage | Parquet files in `data/processed/`, queried with DuckDB (embedded, no database server) |
| Frontend | **React + TypeScript + Vite**, a single-page app. Not Next.js: there is no Node server at runtime |
| Map | Leaflet through `react-leaflet`. No Leaflet.draw: the draw tool is hand-written |
| Charts | Chart.js through `react-chartjs-2` |
| Server data fetching | `@tanstack/react-query` (caching, loading and error states) |
| API boundary types | `zod` schemas in `frontend/src/api/schemas.ts`; TypeScript types are inferred from them (`z.infer`) |
| Frontend tests | Vitest + Testing Library (`@testing-library/react`, `@testing-library/user-event`, `jsdom`) |
| Lint | ESLint with `typescript-eslint` and `eslint-plugin-jsx-a11y`; TypeScript `strict: true` |
| Styling | CSS Modules (built into Vite), with the tokens from `frontend-tasks.md` section 2. No UI kit or Tailwind unless the owner asks |
| Runtime | One Docker image. A Node build stage compiles the frontend; the final image is Python only and Flask serves `frontend/dist/` |

**Approved frontend dependencies:** `react`, `react-dom`, `typescript`, `vite`,
`@vitejs/plugin-react`, `leaflet`, `react-leaflet`, `@types/leaflet`, `chart.js`,
`react-chartjs-2`, `@tanstack/react-query`, `zod`, `vitest`, `@testing-library/react`,
`@testing-library/user-event`, `@testing-library/jest-dom`, `jsdom`, `eslint`,
`typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-jsx-a11y`. Ask before adding
anything else (for example an icon library: `frontend-tasks.md` section 2.2). Use the current
Node.js LTS, pinned in `frontend/.nvmrc` and the Dockerfile.

Development setup:

- `flask --app app run --port 8000` serves the API.
- `npm run dev` (Vite, port 5173) serves the UI and proxies `/api` and `/health` to port
  8000, so no CORS setup is needed.
- In production, `npm run build` writes `frontend/dist/`, and Flask serves it at `/`.

```
firecal/                      Python package (all backend code)
  __init__.py
  config.py                   Settings (section 5) + env overrides
  contracts.py                column lists, dtypes and validate_*() helpers (section 6)
  devdata.py                  synthetic multi-year dataset for development (Stage 3)
  pipeline.py                 Stage 7: runs fetch -> ingest -> cells -> harmonize in one command
  fetch/                      Stage 1a: FIRMS API -> raw CSV cache (download only, no parsing)
    client.py  plan.py  ratelimit.py  cache.py  cli.py
  ingest/                     Stage 1b: FIRMS CSV -> detections
    firms_csv.py  store.py  cli.py
  cells/                      Stage 2: detections -> cell-days
    grid.py  celldays.py  cli.py
  harmonize/                  Stage 3: cell-days -> harmonized daily series
    calibrate.py  apply.py  validate.py  cli.py
  analytics/                  Stage 4: queries for a region + date range
    area.py  query.py  calendar.py  summary.py  maps.py  export.py
  web/                        Stage 5: Flask app factory + routes
    __init__.py  params.py  routes.py  images.py
app.py                        thin entry point: app = create_app()
requirements.txt  requirements-dev.txt  pytest.ini
sample-data/                  modis.csv + viirs.csv, the reference sample (section 2.4)
scripts/make_mocks.py         Stage 5: writes frontend/public/mock/*.json
frontend/                     Stage 6: React + TypeScript + Vite
  package.json  package-lock.json  vite.config.ts  tsconfig.json  eslint.config.js  .nvmrc
  index.html
  public/mock/*.json          example API responses (generated by the backend in Stage 5)
  src/
    main.tsx  App.tsx  App.module.css  index.css (tokens)
    api/
      schemas.ts              zod schemas mirroring C6 (the frontend's copy of the contract)
      client.ts               the ONLY module that calls fetch; validates every response with zod
      hooks.ts                react-query hooks: useCoverage, useCalendar, useSummary, useMap, useHotspots, useMethods
    state/
      urlState.ts             query state <-> URL hash (frontend-tasks.md section 4)
      useAppState.ts          React context + useReducer around urlState (no Redux, no Zustand)
    lib/
      colors.ts               ramps (section 8), quantile bins, legend data, contrast text color
      geo.ts                  bbox validation, area km2, point+radius (same rules as firecal/analytics/area.py)
      format.ts               number/date/percent formatting
    components/               one folder per component: Component.tsx + .module.css + .test.tsx
      AppHeader/  SyntheticBanner/  MapCard/  SidePanel/  ComparisonsPanel/  Watchlist/
      MethodsPanel/  BurningCalendar/  HotspotTable/  Downloads/
    test/setup.ts
data/raw/firms/               raw API responses + manifest.jsonl, written by Stage 1a (git-ignored)
data/raw/manual/              CSVs downloaded by hand, if any (git-ignored)
data/processed/               Parquet outputs + json metadata (git-ignored)
tests/
  fixtures/
```

---

## 5. Decisions (defaults; ask before changing)

All of these live in `firecal/config.py` as one `Settings` dataclass, so they can be changed
in one place.

| Setting | Default | Why |
|---|---|---|
| `SERIES_START` | `2003-01-01` | First full year with Aqua MODIS (Aqua data starts mid-2002) |
| `MODIS_PLATFORMS` | `("Aqua",)` | Aqua and Suomi NPP both pass over around 13:30 local time, the closest MODIS/VIIRS pair |
| `VIIRS_PLATFORMS` | `("SNPP",)` | Single VIIRS platform for consistency; NOAA-20/21 add overpasses and would raise counts |
| `SWITCH_DATE` | `2012-02-01` | First full month of VIIRS 375 m (available from 20 Jan 2012) |
| `GRID_DEG` | `0.05` | Shared grid, same as the first prototype (~5.5 km) |
| `TILE_DEG` | `1.0` | Spatial unit for calibration factors |
| `CONFIDENCE_KEEP` | `("nominal", "high")` | Same rule for both sensors; low-confidence detections dropped |
| `KEEP_TYPES` | `(0,)` | Archive files flag static sources (volcanoes, gas flares) in a `type` column; keep presumed vegetation fires only. If the column is missing (NRT data), keep the row |
| `DAY_BASIS` | `"local_solar"` | `local = utc + longitude / 15` hours (section 2.4) |
| `CALIBRATION_YEARS` | `(2013, 2017)` inclusive | Years used to fit MODIS-to-VIIRS factors |
| `VALIDATION_YEARS` | `(2018, 2021)` inclusive | Held-out years to test the factors (MODIS orbits drift late in the mission, so check per-year metrics before extending either window) |
| `MIN_CALIBRATION_CELLDAYS` | `30` | Below this, fall back to a broader calibration level |
| `MIN_BASELINE_YEARS` | `5` | Fewer complete years than this triggers a baseline warning |
| `MAX_AREA_KM2` | `500_000` | Larger areas are rejected. About 16,000 grid cells at 0.05°, under `MAX_MAP_CELLS`, so the map can show full detail. **Open:** the current UI dropped its limit message; the owner decides whether to keep the limit (and restore the message) or change it |
| `MAX_MAP_CELLS` | `20_000` | Above this, the map aggregates to a coarser grid |
| `REGIONS` | `{"bolivia_east": (-64, -18, -60, -14), "luzon_example": (121.116028, 14.583583, 121.643372, 15.445738)}` | Demo regions (W, S, E, N). `luzon_example` is the box from the team's data-access guide |
| `FIRMS_BASE_URL` | `https://firms.modaps.eosdis.nasa.gov` | |
| `FIRMS_SOURCES` | MODIS: `MODIS_SP` / `MODIS_NRT`; VIIRS: `VIIRS_SNPP_SP` / `VIIRS_SNPP_NRT` | SP for history, NRT only after SP ends |
| `FIRMS_DAY_RANGE_MAX` | `10` | API limit per request |
| `FIRMS_TX_BUDGET` | `4000` per `600` s | Stays below the 5,000 per 10 minutes key limit. Count each requested day as one transaction (worst case; FIRMS says multi-day requests may count as several) |
| `FIRMS_RETRIES` | `5`, exponential backoff from 5 s | FIRMS sometimes returns 504s |
| `NRT_REFRESH_DAYS` | `7` | NRT chunks ending within this many days of today are always fetched again, because NRT data keeps changing |
| `VIIRS_SP_START` | `2012-01-20` | First date of VIIRS 375 m data; never request VIIRS before this |
| UI unit label | "Hotspots (harmonized)" | The Methods tab explains the unit: one fire cell-day in VIIRS-equivalent terms |

Paths (`DATA_RAW`, `DATA_PROCESSED`) and `FIRMS_MAP_KEY` come from environment variables, with
defaults `data/raw` and `data/processed`. `.env.example` already exists.

**Which day is "today".** The analytics functions take `today` as a parameter (section 3).
In the API, `today` is the **latest data date** of the coverage region the area falls in
(`latest_date` in `coverage.json`; if the area overlaps several regions, the earliest of
their latest dates). It is never the server clock. This keeps "this month vs. median" stable
across time zones: a browser in Manila (UTC+8) can be a day ahead of a UTC server. An `end`
later than the latest data date is rejected with a 400.

---

## 6. Data contracts (the interfaces between stages)

Every table is stored as Parquet in `DATA_PROCESSED`. `firecal/contracts.py` defines the
columns and dtypes for each table and a `validate_<table>(df)` function that raises a clear
error on any mismatch. Each writer validates before saving, and each reader validates after
loading. Every writer saves to a temporary file and then renames it, so readers (the web app
during a daily update) never see a half-written file.

### C0 raw cache `data/raw/firms/` (written by Stage 1a)

- One file per request: `data/raw/firms/<SOURCE>/<bbox_slug>/<YYYY-MM-DD>_<day_range>d.csv`.
  `bbox_slug` is the four numbers rounded to 4 decimals and joined with `_`; minus signs
  become `m` (for example `m64_m18_m60_m14`). The file content is the response body exactly
  as received.
- Write each file atomically (write to `.tmp`, then rename), so an interrupted run never
  leaves half a file.
- `manifest.jsonl` has one line per completed request:
  `{source, bbox:[W,S,E,N], date, day_range, rows, sha256, fetched_at, path}`. It never
  contains the key or the full URL.
- A response with only the header row is a valid result (no fires). It is saved and
  recorded, so it isn't fetched again.

### C1 `detections.parquet` (written by Stage 1b)

| column | type | notes |
|---|---|---|
| `uid` | string | hash of platform + lat + lon + UTC datetime; unique |
| `sensor` | string | `MODIS` or `VIIRS` |
| `platform` | string | `Terra`, `Aqua`, `SNPP`, `NOAA20`, `NOAA21` |
| `processing` | string | `SP` (standard) or `NRT` (near real time), from the `version` suffix |
| `latitude`, `longitude` | float64 | |
| `acq_datetime_utc` | timestamp | from `acq_date` + `acq_time` (HHMM; section 2.4) |
| `date_local` | date | local solar date (section 2.4) |
| `daynight` | string | `D` or `N` |
| `confidence_raw` | string | original value |
| `confidence_class` | string | `low`, `nominal`, `high` (section 2.4) |
| `frp` | float64 | |
| `scan`, `track` | float64 | km |
| `brightness`, `bright_t31` | float64 | VIIRS `bright_ti4`/`bright_ti5` renamed |
| `type` | Int8 (nullable) | null when the source has no `type` column |
| `version` | string | |
| `source_file` | string | |

Also written: `coverage.json`, a list of `{name, bbox:[W,S,E,N], start, end, platforms,
latest_date, synthetic}`. Coverage is the **requested** area and dates, not the extent of
the data found.

### C2 `celldays.parquet` + `celldays.meta.json` (written by Stage 2)

One row per (cell, local date, platform) with at least one detection that passes the filters.

| column | type |
|---|---|
| `cell_lat_idx`, `cell_lon_idx` | int32: `floor(lat / GRID_DEG)`, `floor(lon / GRID_DEG)` |
| `tile_id` | string: `f"{floor(lat / TILE_DEG)}_{floor(lon / TILE_DEG)}"` |
| `date_local` | date |
| `platform` | string |
| `n_detections` | int32 |
| `frp_sum` | float64 |

`celldays.meta.json` records the grid, tile size, filters used, build time and source row
count. Later stages compare it with the current `Settings` and refuse to run, with a clear
message, if they don't match.

### C3 `calibration.parquet` (written by Stage 3)

| column | type | notes |
|---|---|---|
| `tile_id` | string | or `ALL` |
| `month` | int8 | 1–12, or 0 for all months |
| `k` | float64 | VIIRS cell-days / MODIS cell-days |
| `modis_celldays`, `viirs_celldays` | int64 | sample behind `k` |
| `level` | string | `tile_month`, `tile`, `all_month`, `all` |

### C4 `harmonized_daily.parquet` (written by Stage 3)

| column | type | notes |
|---|---|---|
| `cell_lat_idx`, `cell_lon_idx` | int32 | |
| `tile_id` | string | |
| `date_local` | date | |
| `value` | float64 | VIIRS-equivalent cell-days (1.0 for a VIIRS cell-day, `k` for a MODIS one) |
| `basis` | string | `viirs`, `modis_scaled`, `modis_gapfill` |

**No `sensor` or `platform` column.** This is the table every analysis reads.

### C5 `validation.json` (written by Stage 3)

Metrics, by year and overall, for calibration years (in-sample) and validation years
(held out): Pearson r of monthly totals, bias % = (Σscaled − Σviirs) / Σviirs, and median
absolute % error over months where VIIRS ≥ 10. Also includes the monthly series behind the
metrics, so the Methods tab can chart them: `monthly_viirs` (S-NPP cell-days) and
`monthly_modis`, which is **Aqua × k (scaled)**, not raw MODIS.

### C6 API responses (written by Stage 5)

Query parameters shared by all area endpoints:

- an area, either `bbox=W,S,E,N` or `point=LAT,LON&radius_km=R`
- `start=YYYY-MM-DD&end=YYYY-MM-DD`

Errors return `{"error": "...", "field": "..."}` with HTTP status 400 (bad input) or 422 (no
data for this area; the response also lists the covered areas).

`GET /api/calendar`

```json
{
  "query": {"bbox": [-64, -18, -60, -14], "start": "2003-01-01", "end": "2026-11-10", "area_km2": 190127},
  "unit": "Hotspots (harmonized)",
  "years": [2003, 2004, "...", 2026],
  "values": [[12.0, 3.5, "... 12 numbers or null"], "... one list per year"],
  "partial": {"year": 2026, "month": 11, "through_day": 10},
  "monthly_median": ["12 numbers"],
  "monthly_p25": ["12 numbers"],
  "monthly_p75": ["12 numbers"],
  "anomaly": [["same shape as values"]],
  "anomaly_pct": [["same shape as values; null when median is 0"]],
  "annual_totals": ["one per year"],
  "partial_years": [2026],
  "baseline_years": [2003, 2025],
  "baseline_warning": null,
  "coverage_warning": null,
  "synthetic": false
}
```

For a point query, `query` has `point` and `radius_km` in place of `bbox`.

`GET /api/summary`

```json
{
  "total": 123456.0,
  "peak_month": {"year": 2010, "month": 8, "value": 9876.0},
  "peak_year": {"year": 2010, "value": 34567.0},
  "current_month": {"year": 2026, "month": 11, "through_day": 10, "value": 210.0,
                    "median_same_span": 150.0, "pct_vs_median": 40.0},
  "latest_data_date": "2026-11-10",
  "synthetic": false
}
```

`GET /api/map` (optional `month=YYYY-MM` to focus on one month)

```json
{"grid_deg": 0.05, "aggregated_to": null, "cells": [{"lat": -16.025, "lon": -61.975, "value": 12.0}]}
```

Other endpoints:

- `GET /api/hotspots?page=1&page_size=100` returns paged detection rows as JSON
  (`page_size` ≤ 500).
- `GET /api/hotspots.csv?all_sensors=0` streams the hotspot CSV.
- `GET /api/calendar.csv` returns the calendar matrix as CSV.
- `GET /api/calendar.png` returns the calendar as an image.
- `GET /api/coverage` returns the contents of `coverage.json`.
- `GET /api/methods` returns a calibration summary plus `validation.json`.
- `GET /health` returns a status check.

---

## 7. Stages

Order: 0 → 1a → 1b → 2 → 3 → 4 → 5 → 6a–6i → 7. Stage 6a and the rest of 6b don't need the
backend, so the owner may schedule them earlier. The other frontend sub-stages need the
Stage 5 mocks.

### Stage 0: Groundwork

Goal: the backend skeleton, settings, contracts and test setup.

- Create the `firecal/` package skeleton, `config.py` (section 5), `contracts.py`
  (section 6, with validators), `tests/`, `pytest.ini`.
- `requirements.txt` (runtime): `flask`, `pandas`, `numpy`, `duckdb`, `pyarrow`, `requests`,
  `matplotlib`, `gunicorn`. Pin versions. `requirements-dev.txt`: `pytest`.
  - Check that the pinned set installs together on `python:3.12-slim` (the Docker base
    image). If the pins conflict, fix them and say so in your report.
  - Don't add an HTTP mocking library; tests inject a fake transport (Stage 1a).
- `Settings` loads `.env` if it exists. A few lines of code are enough, so no extra
  dependency.
- Restore the sample files: `git checkout 82a4528 -- sample-data/`. They are the reference
  for Stages 1b and 2 (section 2.4).

Done when:

- `pytest` passes: contract validator tests (a good frame passes; a missing column, a wrong
  dtype and a `sensor` column in C4 each fail with a clear message) and a `Settings` test
  (defaults, and an override from the environment).
- `sample-data/modis.csv` and `sample-data/viirs.csv` are back.

### Stage 1a: Fetch (FIRMS API → C0)

Goal: automate the team's manual workflow (section 2.3) and extend it to the full history.
This module only downloads and caches. It never parses rows beyond checking the header.

- `client.py`: `FirmsClient(map_key, base_url, transport=requests.get, timeout=120)`.
  - `area_csv(source, bbox, day_range, date=None) -> str`: calls
    `/api/area/csv/{key}/{source}/{W,S,E,N}/{day_range}[/{date}]`.
  - `data_availability(source="all") -> list[dict]`: calls
    `/api/data_availability/csv/{key}/{source}` (start and end date per source).
  - `key_status() -> dict`: current transactions and limit for the key. The link is in the
    MAP_KEY email ("view status"); confirm the URL and response fields against a real call.
  - **Check every response:** the first line must contain `latitude` and `acq_date`.
    Otherwise raise `FirmsError` with the first 200 characters of the body. FIRMS can return
    plain-text errors such as an invalid key or an exceeded limit, so don't trust the HTTP
    status alone.
  - Retry 5xx responses and timeouts with exponential backoff (`FIRMS_RETRIES`). Never retry
    an invalid key.
  - Replace the key with `***` in every message, exception and log line.
  - `transport` is injected so tests can pass a fake. Tests never use the network.
- `plan.py`: `build_plan(bbox, start, end, availability, settings) -> list[Chunk]` (pure
  function). A `Chunk` is `(source, bbox, date, day_range)`.
  - For each sensor, use the SP source for dates up to its last available date, then the NRT
    source from the next day up to `end`.
  - VIIRS never starts before `VIIRS_SP_START`.
  - Split into chunks of at most `FIRMS_DAY_RANGE_MAX` days, aligned to the start date.
    Chunks never overlap and together cover the range exactly.
  - Skip chunks already in the manifest. NRT chunks that end within `NRT_REFRESH_DAYS` of
    today are always fetched again.
  - When SP becomes available for dates that were cached as NRT, plan the SP chunks. Stage 1b
    then replaces the NRT rows.
- `ratelimit.py`: a token-bucket limiter using `FIRMS_TX_BUDGET`. A chunk costs `day_range`
  transactions (worst case). It sleeps when the budget runs out and uses an injectable clock
  so tests run instantly. Before a long run, and every 500 chunks, call `key_status()` and
  pause if the key is near its limit.
- `cache.py`: atomic writes, manifest append and "already fetched?" lookups (C0).
- `cli.py`:
  - `python -m firecal.fetch status`: key status (with the key hidden) plus data
    availability per source.
  - `python -m firecal.fetch backfill --region bolivia_east [--start 2003-01-01] [--end YYYY-MM-DD] [--dry-run]`:
    first prints the number of chunks per source, the estimated transactions and the
    estimated time, then fetches. `--dry-run` stops after printing.
  - `python -m firecal.fetch update --region bolivia_east`: everything from the last cached
    date to today (NRT, plus any SP that has newly become available).
  - Instead of `--region`, `--bbox W,S,E,N --name myarea` is accepted, in the same `W,S,E,N`
    order FIRMS uses. This is how a box drawn on the app's map gets fetched. `--name` also
    adds the area to `coverage.json` when Stage 1b ingests it.
  - Reads `FIRMS_MAP_KEY` from the environment. If it's missing, exits with a message that
    points to the MAP_KEY sign-up page.
- Size estimate to show in the report: the full `bolivia_east` backfill is about 8,600 MODIS
  days (2003 to the end of SP) plus about 5,300 VIIRS days (from 2012-01-20). That's roughly
  14,000 transactions in the worst case, or about 35 minutes at 4,000 per 10 minutes. It
  only runs once per area, because of the cache.

Done when (all without network, using a fake transport and a fake clock):

- **Plan:** `bolivia_east` from 2003-01-01 to 2026-11-10, with a fake availability where SP
  ends on 2026-06-30:
  - no chunk is longer than 10 days and chunks don't overlap
  - per source, the chunks cover the requested dates exactly
  - VIIRS starts on 2012-01-20
  - NRT starts on 2026-07-01
- **Client:**
  - a body that isn't CSV raises `FirmsError`
  - a header-only body is accepted as 0 rows
  - a 504 followed by a success is retried and succeeds
  - an invalid-key body is not retried
  - **the fake key string never appears** in any exception, log record or manifest line
    (assert this in the test)
- **Resume:** a run that fails on chunk N, when run again, fetches only chunk N onward. A
  third run makes zero requests (except NRT refresh chunks).
- **Rate limit:** with a budget of 20 and 10-day chunks, the third chunk waits for the fake
  clock.
- **Dry run:** prints counts and estimates and makes zero requests.
- **Manual check (the owner runs this with a real key):**
  - `python -m firecal.fetch status`
  - `python -m firecal.fetch backfill --region luzon_example --start 2024-01-01 --end 2024-01-31`
  - then Stage 1b ingest on the result

### Stage 1b: Ingest (C0 or manual CSV → C1)

Goal: turn any FIRMS CSV (from the Stage 1a cache or downloaded by hand) into the detections
table.

- `firms_csv.py`: `read_firms_csv(path) -> DataFrame` in C1 shape.
  - Detect the sensor from the columns (`bright_ti4` means VIIRS; `brightness` means MODIS).
    Rename the VIIRS brightness columns.
  - Map `satellite` values to `platform`. Expected spellings: MODIS `Terra`/`T`, `Aqua`/`A`;
    VIIRS `N` → `SNPP`, `1`/`N20` → `NOAA20`, `N21`/`2` → `NOAA21`. **Check these against the
    real files you are given.** Raise an error that lists any unknown values; never guess.
  - `processing` is `NRT` if `version` ends with `NRT`, otherwise `SP`.
  - Timestamps, local solar date and confidence follow section 2.4.
- `store.py`: `merge_into_store(new_df, store_path) -> DataFrame`
  - For each (platform, UTC date) that has any `SP` rows, drop that day's `NRT` rows. Standard
    data replaces NRT about 5 months later.
  - Remove duplicates by `uid`. Validate, then write Parquet.
  - Update `coverage.json`.
- `cli.py`:
  - `python -m firecal.ingest --region bolivia_east` ingests every manifest entry (C0) whose
    bbox matches the region and that hasn't been ingested yet. Keep an ingested-files log
    next to the store.
  - `python -m firecal.ingest --region bolivia_east data/raw/manual/*.csv` ingests files
    downloaded by hand.
  - `--bbox W,S,E,N --name myarea` works in place of `--region`.
- Inputs: the Stage 1a cache (the normal path), FIRMS Archive Download CSVs, the yearly
  country CSVs, or the two sample files. This stage never calls the network.
- The `source_file` column records the cache path (or the manual file name), never a URL.

Done when:

- Ingesting `sample-data/` matches section 2.4: 2,919 rows (Terra 377, Aqua 277, SNPP 2,265),
  all `NRT`; VIIRS confidence classes low 237, nominal 1,971, high 57; MODIS low 7.
- Running the same ingest twice gives the same row count.
- Tests cover: SP replaces NRT for the same platform and date; NRT is kept on dates with no SP;
  unknown satellite values raise an error; VIIRS columns are renamed; negative coordinates work;
  `acq_time` values 18 and 1947 give 00:18 and 19:47.

### Stage 2: Cell-days (C1 → C2)

Goal: count fire **cell-days** instead of raw detections (section 2.4 explains why).

- `grid.py`: cell index and tile id helpers. Use `floor`: `floor(-17.8757 / 0.05) = -358`.
- `celldays.py`: `build_celldays(detections, settings) -> DataFrame` (pure function). Apply the
  confidence and `type` filters, then group by (cell, `date_local`, platform). Keep all
  platforms; Stage 3 chooses which to use.
- `cli.py`: `python -m firecal.cells` writes C2 and its meta file.

Done when:

- With the filters turned off (all confidence classes, all types), the sample matches
  section 2.4:
  - 2026-09-27: MODIS (Terra ∪ Aqua) 104 distinct cells, VIIRS 268, shared 73.
  - 2026-09-28: shared 54, MODIS only 56, VIIRS only 197.
- `celldays.meta.json` is written, and a test shows that a mismatched meta file is refused.

### Stage 3: Harmonization (C2 → C3, C4, C5)

Goal: one sensor-free daily series per cell.

- `calibrate.py`: `fit_calibration(celldays, settings) -> DataFrame` (C3).
  - Use **only** the calibration years, Aqua vs. SNPP.
  - `k = Σ SNPP cell-days / Σ Aqua cell-days` (ratio of sums).
  - Fallback order when `modis_celldays < MIN_CALIBRATION_CELLDAYS`: tile × month → tile →
    all tiles × month → all tiles. Record the level used.
- `apply.py`: `build_harmonized(celldays, calibration, settings) -> DataFrame` (C4).
  - Drop dates before `SERIES_START`.
  - `SERIES_START ≤ date < SWITCH_DATE`: Aqua cell-days with `value = k(tile, month)`,
    `basis = modis_scaled`.
  - `date ≥ SWITCH_DATE`: SNPP cell-days with `value = 1.0`, `basis = viirs`.
  - **Gap fill:** on dates ≥ `SWITCH_DATE` where SNPP has zero detections across the whole
    coverage area but Aqua has some, treat it as a VIIRS outage. Use Aqua × k with
    `basis = modis_gapfill`.
- `validate.py`: `validate(celldays, calibration, settings) -> dict` (C5). Compare Aqua × k
  with SNPP in both the calibration and validation years.
- `cli.py`: `python -m firecal.harmonize`. If the calibration years aren't in the data (for
  example, with only the 7-day sample), stop with a clear message. Never silently use a
  default `k`.
- `firecal/devdata.py`: `python -m firecal.devdata --region bolivia_east` generates a
  **labeled synthetic** C2 dataset for 2003 to today. It has seasonality (peak Aug–Oct), a
  known per-tile ratio between SNPP and Aqua, and noise. Stages 4–6 can then be developed
  before the real archive is downloaded.

Done when:

- In a synthetic test where tile A has SNPP = 2.5 × Aqua and tile B has 1.5 × (with noise),
  the fitted `k` is within ±5% for both tiles. Validation r > 0.9 and |bias| < 5%.
- A fallback test gives the parent `k` and the correct `level`.
- A switch-date test and a gap-fill test pass.
- C4 has no `sensor` or `platform` column (enforced by the contract validator).
- C5's `monthly_modis` is Aqua × k (a test checks it against the hand-computed value).
- On real data, include `validation.json` metrics in your stage report.

### Stage 4: Analytics (C4 + C1 → Python results)

Goal: pure functions that answer every question the UI asks. Use DuckDB over the Parquet
files. Every function takes `today` (section 5, "Which day is today").

- `area.py`:
  - An `Area` dataclass, with `from_bbox(w, s, e, n)` and `from_point(lat, lon, radius_km)`.
  - Validation: `-180 ≤ W < E ≤ 180` (no crossing the antimeridian), `-90 ≤ S < N ≤ 90`,
    radius 1–500 km, area ≤ `MAX_AREA_KM2`.
  - `area_km2` on a sphere: `R² × (sin N − sin S) × (E − W in radians)`, with R = 6371.0 km.
    A point area is `π × radius²`. The frontend's `lib/geo.ts` uses the same formulas.
  - A cell is inside if its **center** is inside. West and south edges are inclusive; east and
    north are exclusive. Point + radius uses haversine distance to the cell center.
- `calendar.py`: `calendar_matrix(area, start, end, today) -> dict` (C6 calendar shape).
  - Sum `value` per year and month. Months entirely outside the range are `null`.
  - **`partial`** is set only when `end` is before the last day of its month:
    `{year, month, through_day: end.day}`. Otherwise it is `null`.
  - **Baseline years** = complete years inside the range, excluding the current year. Set a
    warning if there are fewer than `MIN_BASELINE_YEARS`.
  - Monthly median, 25th and 75th percentiles across the baseline years.
  - `anomaly = value − median`; `anomaly_pct = 100 × anomaly / median` (null when median = 0).
- `summary.py`: `summary(area, start, end, today) -> dict` (C6 summary shape).
  - Peak year uses complete years only.
  - **Current month is partial:** `current_month` covers day 1 of `today`'s month through
    `today`, compared with the median of the **same day span** in the baseline years. It is
    `null` when `today` is outside `[start, end]`.
- `maps.py`: `map_cells(area, start, end, month=None) -> dict`. If there are more than
  `MAX_MAP_CELLS` cells, aggregate to a 5× coarser grid and set `aggregated_to`.
- `export.py`:
  - `hotspot_rows(area, start, end, all_sensors=False) -> Iterator[DataFrame]`.
  - By default, export the detections that **feed the harmonized series** for each date
    (Aqua before the switch, SNPP after, including gap-fill days), with the same filters.
    `all_sensors=True` exports every detection.
  - Columns: `date_local, acq_datetime_utc, latitude, longitude, confidence_class, frp,
    daynight, sensor, platform, processing`.
  - Yield chunks, so large exports stream.

Done when:

- Unit tests on a small, hand-made C4 fixture (3 cells × 3 years) match matrices, medians,
  anomalies and totals that are worked out by hand in the test file.
- Edge tests pass:
  - a cell center on the boundary
  - point + radius
  - the area limit, and an antimeridian bbox (rejected)
  - `area_km2` for the `bolivia_east` box is 190,127 km² (rounded)
  - `partial`: `end=2024-01-31` gives `null`; `end=2026-11-12` gives
    `{year: 2026, month: 11, through_day: 12}`
  - the baseline warning
  - `current_month` is `null` when `today` is outside the range
- On the synthetic `bolivia_east` dataset, `calendar_matrix` for the full record runs in
  under 2 s.

### Stage 5: API (Flask)

Goal: serve Stage 4 over HTTP with the C6 shapes.

- `firecal/web/__init__.py`: `create_app(settings=None)` app factory. The root `app.py` is
  `from firecal.web import create_app; app = create_app()`.
- `params.py`: parse and validate query parameters into an `Area` plus dates. Invalid input
  returns 400 with `field`. An `end` later than the latest data date is a 400 on `end`.
- `routes.py`: every endpoint in C6.
  - No module-level mutable state. Open DuckDB read-only (one connection per request or per
    thread).
  - **Every area endpoint** (calendar, summary, map, hotspots, the CSVs and the PNG) runs the
    same coverage check: an area outside every coverage returns 422 with the coverage list; a
    partial overlap returns 200 with `coverage_warning`.
  - `today` comes from coverage, never the server clock (section 5).
  - CSV downloads stream from a generator, with
    `Content-Disposition: attachment; filename=hotspots_<W>_<S>_<E>_<N>_<start>_<end>.csv`.
- `images.py`: `/api/calendar.png` with matplotlib. Use the same color ramps as the UI
  (section 8), with the numbers drawn in the cells.
- Debug mode comes from `FLASK_DEBUG` (default off).
- **Serve the built frontend:**
  - `/` returns `frontend/dist/index.html`, and `/assets/*` serves `frontend/dist/assets/`.
  - Any other path that isn't `/api/*` or `/health` returns `index.html`, so client-side
    routes work.
  - If `frontend/dist/` doesn't exist yet, `/` returns a short text page that says to run
    `npm run build` (or to use `npm run dev`).
- `scripts/make_mocks.py` writes example responses from the synthetic dataset to
  `frontend/public/mock/*.json`: one file per endpoint, plus 400 and 422 error examples.
  Every field in C6 is present (including `query.bbox`).

Done when:

- Flask test client tests cover every endpoint: success, 400 and 422 cases, including a 422
  from `/api/summary`.
- `/api/calendar` is under 50 KB for the full record.
- The only endpoint that returns detection rows as JSON is the paged `/api/hotspots`.
- Mock files are generated, and a Python test validates each one against the C6 shape.

### Stage 6: Frontend (one sub-stage per session)

**The spec is `docs/frontend-tasks.md`.** Its section 5 describes every component, and its
section 6 lists the sub-stages with their tests. Its section 1.2 (the problems on the old
branch) and section 7 (backend fixes) describe the deleted first attempt; those lessons are
now in section 2.2 and in Stages 4 and 5 here.

Rules for every sub-stage:

- React + TypeScript + Vite, using only the approved dependencies (section 4).
  TypeScript is `strict`; no `any` unless it has a comment explaining why.
- **Only `api/client.ts` calls `fetch`.** It checks `res.ok`, parses every response with the
  zod schema for that endpoint and throws a typed error if the shape doesn't match.
  Components get data only through the hooks in `api/hooks.ts`.
- Components share state only through `useAppState` (query state synced with the URL hash).
  Server data stays in react-query. Never copy it into app state.
- Each component lives in its own folder with its `.module.css` and its `.test.tsx`. It takes
  typed props or reads `useAppState`. It never reaches into another component.
- **Never use `dangerouslySetInnerHTML`.** React escapes text by default; keep it that way.
- Leaflet and Chart.js objects live inside their components (refs and effects) and are
  cleaned up on unmount.
- Mock mode (`?mock=1` in the URL, or `VITE_USE_MOCKS=true`) makes `client.ts` read from
  `/mock/*.json`, so the UI works without the backend.
- Show `SyntheticBanner` whenever any response has `synthetic: true`.
- Accessibility:
  - Never use color alone; every colored value also shows its number.
  - Text contrast meets WCAG AA (pick the text color automatically from the background
    color).
  - Every control works with the keyboard.
  - Loading and error messages go in an `aria-live` region.

Sub-stages (details in `frontend-tasks.md` section 6):

- **6a. Plumbing, tokens and the app shell.** npm scripts `dev`, `build`, `preview`, `test`,
  `lint`, `typecheck` (`tsc --noEmit`) and `check` (typecheck + lint + test); ESLint; the
  Vite proxy; `api/` (schemas, client, hooks); `state/`; `lib/colors.ts` and
  `lib/format.ts`; the tokens; `AppHeader` and `SyntheticBanner`; `frontend/.nvmrc`; add
  `frontend/node_modules/` and `frontend/dist/` to `.gitignore`. `lib/geo.ts` already
  exists; extend its tests with the Stage 4 edge cases.
  - **Contract test:** a Vitest test parses every file in `public/mock/` with the matching
    zod schema. If the backend changes a response shape, regenerating the mocks makes this
    test fail.
- **6b. Map card: map, draw tool and area fields.** Partly done (section 2.1). Still to do:
  the Satellite basemap toggle, coverage outlines, the area label chip, Point + radius mode,
  the validation messages from `frontend-tasks.md` 5.3, moving inline styles to CSS Modules,
  and the 6b tests.
  - The map toolbar is a bboxfinder-style stack at the top-left: zoom +/−, then "Draw area"
    and "Delete area" (and a circle button when Point + radius mode arrives). 44 px buttons,
    `z-index: 1000`, rendered outside `MapContainer`. No Leaflet.draw.
- **6c. Dates and Analyze.**
- **6d. Burning calendar.**
- **6e. Side panel and Comparisons tab.**
- **6f. Map results layer and footer.**
- **6g. Hotspot table and Downloads.**
- **6h. Methods tab.**
- **6i. Watchlist tab.**

Done when (each sub-stage):

- `npm run check` passes, with component tests for the new behavior.
- It works in mock mode and against the real API (through the Vite proxy), with no console
  errors.
- It passes a keyboard-only check.
- There is a screenshot in `docs/screenshots/`.

### Stage 7: Pipeline, Docker, docs

- `firecal/pipeline.py`, the automated input workflow from start to finish:
  - `python -m firecal.pipeline backfill --region X` runs fetch backfill → ingest → cells →
    harmonize (with calibration).
  - `python -m firecal.pipeline update [--region X | --all]` runs fetch update → ingest →
    cells → harmonize. It reuses the existing calibration; `--recalibrate` refits it.
  - Each step is the same function its stage's CLI calls; `pipeline.py` only chains them and
    stops at the first failure with a clear message.
  - Rebuilding cells and the harmonized table in full each time is fine. Only optimize if it
    takes more than 5 minutes.
- **Daily update:** `docker-compose.yml` already has an `updater` service that runs
  `pipeline update --all` once a day and shares the `data/` volume with the web service.
  Check that it works with the real pipeline. Writers already save atomically (section 6),
  so the web app never reads a half-written file.
- **Dockerfile:** it's already multi-stage (a Node stage builds `frontend/`; the
  `python:3.12-slim` stage copies `firecal/`, `app.py` and `frontend/dist/`). Update the Node
  image to the current LTS, matching `frontend/.nvmrc`. The final image contains no Node and
  no `node_modules`.
- Write `README.md` around the challenge. Cover:
  - what the app does
  - how to get a `MAP_KEY` and put it in `.env`
  - how to run `pipeline backfill` for a new area (including `--bbox` from a box drawn in
    the app)
  - how harmonization works
  - its limitations
- Done when:
  - `docker compose up --build` serves the app over processed data mounted from the host.
  - The updater runs one update cycle without errors (with a real key; the owner checks this).
  - Every test passes inside the container.

### Stage 8: Stretch (only if asked)

- On-demand areas: when a user draws an area outside the coverage, offer "Fetch history for
  this area". It queues a background `pipeline backfill` job and shows progress. Limit it to
  one job at a time and show the estimated transactions before starting, because a backfill
  takes tens of minutes and uses the key's quota.
- NOAA-20 as a continuity fallback for S-NPP, with its own calibration against S-NPP.
- Place search, preset administrative boundaries, a PDF report.

---

## 8. Color ramps (use exactly these unless told otherwise)

- **Sequential (counts)**, ColorBrewer YlOrRd, 7 classes:
  `#ffffb2 #fed976 #feb24c #fd8d3c #fc4e2a #e31a1c #b10026`.
  Zero gets a neutral color outside the ramp. Bins are quantiles of the non-zero monthly
  values for the selected area, shown in the legend as ranges.
- **Diverging (anomaly)**, ColorBrewer RdBu, 7 classes, red = above median:
  `#b2182b #ef8a62 #fddbc7 #f7f7f7 #d1e5f0 #67a9cf #2166ac`.
  Centered on 0, with symmetric bins (`frontend-tasks.md` section 2.3 gives the bin edges).
- Pick the text color on every colored cell (dark or light) from the background luminance.

---

## 9. Objective → stage map (check this at the end)

| Challenge objective | Stage |
|---|---|
| Harmonized MODIS + VIIRS time series, sensor no longer matters | 1a, 1b, 2, 3 |
| Data stays current (needed for "this month vs. median") | 1a, 7 (daily update) |
| Proof the harmonization works | 3 (validation), 6h |
| Select a region (draw or lat/lon) | 4, 5, 6b |
| Select a date range | 4, 5, 6c |
| Burning calendar, early 2000s to today, accessible color ramps | 4, 5, 6d |
| Which months and years have more fire | 6d, 6e |
| Current month vs. historical median, anomalies | 4, 6d, 6e, 6i |
| Downloadable hotspot CSV for a search | 4, 5, 6g |
| Download analytics and visualizations | 5, 6e, 6g |
