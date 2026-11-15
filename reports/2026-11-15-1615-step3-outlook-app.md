# Report: step 3 — outlook in the app (branch outlook/app), 2026-11-15 16:15
Task: inbox/claude-2026-11-15-1350-outlook-override.md, step 3; spec inbox/task-fire-outlook.md
Branch: outlook/app @ e7d09a0 (built on outlook/data, merged to pascual 94cf7ce). Merge pending CI.

## What was built
Backend (Flask, read-only on the Parquet tables):
- GET /api/outlook?<area> — issued, latest_data_date, months x3 (lead 1-3), model climatology, expected (area sum of C14 expected), typical_range (p25-p75 of the area's baseline-year totals from monthly_cells), normal_mean/normal_median, observed_so_far (lead 1, month in progress), cells_likely (p_fire >= 0.5), season (12-month median/mean + peak/busiest), skill (from C16), data_version (dv of monthly_cells+outlook).
- GET /api/outlook/map?<area>&lead=1..3 — kept cells only, lat/lon to 3 decimals, chances to 2, counts to 1.
- GET /api/outlook.csv?<area> — every kept cell x 3 leads.
- GET /api/cells.csv and /api/cells.parquet ?<area>&start=&end= — C12 rows with lat/lon centres and value_* columns; Parquet built in memory (con.execute(sql) -> DuckDB Arrow -> pyarrow), cap 2,000,000 rows (400 over the cap).
- Outlook endpoints take no cover parameter: anything but all is 400, field "cover".
- /api/methods?region= gains grid (cells by mask reason, masked share of fire) and outlook (grid, mask, threshold, VIIRS-years p_fire rule, model, issued, targets, skill incl. big years 2015/2019/2023).
- /api/coverage gains per-region outlook: {issued, targets}.
- write_data_versions now includes monthly_cells and outlook (grid_cells fingerprinted in C11 build; monthly_cells fingerprinted per year in C12 build; outlook per issue in C14 build — even no-op runs re-record them, so the ETag never goes stale).
- 400/422/304 for all outlook paths (outlook shares ONE data version, so /api/outlook and /api/outlook/map return the same ETag and 304 on either).
Frontend:
- Outlook tab in the SidePanel (Watchlist slot, tab=outlook): "Outlook (experimental) from data through 14 November 2026. Based on past fire patterns, not a weather forecast."; three month cards (expected mono 32/600, typical range, typical median, "So far (1-14 Nov)" for the month in progress); "Where?" with month switch (Nov|Dec|Jan), top-10 cells "rank · coords · NN% chance · about N hotspots", "Show on map" (sets layer outlook + lead + cell in the hash; the map pans and highlights the cell); "When does this area burn?" 12-bar chart (peak in --ink, rest --muted); "How reliable is this?" tiles (top-10% capture, tested on 2015-2025), link Methods.
- Map: History | Outlook segmented control in the footer (hash layer=), month switch (hash lead=1..3), 0.15 deg rectangles, chance colors on the fixed bins (exactly 5% falls in the second bin — tested), popup "… · NN% chance of fire activity · about N hotspots", footer note "15 km cells. Sea, lakes, barren land and ice are left out.", legend "Chance of fire … rare to likely" and the fire-activity definition.
- Downloads: Outlook CSV + Monthly 15 km cells CSV/Parquet with the note "One row per cell and month with fire; months without a row had none."
- Mocks regenerated from the real app (make_mocks.py): api_outlook.json, api_outlook_map.json; api_methods/api_coverage now carry the new blocks; contract test passes.

## Numbers (real app, Central Kalimantan)
issued 2026-10 (latest_data_date 2026-11-14, partial Nov). Lead 1 (Nov 2026): expected 727.6, typical range 181-504, median 267, observed so far 1,275.3 (1-14 Nov), cells_likely 60; lead 2 (Dec): expected 85.9; lead 3 (Jan 2027): expected 135.6. Mask: 26,015 kept of 86,328 cells (water-masked 60,313); masked share of fire 0.042%. Backtest-lite pooled: capture 62.35%, Brier 0.1132 (2015-2025). Map screenshot shows the 0.15 deg chance-coloured cells over the starter area.

## Verification
- Backend: 173 pytest green (includes 12 new endpoint tests: 200/400/422/304; Parquet opens with pyarrow and has the right columns; /api/cells cap; methods grid/outlook; coverage outlook).
- Frontend: 76 vitest green; typecheck and eslint clean (`npm run check`).
- Contract: all 8 mocks parse with the zod schemas (contract.test.ts).
- Screenshots: docs/screenshots/outlook-tab.png, outlook-map.png, outlook-methods.png (headless Chrome against the built app in mock mode, no errors in console).

## Notes / deviations
- The Outlook endpoints carry one ETag for outlook+cells (they share the outlook data version); /api/outlook and /api/outlook/map 304 each other.
- /api/outlook deliberately has no start/end; the query block echoes bbox/point and area_km2 only.
- P6 (wiring the outlook into `pipeline update`) NOT done — merged after 20:30 (see below); check the report for the final decision.
- Commit f52bae0 was an in-progress snapshot (tests failing); e7d09a0 is the tested state. Nothing was pushed broken; CI on e7d09a0 is green at merge time.
- An earlier flask/vite preview pair was left serving a stale build (killed); a stray data_version.json was rewritten during outlook CLI wiring and immediately restored with all five keys identical for the three legacy datasets.

## Build/timing
Outlook builds on E:\datasets done post-merge of outlook/data (build-grid 122.1 s; build-monthly up-to-date; issue 38.3 s, peaks ~1 GB for climatology). Backtest 404 s.
