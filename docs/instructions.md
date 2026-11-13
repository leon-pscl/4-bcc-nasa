# Instructions for the coding agent

Read this whole file before writing any code. It explains what we are building, how the
code is split into modules, and the order in which to build them. Work **one stage at a
time** and stop at the end of each stage for review.

Read it together with:

- `docs/frontend-tasks.md`: what each UI element looks like and how it behaves.
- `docs/ui_settings.md`: fonts, colors and style, applied as `frontend-tasks.md` section 2
  describes.
- `docs/decisions.md`: every decision made after the plan was first written, with the reason.
  This file already reflects them; the log says why.

**Which file wins when they disagree:** `frontend-tasks.md` wins on the UI's layout, look and
behavior, except for the overrides listed in Stage 6 here. This file wins on everything else:
contracts, approved dependencies, the working agreement, tests and the backend. If this file
and `decisions.md` ever disagree, stop and ask the owner.

**Status (13 Nov 2026):** Stages 0, 1a, 1b and 2 are done. Stage 3 is in rework. Stages 4 and
5 are placeholders. **Next:** Stage 0b (CI, regions file, decision log), then finish Stage 3,
then Stage S (scale and regions). Section 7 gives the full order.

**Built to grow.** The app has to take on more regions, more years, more users and new
satellites without rewrites. Concretely: regions are data, not code (section 5.1); stored data
is partitioned by region and year (section 6); calibration is keyed by satellite (C3); every
response carries a data version so it can be cached (C7); and CI checks every push
(section 3). Section 4 lists what we deliberately don't build yet.

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

Where each stage stands (13 Nov 2026, evening):

| Stage | State |
|---|---|
| 0 Groundwork | Done: `firecal/` package, `config.py`, `contracts.py` (C1–C4), pytest setup, pinned requirements, `sample-data/` restored |
| 1a Fetch | Done. The key-status URL is a guess and FIRMS answers "Invalid API call", so the near-limit pause is off (the rate limiter still applies). Fix or remove it in Stage S |
| 1b Ingest | Done for small areas. It loads the whole store into memory and processes rows one by one, so it can't handle the two regions yet (Stage S) |
| 2 Cell-days | Done for small areas; same limit (Stage S) |
| 3 Harmonize | In rework. Calibration now counts cell-days. Still wrong: validation compares VIIRS with the harmonized table instead of Aqua × k, the synthetic generator doesn't produce its intended ratios, and the tests don't check results |
| 4 Analytics, 5 API | Placeholders only (commit `2d2b167`). Rebuild them from this file |
| 6 Frontend | Map card partly built (below) |
| 7 Pipeline, Docker | `Dockerfile` and `docker-compose.yml` exist; nothing else |

Other files: `docs/` (this file, `frontend-tasks.md`, `ui_settings.md`, `dashboard.jpg`,
`refs/`), `.env.example`, `.gitignore` (data, Python, Node and `.env` are ignored) and
`.dockerignore`.

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
  section 5.2.
- The API had no tests, and the mock files didn't match the contract (the calendar mock had
  no `query.bbox`). See Stage 5.
- **Duplicate (cell, date) counts:** the harmonized table counted every row twice in the
  early years — the pipeline's calibration `UNION ALL` added a second region-wide ALL
  month-0 row (the month-0 row is the region factor) on top of the one
  `calibration_all_sql` already emits, and the `k_all` join then doubled every k-scaled
  row (all of 2003-2011, plus NOAA and gap-fill days later). Guards that would have caught
  it: one row per (region, platform, reference, tile_id, month) in C3, one row per
  (region, cell_lat_idx, cell_lon_idx, date_local) in C4 — asserted after every build,
  and byte-identical counts when the build is a no-op. And the month-0 ALL row must be
  labeled `all`, not `all_month`.

Frontend:

- Data values went into `innerHTML` unescaped (an XSS risk). Never use
  `dangerouslySetInnerHTML`.
- `Number("-")` is `NaN`, which made Leaflet throw and blanked the page; clearing a field
  turned it into `0`. Keep field values as strings and parse them only to validate.
- There was no Vite proxy, so `/api/*` returned `index.html` in development.
- The API client never checked `res.ok`, and the zod schemas covered only part of each
  response.

From the first day of the fresh start:

