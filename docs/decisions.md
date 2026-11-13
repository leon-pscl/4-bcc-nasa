# Decisions

One entry per decision that changed the plan after it was first written. `instructions.md`
already reflects each one; this file records why. Add an entry whenever a section 5 default
or a contract changes. Newest last.

| ID | Date | Decision | Why |
|---|---|---|---|
| D1 | 2026-11-13 | **Fresh start.** Branch `pascual` reset at `a5e4cfb`; the first attempt stays in history at `82a4528` for reference only. Only `sample-data/` was restored from it. | The first attempt had grown too far from the plan to fix in place. |
| D2 | 2026-11-13 | **Own drag-to-draw handler; no Leaflet.draw.** | Leaflet.draw keeps its own copy of the shapes, which has to be synced with React state both ways. It hasn't had a release since 2018, its toolbar fights the spec, and it doesn't wrap longitudes. |
| D3 | 2026-11-13 | **bboxfinder-style map toolbar:** a stack at the top-left (zoom +/−, Draw area, Delete area), 44 px buttons, `z-index: 1000`, rendered outside `MapContainer`. Overrides `frontend-tasks.md` 5.3, which put zoom at the bottom-right. | The owner's choice of look. The first version was invisible because it had no z-index and sat under Leaflet's map layers. |
| D4 | 2026-11-13 | **"Today" is the latest data date**, never the server clock. `end` after it is a 400. | Closes `frontend-tasks.md` B3. A browser in Manila can be a day ahead of a UTC server, and "this month vs median" must not shift with time zones. |
| D5 | 2026-11-13 | **`FIRMS_DAY_RANGE_MAX = 5`.** | FIRMS's page says 1..10, but a real request with 10 was rejected. Transactions are counted per day either way, so this only doubles the number of requests. |
| D6 | 2026-11-13 | **Two regions, Southeast Asia and the Amazon, kept in `config/regions.json`,** with starter areas under 500,000 km² for the default view and the "Jump to" picker. Users analyze areas inside the regions only. | FIRMS charges per day, not per area, so a few large regions are the cheapest coverage. Both are among the most fire-active regions on Earth. Regions as data mean adding one needs no code change. |
| D7 | 2026-11-13 | **History from FIRMS yearly country files; the area API only for the current year and daily updates.** Each region downloads every country its box touches and clips to the box. | About 650 transactions per region instead of about 14,000. Including every touched country avoids parts of a box silently showing zero fires. |
| D8 | 2026-11-13 | **Parquet datasets partitioned by region and year, processed with DuckDB or one partition at a time.** | The two regions likely hold tens of millions of detections, too many to load whole into pandas. Partitions let a daily update rebuild only the current year. |
| D9 | 2026-11-13 | **Calibration keyed by satellite:** C3 has `region`, `platform` and `reference` (`SNPP`). | MODIS is near end of life and S-NPP has flown since 2011. NOAA-20/21 can be calibrated to the same reference later without changing C4 or the app. |
| D10 | 2026-11-13 | **Data version** (C7) in every API response, as an `ETag`, and as the key of a server-side response cache. `/health` reports freshness per region. | Repeated queries (starter areas, watchlist checks) become instant, caches refresh themselves after each pipeline run, and stale data is visible. |
| D11 | 2026-11-13 | **CI on GitHub** (`pytest`, `npm run check`) on every push; merge only when green. Reports name commits and tests, and give the numbers each stage asks for. | On day one, a fix was reported but never committed, and tests that checked nothing passed while k was 4× wrong. CI makes "tests pass" visible without running anything locally. |
| D12 | 2026-11-13 | **Not built yet:** database server, Kubernetes, microservices, job queue, user accounts. | Data is read-only for users and has one writer, the pipeline. If the app outgrows one machine, the data moves to object storage and the API runs as read-only copies: a migration, not a rewrite. |
| D13 | 2026-11-13 | **ESLint** (with `typescript-eslint` and `jsx-a11y`) as the linter. | It's on the approved list, and no linter was installed after the reset, so `frontend-tasks.md` 6a's ESLint-or-oxlint question no longer applies. |

## Open

| ID | Question | Notes |
|---|---|---|
| O1 | Keep the 500,000 km² analysis limit? | The backend enforces it, but the current map card no longer shows the warning. Either restore the message or change `MAX_AREA_KM2`. The starter areas were chosen to fit under it. |
| O2 | The FIRMS key-status URL | The guessed URL returns "Invalid API call". Get the real one from the "view status" link in the MAP_KEY email (Stage S). |
