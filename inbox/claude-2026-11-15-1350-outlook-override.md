From: Claude, 15 Nov 2026 13:50. Deadline: TONIGHT 23:59 Manila.

This message overrides the usual order of work and the stop-for-review rule for today.
The owner has pasted the outlook spec (task-fire-outlook.md) right after it: use the spec
for details; this message says what is in and out tonight. Save both in inbox/.

## Rules for tonight
- Don't stop for review between steps. Push a report to `handoff` at each merge or tag and
  keep going. Stop only if you're blocked or a check below fails.
- Still in force: CI green before every merge into `pascual`; every tag gets a hard-link
  data snapshot on E: with a SHA-256 manifest; stop only processes you started.
- No new dependencies and no Docker image changes (no scikit-learn tonight).
- NOT tonight: fix/c1-slim (don't merge, don't migrate), the grid-edge fix and rebuild, the
  world/Asia work, MCD12C1, ENSO/IOD inputs, the GLM model (P3 model part).
- Each step has a hard time. If it misses it, leave the branch unmerged, note it in the
  report, and move to the next step.

## Step 1 (by 15:30): item 17, the missing VIIRS NRT files, then a safety tag
1. Read-only first: detections by platform x processing (SP/NRT) x month for Jul-Nov 2026,
   and C4 rows by `basis` for the same months.
2. If the S-NPP, NOAA-20 or NOAA-21 NRT rows for Aug-Nov 2026 are missing: stop the updater,
   ingest only the three southeast_asia NRT CSVs (SV-C2, J1V-C2, J2V-C2), then rebuild
   cells and harmonize for 2026 only (no --recalibrate). Ingest those three files by path;
   check that the 5 already-ingested files aren't staged again and no rows are duplicated.
3. Report Central Kalimantan before/after: 2026 total; Aug, Sep, Oct totals; Nov 1-14 total
   and its forest share; and the region-wide 2026 total.
4. Measure only, don't fix: 2026 NRT detections in 0.05 deg cells that have archive
   detections with type 1 or 2 (NRT files have no `type`, so these pass KEEP_TYPES).
   Give the count and the top 10 cells.
5. Confirm CI green on 034ac48, tag it `v1.0.2-southeast-asia` (annotated), and snapshot
   the data as E:\snapshots\v1.0.2-southeast-asia. If step 2 isn't done by 15:30, leave the
   data as it was, tag anyway with that data, and list item 17 as a known limit.

## Step 2 (by 18:30): outlook data, branch `outlook/data`
From the spec: P1, P2 and the climatology part of P3, with these cuts:
- P1 as written (0.15 deg = 3 x 3 fine cells, C10, C11, the mask: water 17/255/nodata,
  barren 16, ice 15, < 5% burnable in every year). MCD12Q1 only: no `source` parameter for
  MCD12C1 and no MCD12C1 tests. The grid-edge task's `cell_range` doesn't exist yet: write a
  0.15 deg center-in-box helper with integer math in firecal/outlook/grid.py.
- Wetlands (IGBP 11) are burnable and must be kept: the peat swamps are where Kalimantan
  burns. Report Central Kalimantan's kept share of cells and of fire.
- P2 as written (C12 + meta). Skip the C15 15 km check and use the spec's fallback: p_fire
  from VIIRS years only (complete years 2013 on) with T = 1; mean/median/expected from the
  full record 2003 on. Record this in the meta file and the Methods text.
- P3, climatology only: C13, and an issue (C14) with model = "climatology" for every lead.
- Backtest-lite (C16): for each test year 2015-2025 and target month, with climatology from
  years before Y only: top-10% capture (share of the month's fire in the 10% of kept cells
  with the highest climatology mean) and the Brier score of p_fire. Pooled and per year.
- Tests to keep (drop the others): g_index -1->-1, -3->-1, -4->-2, -220->-74, 1840->613, and
  the DuckDB expression agrees over range(-3600, 3600); SEA 86,328 cells, the fine_cells
  counts, sum 774,200, area sum 23,186,978 km2; Central Kalimantan 1,015 cells (g_lat -24..4,
  g_lon 738..772); the mask fixture cases; kept + masked = C4 total per year; an area on
  0.15 deg lines with no masked cells equals the calendar total; climatology 3-of-5 = 0.45
  and year Y never read for target year Y; latest 2026-11-14 -> issued 2026-10, targets
  Nov 2026 - Jan 2027.
- Stop and report if the masked share of fire is above 1% or any check fails.
- Report: the granule histogram (17, 255, nodata), cells by mask reason, the masked share of
  fire and the top 20 masked cells, C12 rows and MB, the backtest table, build time and peak
  memory, docs/screenshots/outlook-mask.png. Merge when CI is green, then run build-grid,
  build-monthly and issue on E:\datasets.

## Step 3 (merged by 21:00): outlook in the app, branch `outlook/app`
P4 and P5, cut down:
- Endpoints as in the spec: /api/outlook, /api/outlook/map, /api/outlook.csv,
  /api/cells.csv, /api/cells.parquet. Area range = p25-p75 of the area's monthly totals over
  the baseline years (from C12 at query time), shown as "typical range"; no block
  quantiles. Leave out pct_vs_normal and the "vs average" map view (they need the model).
  `skill` carries the backtest-lite numbers; /api/methods gets a short outlook section.
- Mocks from the real app (make_mocks.py); the contract test passes.
- UI: Outlook tab in the Watchlist slot (tab=outlook) with "Outlook (experimental) ... based
  on past fire patterns, not a weather forecast"; three month cards (typical expected,
  typical range, median, and "So far" for the month in progress); top-10 cells with "Show
  on map"; the 12-bar "When does this area burn?" chart; skill tiles (top-10% capture,
  tested on 2015-2025). Map: History | Outlook switch, month switch, chance colors on the
  fixed bins, popup, footer note. Downloads: Outlook CSV, monthly 15 km cells CSV and Parquet.
- Tests: each endpoint 200/400/422/304; the Parquet opens with pyarrow with the right
  columns; tab in hash; cards from the mock; top-cell order; layer switch and the
  5%-falls-in-the-second-bin case; download links. Screenshots docs/screenshots/outlook-*.png.
- Wiring into `pipeline update` (P6) only if everything else is merged by 20:30.
- Not green by 21:00: don't merge. Tonight's submission is then v1.0.2.

## Step 4 (21:00-22:30): submission
- README for judges (branch docs/readme, status item 7): plain intro, a screenshot, coverage
  = Southeast Asia 2003 to the data's latest date, results (from the data after step 1),
  the outlook and what it isn't, how to run (docker compose up with the snapshot as
  ./data), known limits (on-edge grid cells ~1 in 10,000; pre-2012 MODIS +-13%; the NRT
  static sources if step 1 found them; the outlook is climatology only). Delete the blank
  docs/screenshots/stage-6h-hotspot-table-downloads.png. Merge when green.
- Then tag the final commit: v2-southeast-asia-outlook if step 3 merged, otherwise
  v1.0.3-southeast-asia. Snapshot it on E: like the others.
- Draft the GitHub release notes for that tag in your report, for the team lead.
- 22:30: freeze. No merges after. Last report: the final tag, commit, CI run, snapshot.