- **k was computed from detections, not cell-days.** On a test with a true ratio of 2.5 it
  returned 10, which would have made every MODIS year about 4× too high. Calibration counts
  rows of C2 (one row = one cell-day).
- **Tests that check nothing passed.** `assert True`, or only `len(x) > 0`, while the code was
  wrong. A test asserts the expected value (section 3).
- **A fix was reported as done but never committed.** Reports now name the commit and the
  test for each fix, and CI shows the result on GitHub (section 3).
- **The synthetic generator overwrote the real cell-days file** and didn't label its output.
  Synthetic data lives in its own folder and always carries `synthetic: true`.
- **An external URL was guessed** (FIRMS key status). Confirm URLs against a real response
  before relying on them.

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
  `DATE .. DATE + DAY_RANGE - 1`, and `DAY_RANGE` is **1 to 5** (FIRMS rejects 6-10).
- Use the NRT sources only for recent days that standard processing doesn't cover yet. Check
  where each source starts and ends with `/api/data_availability/`.
- Loop over 5-day chunks, stay under the transaction limit, cache every response and resume
  after interruptions.

**How the app gets its data (decisions D6, D7).** The app covers fixed **regions**, each
loaded once and then topped up daily (section 5.1). Two sources feed each region:

| Period | Source | Cost |
|---|---|---|
| 2003 (MODIS) or 2012 (VIIRS) to the last complete year | FIRMS **yearly country files**, one CSV per country, year and sensor, linked from <https://firms.modaps.eosdis.nasa.gov/country/>. Download the files for every country the region's box touches, then clip the rows to the box | No API transactions |
| From the day after the yearly files end, to today; then daily | The area API above, for the region's box | One transaction per requested day per source, **whatever the area's size**: about 650 for the rest of a year (2 sources), a handful per day after that |

A full 2003-to-today history from the API alone would cost about 14,000 transactions per
region (about 35 minutes at our budget, often more), which is why the history comes from the
yearly files.

**In the app, the map's box never triggers a FIRMS download.** The web app only reads the
processed files. A box outside the covered regions gets a 422 with the list of covered
regions. The browser never calls FIRMS: the key is part of every FIRMS URL.

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
   whenever it is used. Synthetic data is written to `data/synthetic/`, never over real data.
10. **CI must be green.** Every push runs `pytest` and `npm run check` on GitHub (Stage 0b).
    Merge into `pascual` only when CI passes on the branch.
11. **Tests check results.** Every test asserts an expected value: a count, a ratio, a row, a
    message. `assert True`, or `len(x) > 0` on its own, is not a test. When a stage's "Done
    when" names a number, a test asserts that number.
12. **Reports show evidence, not just a test count.** A stage report gives:
    - the commit hash
    - the names of the tests added
    - every number the stage's "Done when" asks for (counts, k values, metrics, timings)
    - for each fix from a review: the commit and the test that covers it
13. **No placeholders under a stage's name.** Unfinished work is committed as `wip: ...` on its
    stage branch and isn't merged.

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
| CI | GitHub Actions: `pytest` on Python 3.12 and `npm ci && npm run check` in `frontend/`, on every push and pull request (Stage 0b) |

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
.github/workflows/ci.yml      Stage 0b: tests on every push and pull request
config/regions.json           regions and starter areas (section 5.1)
firecal/                      Python package (all backend code)
  __init__.py
  config.py                   Settings (section 5) + env overrides
  regions.py                  loads and validates config/regions.json (Stage 0b)
  version.py                  reads and writes data_version.json (C7)
  contracts.py                column lists, dtypes and validate_*() helpers (section 6)
  devdata.py                  synthetic multi-year dataset for development (Stage 3)
  pipeline.py                 Stage 7: add-region and update, chaining the stages below
  fetch/                      Stage 1a: FIRMS -> raw CSV cache (download only, no parsing)
    client.py  plan.py  ratelimit.py  cache.py  country.py  cli.py
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
data/raw/firms/               raw API responses + manifest.jsonl (git-ignored)
data/raw/firms_country/       yearly country CSVs + manifest_country.jsonl (git-ignored)
data/raw/manual/              CSVs downloaded by hand, if any (git-ignored)
data/processed/               partitioned Parquet datasets + json metadata (section 6; git-ignored)
data/synthetic/               synthetic datasets, always labeled (git-ignored)
docs/decisions.md             decision log
tests/
  fixtures/
```

**Not built yet, on purpose (decision D12).** No database server (Postgres/PostGIS), no
Kubernetes, no microservices, no job queue, no user accounts. None of them solves a problem
this app has: the data is read-only for users and has a single writer, the pipeline. If the
app outgrows one machine, the Parquet datasets move to object storage (DuckDB reads them
there) and the API runs as several read-only copies behind the same data version. That's a
migration, not a rewrite. Ask the owner before adding any of these.

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
| `MAX_AREA_KM2` | `500_000` | Applies to an analyzed area, not to a region. Larger areas are rejected. About 16,000 grid cells at 0.05°, under `MAX_MAP_CELLS`, so the map can show full detail. **Open:** the current UI dropped its limit message; the owner decides whether to keep the limit (and restore the message) or change it |
| `MAX_MAP_CELLS` | `20_000` | Above this, the map aggregates to a coarser grid |
| `REGIONS`, `STARTER_AREAS` | Loaded from `config/regions.json` (section 5.1) | Regions are data, so adding one needs no code change |
| `TEST_REGIONS` | `{"bolivia_east": (-64, -18, -60, -14), "luzon_example": (121.116028, 14.583583, 121.643372, 15.445738)}` | Small boxes (W, S, E, N) for tests, the sample data and local experiments. Use them only with a separate `DATA_PROCESSED`; the API serves only the regions in `regions.json` |
| `FIRMS_BASE_URL` | `https://firms.modaps.eosdis.nasa.gov` | |
| `FIRMS_SOURCES` | MODIS: `MODIS_SP` / `MODIS_NRT`; VIIRS: `VIIRS_SNPP_SP` / `VIIRS_SNPP_NRT` | SP for history, NRT only after SP ends |
| `FIRMS_DAY_RANGE_MAX` | `5` | API limit per request. FIRMS's page says 1..10, but a real request with 10 was rejected (decision D5) |
| `FIRMS_TX_BUDGET` | `4000` per `600` s | Stays below the 5,000 per 10 minutes key limit. Count each requested day as one transaction (worst case; FIRMS says multi-day requests may count as several) |
| `FIRMS_RETRIES` | `5`, exponential backoff from 5 s | FIRMS sometimes returns 504s |
| `NRT_REFRESH_DAYS` | `7` | NRT chunks ending within this many days of today are always fetched again, because NRT data keeps changing |
| `VIIRS_SP_START` | `2012-01-20` | First date of VIIRS 375 m data; never request VIIRS before this |
| `REFERENCE_PLATFORM` | `"SNPP"` | The satellite every other one is calibrated to. Aqua MODIS is calibrated to it now; NOAA-20/21 can be added later without changing C4 (decision D9) |
| `API_CACHE_ENTRIES` | `512` | Size of the server-side response cache (Stage 5). Entries are keyed by data version, so a pipeline run makes them stale automatically |
| UI unit label | "Hotspots (harmonized)" | The Methods tab explains the unit: one fire cell-day in VIIRS-equivalent terms |

Paths (`DATA_RAW`, `DATA_PROCESSED`) and `FIRMS_MAP_KEY` come from environment variables, with
defaults `data/raw` and `data/processed`. `.env.example` already exists.

### 5.1 Regions file (`config/regions.json`, decision D6)

```json
{
  "regions": [
    {"name": "southeast_asia", "label": "Southeast Asia",
     "bbox": [92.0, -11.0, 141.0, 28.5],
     "countries": ["Myanmar", "Thailand", "Laos", "Cambodia", "Vietnam", "Malaysia",
                   "Singapore", "Brunei", "Indonesia", "Philippines", "Timor-Leste",
                   "China", "Taiwan", "India", "Bangladesh"],
     "history": "country_files"},
    {"name": "amazon", "label": "Amazon",
     "bbox": [-80.0, -20.0, -44.0, 6.0],
     "countries": ["Brazil", "Bolivia", "Peru", "Ecuador", "Colombia", "Venezuela",
                   "Guyana", "Suriname", "French Guiana", "Paraguay", "Chile"],
     "history": "country_files"}
  ],
  "starter_areas": [
    {"name": "central_kalimantan", "label": "Central Kalimantan", "region": "southeast_asia",
     "bbox": [110.7, -3.6, 115.9, 0.8]},
    {"name": "northern_thailand", "label": "Northern Thailand", "region": "southeast_asia",
     "bbox": [97.3, 17.0, 101.5, 20.5]},
    {"name": "luzon_example", "label": "Luzon example", "region": "southeast_asia",
     "bbox": [121.116028, 14.583583, 121.643372, 15.445738]},
    {"name": "rondonia", "label": "Rondônia", "region": "amazon",
     "bbox": [-66.0, -13.7, -60.0, -7.9]},
    {"name": "bolivia_east", "label": "East Bolivia", "region": "amazon",
     "bbox": [-64, -18, -60, -14]}
  ]
}
```

Rules (Stage 0b tests them):

- **Regions don't overlap.** Each detection belongs to exactly one region partition.
- **`countries` lists every country the box touches**, so no part of the box silently shows
  zero fires. Use FIRMS's own country names; check them against the country file list.
  Southeast Asia's box also clips slivers of Bhutan, Japan's southern islands, Palau and the
  Papua New Guinea border. Add those only if their files are small.
- **`history`** is `country_files` (yearly files, then the API) or `api` (the API for
  everything, for a small region or one with no country files).
- **Every starter area lies inside its region and is at most `MAX_AREA_KM2`.** Sizes:
  Central Kalimantan 282,742 km², Northern Thailand 172,083, Luzon example 5,429, Rondônia
  422,476, East Bolivia 190,127.
- **Adding a region** is one entry here plus `python -m firecal.pipeline add-region <name>`
  (Stage 7). No code changes.

### 5.2 Which day is "today"

The analytics functions take `today` as a parameter (section 3).
In the API, `today` is the **latest data date** of the region the area falls in (`latest_date`
in `data_version.json`, C7). It is never the server clock. This keeps "this month vs. median" stable
across time zones: a browser in Manila (UTC+8) can be a day ahead of a UTC server. An `end`
later than the latest data date is rejected with a 400.

**`latest_date` is the last *complete* local day.** A day is complete once the region recorded
both its night and day satellite passes; a fetch that runs before the day pass (for example
00:18 in the morning) sees only the night pass, so that day is not yet complete and
`latest_date` stays at the previous complete day. The pipeline computes it from the
detections table (a day with both `day` and `night` rows); if a fetch happens after the day
pass, the day counts as complete.

### 5.3 Data version (decision D10)

Every pipeline run ends by writing `data_version.json` (C7): a version string plus each
region's latest data date. The API puts the version in every response and in an `ETag`
header, and keys its response cache on it. Answers stay cached until the data changes, then
refresh by themselves. `/health` uses it to show how fresh each region is.

---

## 6. Data contracts (the interfaces between stages)

Every table is stored as Parquet in `DATA_PROCESSED`. `firecal/contracts.py` defines the
columns and dtypes for each table and a `validate_<table>(df)` function that raises a clear
error on any mismatch. Each writer validates before saving, and each reader validates after
loading. Every writer saves to a temporary file and then renames it, so readers (the web app
during a daily update) never see a half-written file.

**Partitioning (decision D8).** C1, C2 and C4 are Parquet datasets split by region and year:
`<table>/region=<name>/year=<YYYY>/part-0.parquet`. This is Hive-style, so DuckDB reads `region`
and `year` as columns and skips partitions a query doesn't need. A writer rebuilds one
partition at a time and swaps it in with a rename. A daily update only rebuilds the
current year's partitions. The column tables below describe the rows inside a partition.
Nothing loads a whole dataset into pandas: heavy steps run in DuckDB, or one partition at a
time.

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

**Country files** (Stage S): `data/raw/firms_country/<SENSOR>/<YEAR>/<Country>.csv`, as
downloaded (or extracted from FIRMS's yearly archive), written atomically.
`manifest_country.jsonl` has one line per file:
`{sensor, year, country, rows, sha256, fetched_at, path, source_url}`.

### C1 `detections/` dataset (written by Stage 1b)

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

Also written: `coverage.json`, one entry per region: `{name, label, bbox:[W,S,E,N],
countries, start, end, platforms, latest_date, synthetic}`. Coverage is the **requested**
region and dates, not the extent of the data found.

### C2 `celldays/` dataset + `celldays.meta.json` (written by Stage 2)

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
| `region` | string | calibration is fitted per region |
| `platform` | string | the satellite being scaled: `Aqua` today; `NOAA20` or `NOAA21` later |
| `reference` | string | the satellite it's scaled to: `REFERENCE_PLATFORM` (`SNPP`) |
| `tile_id` | string | or `ALL` |
| `month` | int8 | 1–12, or 0 for all months |
| `k` | float64 | VIIRS cell-days / MODIS cell-days |
| `modis_celldays`, `viirs_celldays` | int64 | sample behind `k` |
| `level` | string | `tile_month`, `tile`, `all_month`, `all` |

### C4 `harmonized_daily/` dataset (written by Stage 3)

| column | type | notes |
|---|---|---|
| `cell_lat_idx`, `cell_lon_idx` | int32 | |
| `tile_id` | string | |
| `date_local` | date | |
| `value` | float64 | VIIRS-equivalent cell-days (1.0 for a VIIRS cell-day, `k` for a MODIS one) |
| `basis` | string | `viirs`, `viirs_noaa20`, `viirs_noaa21`, `modis_scaled`, `modis_gapfill` |

**No `sensor` or `platform` column.** This is the table every analysis reads.

### C5 `validation/<region>.json` (written by Stage 3)

Shape: `calibration_years` and `validation_years` each have `years` (list), `metrics`
(`pearson_r`, `bias_pct`, `median_abs_pct_error`, `monthly_viirs`, `monthly_modis`) and
`per_year` (keyed by year, same fields). The monthly series have 12 values each.

Metrics: Pearson r of monthly totals, bias % = (sum scaled - sum viirs) / sum viirs, and
median absolute % error over months where VIIRS >= 10. `metrics` aggregates all years in
the set; `per_year` is per year.

**Measured bias for the Northern Thailand starter area** (97.3°E–101.5°E, 17.0°N–20.5°N): the
held-out 2018–2021 bias is larger than the region-wide figure. Region-wide (southeast_asia,
including 2021): −4.91%. Northern Thailand, per year: 2018: −9.73% · 2019: −10.10% ·
2020: −18.47% · 2021: −12.92%. The reason for the larger Northern Thailand undercount has
**not been established**; nothing should be inferred about cause (cloud, crop cycle,
retrieval artefacts, or anything else) from these numbers alone. They are reported here so
the area's scaled counts are not mistaken for the region-wide accuracy. If the reason is
later shown, upgrade this note into a decision record.
The series are `monthly_viirs` (S-NPP cell-days) and `monthly_modis`, which is
**Aqua x k (scaled)**, not raw MODIS. Both come from C2 (Aqua cell-days x k(tile, month),
and S-NPP cell-days), with VIIRS outage days excluded. Do not use C4: from 2012 on it
holds VIIRS, so it has no MODIS to compare.

### C6 API responses (written by Stage 5)

Query parameters shared by all area endpoints:

- an area, either `bbox=W,S,E,N` or `point=LAT,LON&radius_km=R`
- `start=YYYY-MM-DD&end=YYYY-MM-DD`

Errors return `{"error": "...", "field": "..."}` with HTTP status 400 (bad input) or 422 (no
data for this area; the response also lists the covered regions).

An analyzed area must lie inside one region. Every JSON response includes
`"data_version": "..."` (C7) and is sent with `ETag: "<data_version>"`; a request with a
matching `If-None-Match` gets a 304.

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
  (`page_size` ≤ 500). Shape (the frontend reads this):
  ```json
  {"page": 1, "page_size": 100, "total": 1234,
   "rows": [{"date_local": "2026-09-27", "acq_datetime_utc": "2026-09-27T00:18:00",
             "latitude": -16.025, "longitude": -61.975,
             "confidence_class": "nominal", "frp": 12.3, "daynight": "D",
             "sensor": "MODIS", "platform": "Aqua", "processing": "NRT"}],
   "data_version": "a1b2c3d4e5f6g7h"}
  ```
  `sensor`, `platform`, `processing` are present when requested via `all_sensors=1`;
  by default (the harmonized series) they may be omitted.
- `GET /api/hotspots.csv?all_sensors=0` streams the hotspot CSV.
- `GET /api/calendar.csv` returns the calendar matrix as CSV.
- `GET /api/calendar.png` returns the calendar as an image.
- `GET /api/coverage` returns `{regions: [...coverage.json entries], starter_areas: [...from
  regions.json], data_version}`.
- `GET /api/methods?region=<name>` returns that region's calibration summary plus
  `validation/<region>.json`.
- `GET /health` returns `{status, data_version, regions: [{name, latest_date, age_days}]}`.
  `status` is `"stale"` when a region's latest date is more than 3 days old.

### C7 `data_version.json` (written at the end of every pipeline run)

```json
{"version": "2026-11-13T22:05:00Z",
 "regions": {"southeast_asia": {"latest_date": "2026-11-12", "synthetic": false},
             "amazon": {"latest_date": "2026-11-12", "synthetic": false}}}
```

`version` is the run's finish time in UTC. It changes only when the data does.

---

## 7. Stages

Order from here: **0b → 3 (finish) → S → load the two regions → 4 → 5 → 6a–6i → 7.**
Stages 0, 1a, 1b and 2 are done; their sections stay as the spec their tests check, and
Stage S changes how they store data. Stage 6a and the rest of 6b don't need the backend, so
the owner may run them in parallel. The other frontend sub-stages need the Stage 5 mocks.

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

### Stage 0b: Foundations for growth (next)

Goal: the cheap groundwork that is expensive to add later.

- **CI:** `.github/workflows/ci.yml` runs on every push and pull request:
  - Python 3.12: `pip install -r requirements-dev.txt`, then `pytest -q`
  - Node (current LTS, from `frontend/.nvmrc`): `npm ci`, then `npm run check` in `frontend/`.
    Add the missing `lint`, `typecheck` and `check` scripts if 6a hasn't yet.
  - No secrets: tests never touch the network, so CI needs no FIRMS key.
- **Regions file:** create `config/regions.json` exactly as section 5.1 shows.
  `firecal/regions.py` loads it and checks the rules; `Settings` exposes `REGIONS` and
  `STARTER_AREAS` from it. The CLIs accept `--region` for a region or a test region.
- **Decision log:** add `docs/decisions.md` (the owner provides the first version) and append
  an entry whenever a section 5 default or a contract changes.

Done when:

- CI runs on GitHub and passes on `pascual`. Report the link to the passing run.
- Tests: the regions file loads; regions don't overlap; every starter area is inside its
  region and at most `MAX_AREA_KM2`; a broken file (overlap, oversized starter area, unknown
  region) fails with a clear message.

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
  only runs once per area, because of the cache. The cost is per day, not per area, which
  is why the history now comes from yearly country files and the API only fills in the
  current year (section 2.3, Stage S).

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
  - Fit per region; write `region`, `platform` and `reference` into C3. Also fit
    platform = `NOAA20` and `NOAA21` vs `SNPP` over their overlap years (for continuity).
  - Calibrated factors are shrunk (decision D14):
    `k_month = (viirs + m*k_tile)/(aqua + m)`, `k_tile = (viirs_tile + m*k_region)/(aqua_tile + m)`,
    with `SHRINK_M = 30`.
  - Fallback order when `modis_celldays < MIN_CALIBRATION_CELLDAYS`: tile, all tiles, then
    region (`ALL` rows). Record the level used.
- `apply.py`: `build_harmonized(celldays, calibration, settings) -> DataFrame` (C4).
  - Drop dates before `SERIES_START`.
  - `SERIES_START ≤ date < SWITCH_DATE`: Aqua cell-days with `value = k(tile, month)`,
    `basis = modis_scaled`.
  - `date >= SWITCH_DATE`: SNPP cell-days with `value = 1.0`, `basis = viirs`.
  - Continuity (after S-NPP's last day, 2026-11-02): use NOAA-20 cell-days with
    `value = k(NOAA-20 -> SNPP)`, `basis = viirs_noaa20`; if NOAA-20 has no data,
    NOAA-21, `basis = viirs_noaa21`; if neither, Aqua x k gap fill, `basis = modis_gapfill`.
  - **Gap fill:** on dates ≥ `SWITCH_DATE` where SNPP has zero detections across the whole
    coverage area but Aqua has some, treat it as a VIIRS outage. Use Aqua × k with
    `basis = modis_gapfill`.
- `validate.py`: `validate(celldays, calibration, settings) -> dict` (C5). Compare Aqua × k
  with SNPP in both the calibration and validation years, both computed from C2 (see C5).
- `cli.py`: `python -m firecal.harmonize`. If the calibration years aren't in the data (for
  example, with only the 7-day sample), stop with a clear message. Never silently use a
  default `k`.
- `firecal/devdata.py`: `generate(settings, seed) -> DataFrame` (callable from tests) and
  `python -m firecal.devdata`, which writes a **labeled synthetic** C2 dataset to
  `data/synthetic/` (never `data/processed/`) with `synthetic: true` in its coverage.
  - Two specific 1° tiles: tile A with SNPP = 2.5 × Aqua, tile B with 1.5 ×.
  - Each day, Aqua fire cells ~ Poisson(λ × seasonal factor, peak Aug–Oct) and SNPP cells
    ~ Poisson(ratio × λ × seasonal factor), drawn as **distinct cells** within the tile, so
    there are no duplicate (cell, date, platform) rows.
  - Aqua for 2003 to today; SNPP only from 2012-01-20.
  - λ is high enough that every tile × month in 2013–2017 has at least
    `MIN_CALIBRATION_CELLDAYS` Aqua cell-days.
  - A few days in 2016 with Aqua fires and no SNPP, to exercise gap fill.
  - Fixed seed.

Done when (each one is a test that asserts the number):

- Synthetic: k is within ±5% of 2.5 for tile A and of 1.5 for tile B, at level `tile_month`.
- Synthetic: validation r > 0.9 and |bias| < 5%, for both the calibration and the
  validation years.
- Fallback: a tile with too few Aqua cell-days gets the parent k and the right `level`.
- Switch date: Aqua before 2012-02-01 is `modis_scaled`; SNPP after it is `viirs`.
- Gap fill: the 2016 Aqua-only days become `modis_gapfill` with value k.
- No calibration-year data: a clear error.
- C4 has no `sensor` or `platform` column (enforced by the contract validator).
- C5's `monthly_modis` equals Aqua cell-days × k for a hand-checked month.
- The report gives the recovered k for both tiles, the validation metrics and the C4 row
  count per `basis`. On real data (after Stage S), the same per region.

### Stage S: Scale and regions (C0–C5 at continental size)

Goal: load the two regions (likely tens of millions of detections) and make adding a region
or a satellite a data change, not a rewrite. Stages 1a–3 keep their logic and tests; this
stage changes how they store and process data.

- **Country files** (`firecal/fetch/country.py`, CLI `python -m firecal.fetch country
  --region <name>`). First report, without downloading at scale:
  - the file URLs on <https://firms.modaps.eosdis.nasa.gov/country/>
  - whether single-country files exist or only the yearly all-country archives, and their
    sizes
  - the last complete year available, and whether its `version` is SP or NRT
  - whether the columns match the area API's (including `type`)
  - FIRMS's exact spelling of each country in `regions.json`

  The owner approves before the large download. Then download MODIS (2003 to the last
  complete year) and VIIRS S-NPP (2012 to the last complete year) for the region's
  countries into C0's country cache, skipping files already present.
- **API for the current year:** `backfill --region <name>` starts from the day after the
  country files end. For a `history: api` region, it covers everything.
- **Key status:** take the real URL from the "view status" link in the MAP_KEY email, parse
  the response, and pause near the limit. If that can't be done, remove the call instead of
  warning.
- **Progress:** downloads and backfills print a line every 50 items (done/total,
  transactions used, elapsed time, ETA). Dry runs print the estimated time.
- **Ingest:** vectorized (no `apply(axis=1)`, `iterrows` or per-row loops). Clip rows to the
  region's box and tag them with the region. Write C1 partitions by region and year;
  SP-replaces-NRT and dedup run per partition in DuckDB.
- **Cells and harmonize:** per region and year, in DuckDB or vectorized pandas. Rebuild only
  the partitions whose inputs changed (record input fingerprints in the meta file). Gap fill
  is decided per region ("SNPP has zero cell-days across the region that day").
  Calibration is fitted once per region and refitted only with `--recalibrate`.
- **Data version:** every run ends by writing C7.

Done when:

- A test with two small synthetic regions writes separate partitions per region and year,
  with no rows crossing regions. Changing one year's input rebuilds only that year.
- All earlier tests still pass, including the sample-data numbers from section 2.4.
- On one real region-year (e.g. `amazon` 2019), the report gives the ingest, cells and
  harmonize times and the peak memory. Flag it if peak memory goes above 4 GB.

**Then load the two regions.** For each region: country files, API backfill, ingest,
cells, harmonize. Report rows per platform and per year, the median k, the validation
metrics, and the latest date in C7.

### Stage 4: Analytics (C4 + C1 → Python results)

Goal: pure functions that answer every question the UI asks. Use DuckDB over the
partitioned datasets, filtering on `region` and `year` first so only the needed partitions
are read. Every function takes `today` (section 5.2). The placeholder code from commit
`2d2b167` doesn't follow this section; rebuild it.

- An area must lie inside one region. `Area.region(regions)` returns that region, or `None`
  (the API turns `None` into a 422).

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
- On real data, `calendar_matrix` for a 500,000 km² box inside a region, over 2003 to
  today, runs in under 1 s (warm) on the dev machine. Report the time. If it's slower, add a
  monthly per-cell rollup built by the pipeline, and only then: measure before optimizing.

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
  - `today` comes from C7, never the server clock (section 5.2).
  - Every JSON response carries `data_version`, with `ETag` / `If-None-Match` → 304 (C6).
  - A server-side LRU cache (`API_CACHE_ENTRIES`) keyed by path, query string and data
    version. Starter areas and watchlist checks repeat the same queries.
  - `/api/coverage` and `/health` follow the C6 shapes (regions, starter areas, freshness).
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
- A repeated request with the returned ETag gets a 304; after a new C7 version, the same
  request gets fresh data.
- `/health` reports `stale` when a region's latest date is more than 3 days old (test with a
  fixed `today`).
- `/api/calendar` is under 50 KB for the full record.
- The only endpoint that returns detection rows as JSON is the paged `/api/hotspots`.
- Mock files are generated, and a Python test validates each one against the C6 shape.

### Stage 6: Frontend (one sub-stage per session)

**The spec is `docs/frontend-tasks.md`.** Its section 5 describes every component, and its
section 6 lists the sub-stages with their tests. Its section 1.2 (the problems on the old
branch) and section 7 (backend fixes) describe the deleted first attempt; those lessons are
now in section 2.2 and in Stages 4 and 5 here.

**Overrides of `frontend-tasks.md`** (decisions D3, D6). These win over that file:

- **Default view:** when the hash is empty, open on the first starter area from
  `/api/coverage`, with dates from its region's start to its `latest_date`. (Not "the first
  region": a region is far bigger than `MAX_AREA_KM2`.)
- **6b "Jump to" picker:** lists the starter areas grouped by region. Choosing one fills the
  draft and fits the map to it.
- **6b coverage check before Analyze:** when the draft area isn't inside one region, Analyze
  is disabled and the helper line names the covered regions. The user shouldn't need a 422
  to find out.
- **6b map toolbar:** the bboxfinder-style stack below, not zoom at the bottom-right.
- **"Data through"** shows the analyzed region's `latest_date`. `/api/coverage` follows
  C6's new shape (6a schemas).
- **6h Methods tab:** shows the region of the analyzed area (`/api/methods?region=`).

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
  - `python -m firecal.pipeline add-region <name>` loads a region from `regions.json`:
    country files (if `history: country_files`) → API backfill for the rest → ingest → cells
    → harmonize (with calibration) → C7.
  - `python -m firecal.pipeline update [--region X | --all]` runs fetch update → ingest →
    cells → harmonize → C7. It rebuilds only the partitions whose inputs changed (normally
    the current year), reuses the existing calibration, and refits it with `--recalibrate`.
  - Each step is the same function its stage's CLI calls; `pipeline.py` only chains them and
    stops at the first failure with a clear message.
  - Each run writes a short summary (rows added per region, partitions rebuilt, durations)
    to `data/processed/runs/<timestamp>.json`.
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
- NOAA-20 and NOAA-21 as continuity for S-NPP. Each gets C3 rows with `platform = NOAA20`
  (or `NOAA21`) and `reference = SNPP`. C4 and everything downstream stay the same.
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
| New regions and satellites without rewrites | 0b, S, 7 (`add-region`), 8 |
