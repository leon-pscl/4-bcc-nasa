# Fire outlook on a 15 km grid: spec for tonight (Southeast Asia, climatology only)

The spec for steps 2 and 3 of the 13:50 message, which lists the tests, reports and times.
It's task-fire-outlook.md trimmed to tonight's scope: the GLM model, the 15 km sensor check
(C15), block ranges, the other land-cover source (MCD12C1) and pipeline wiring (P6) come later.
Save it in inbox/ next to the 13:50 message.

## 1. What the user gets
For any area inside the region (same rules as today: a box or point + radius, up to 500,000 km2):
- Where: a map of 15 km cells with each cell's chance of fire activity for each of the next
  three months, plus the ten cells most likely to burn.
- When: the area's usual fire season, month by month.
- How sure: backtest numbers from 2015-2025, shown next to the outlook.
- The data: fires per month per 15 km cell, 2003 to today, as CSV or Parquet; the outlook as CSV.
It is NOT a weather-based fire danger forecast: it learns only from where and when fires
happened before. Label it "Outlook (experimental)" and never call it a fire danger forecast.

## 2. How it fits the pipeline
  land cover GeoTIFFs -> C10 cell_surface (0.05 deg, static) -> C11 grid_cells (0.15 deg, mask)
  C4 harmonized_daily (0.05 deg, daily) -> C12 monthly_cells (0.15 deg, monthly)
  C12 -> C13 climatology -> C14 outlook (issued monthly); C16 backtest-lite
Everything heavy runs in the pipeline (updater image). The web app only reads small Parquet
files with DuckDB, as today. No model runs in the web container.

## 3. The grid: 0.15 deg, three by three of today's cells
g_idx = floor(cell_idx / 3) on each axis, where cell_idx is the existing 0.05 deg index (C2, C4).

| Latitude | N-S | E-W | Area |
|---|---|---|---|
| 0 deg | 16.7 km | 16.7 km | 278 km2 |
| 14.5 deg (Luzon) | 16.7 km | 16.1 km | 269 km2 |
| 28.5 deg (north edge) | 16.7 km | 14.7 km | 244 km2 |

- It nests exactly: each 15 km cell is 9 whole 0.05 deg cells, so its count is an exact sum of
  C4, and areas made of whole 15 km cells match the calendar to the last decimal.
- The calibration carries over: sum the harmonized 0.05 deg values. Never recount "days with
  fire" at 15 km; that would need a new k.
- Integer arithmetic only: no coordinate is divided by 0.15 to find a cell.
- Pitfall, negative indices: int(-1/3) is 0 but must be -1. Use Python // or math.floor, and
  in DuckDB CAST(FLOOR(cell_lat_idx / 3.0) AS INTEGER). Don't use DuckDB's // without a test.
- Edge cells: the box's south (-11.0) and west (92.0) edges aren't on 0.15 deg lines. The south
  row holds 3 of its 9 fine cells, the west column 6, the south-west corner 2. Store
  `fine_cells` and `area_km2` for the part inside.
- Area selection: a 15 km cell is inside an area when its center is, the same rule as today.
  The grid-edge task's cell_range doesn't exist yet, so write a 0.15 deg center-in-box helper in
  firecal/outlook/grid.py that works on integer indices and isn't fooled by float error at the
  edges. The Central Kalimantan test pins it.

Reference numbers for Southeast Asia (tests assert them):
- 264 rows x 327 columns = 86,328 cells
- fine_cells: 85,738 cells with 9, 263 with 6, 326 with 3, 1 with 2; they add up to 774,200
- cell areas add up to the box area, 23,186,978 km2 (sphere, R = 6371 km)
- Central Kalimantan (110.7-115.9E, 3.6S-0.8N): 29 x 35 = 1,015 cells,
  g_lat_idx -24 to 4, g_lon_idx 738 to 772

## 4. Taking out water, deserts and ice (the mask)
A 15 km cell is dropped (keep = false) when less than MASK_MIN_BURNABLE_PCT (5%) of it is
burnable land in EVERY year of the land cover record (MCD12Q1, 2002-2024).
- Burnable: IGBP classes 1-14 (forests, shrublands, savannas, grasslands, wetlands, croplands,
  urban, mosaics). Wetlands (11) must stay: the peat swamps are where Kalimantan burns.
- Not burnable: 17 water, 255 fill (open sea outside the land tiles), the raster's nodata,
  16 barren, 15 permanent snow and ice.
- Count every pixel whatever its QC. The cover filter (D25) counts only QC == 0 pixels and
  drops mostly wetlands and urban land, which are still land. So C9 can't be used for the mask
  (it also has no rows for all-water cells): this needs one more pass over the 23 GeoTIFFs (C10).
- "In every year": take each fine cell's highest burnable share over 2002-2024, then average
  over the 15 km cell weighted by pixel count. This keeps flood plains (Tonle Sap), shifting
  rivers and reservoirs that filled later.
- "Barren", not "dry": no aridity index. Only land with nothing to burn goes.
- The mask comes from the land, never from the fire data: don't keep a cell because it had fires.
- Before writing C10, check one granule's value histogram and report the counts of 17, 255
  and nodata, to confirm how open sea is encoded.
- Masking drops the fires in masked cells (expected: coastal flares, well under 0.5% of the
  total). Report the masked share and the 20 masked cells with the most fire. Stop and report
  if it's above 1%.

## 5. What is counted
Per 15 km cell and month: value = sum of C4.value over its 9 fine cells and the month's days
(local solar dates, as in C4). Unit: "Hotspots (harmonized)", the calendar's unit. At most
9 x 31 = 279 per cell-month.
- Sensor harmonization: C4 already does it (Aqua x k before Feb 2012, S-NPP after,
  NOAA-20/21 x k after S-NPP ended, plus gap fills). Nothing new.
- Time: the month holding latest_date is partial. Flag it (`partial_month` in the meta file)
  and never treat it as a full month.
- Space: partial edge cells and coastal cells carry area_km2 and burnable_pct.
- Chance of fire tonight: "fire activity" means value >= T with T = 1, and p_fire uses VIIRS
  years only (complete years 2013 on). Reason: k makes MODIS totals match VIIRS, but Aqua misses
  small fires, so before 2012 more cell-months read zero, and a chance-of-fire number would learn
  the sensor change as a trend. Means, medians and expected counts use the full record from 2003,
  because k makes the sums match. Record this in the meta file and the Methods text.

## 6. The outlook (climatology only tonight)
### 6.1 Issue month and targets
- The issue month is the last complete month on or before latest_date (complete when
  latest_date is its last day).
  - latest_date 2026-11-14: issued 2026-10; targets Nov 2026 (lead 1), Dec 2026, Jan 2027.
  - latest_date 2026-11-30: issued 2026-11; targets Dec 2026 to Feb 2027.
- A new outlook is issued once a month, when the issue month moves.
- For each kept cell and target month: p_fire, expected (= the climatology mean), the
  climatology numbers, and model = "climatology".
- Lead 1 is usually the month in progress: the UI shows the value observed so far next to it.

### 6.2 Climatology
Per kept cell and calendar month, over the baseline years (complete years before the target
year; from 2013 for p_fire, from 2003 for the rest):
- p_fire = (n_fire_years + m * p_nbr) / (n_years + m): the share of baseline years with
  value >= T, shrunk toward the 5 x 5 neighbourhood (kept cells only), m = 3.
  Example (a test): 3 of 5 years, p_nbr = 0.2, m = 3 -> (3 + 0.6) / 8 = 0.45.
- mean, median, p25 and p75 of value, and rank_in_year (1 = the month with the highest mean).
- For an area, never add up cell medians: fires are patchy. The API computes area numbers from
  monthly_cells at query time: the area's total for that month in each baseline year, then the
  median, mean, p25 and p75 of those totals.
- No look-ahead: climatology for a target in year Y never reads year Y or later.

### 6.3 Backtest-lite (C16)
For each test year Y in 2015-2025 and each target month, with climatology from years before Y only:
- top-10% capture: the share of the month's fire that fell in the 10% of kept cells with the
  highest climatology mean. The plain number for responders: "the top tenth of cells held X%
  of next month's fire".
- the Brier score of p_fire.
Pooled and per year; call out 2015, 2019 and 2023 (the big years).

## 7. Storage
All new tables are Parquet in DATA_PROCESSED, written atomically (staging, check, rename) and
validated by contracts.py on write and read.

C10 cell_surface/region=<r>/part-0.parquet: one row per 0.05 deg cell in the box, including
all-water cells (about 774,200 rows): region, cell_lat_idx, cell_lon_idx (int32), total_px
(int32), water_pct, barren_pct, snow_ice_pct (2024 map), burnable_pct_max, burnable_year_max.

C11 grid_cells/region=<r>/part-0.parquet: 86,328 rows: region, g_lat_idx, g_lon_idx (int32),
center_lat, center_lon ((g + 0.5) x 0.15, 4 decimals, display only, never for filtering),
fine_cells (int8), area_km2, water_pct, barren_pct, snow_ice_pct, burnable_pct, forest_pct,
crop_pct (from C9, latest map, display only), keep (bool), mask_reason (kept, or the largest
non-burnable share: water, barren, snow_ice).

C12 monthly_cells/region=<r>/year=<y>/part-0.parquet: one row per kept cell and month with
value > 0 (zeros are implied; join with C11): month (int8), g_lat_idx, g_lon_idx, value,
value_forest, value_farmland, value_other (the cover split via C9 with the year rule; these can
add up to less than value), fine_celldays (int32). Plus monthly_cells.meta.json: grid, mask
settings, T and the VIIRS-years rule, latest_date, partial_month ({year, month, through_day} or
null), and per year the input fingerprint and the harmonized, kept and masked totals. Write
with write_partition; rebuild only years whose C4 fingerprint changed.

C13 climatology/region=<r>/part-0.parquet: every kept cell x 12 months: g_lat_idx, g_lon_idx,
month, baseline_first, baseline_last, n_years, p_fire, mean, median, p25, p75, rank_in_year.

C14 outlook/region=<r>/year=<issue year>/part-0.parquet: every kept cell x 3 leads per issue:
issued (YYYY-MM), lead (int8), target_year, target_month, g_lat_idx, g_lon_idx, p_fire,
expected, p_fire_clim, mean_clim, model ("climatology"). Each issue is added to its year's
partition, so past outlooks stay.

C16 validation/outlook_<region>.json: the backtest-lite table (pooled and per year) and the
baseline rules.

Example queries (put them in the README):
  -- the 20 cells most likely to burn in December 2026
  SELECT g.center_lat, g.center_lon, o.p_fire, o.expected
  FROM read_parquet('"'"'data/processed/outlook/region=southeast_asia/year=2026/*.parquet'"'"') o
  JOIN read_parquet('"'"'data/processed/grid_cells/region=southeast_asia/*.parquet'"'"') g
    USING (g_lat_idx, g_lon_idx)
  WHERE o.issued = '"'"'2026-10'"'"' AND o.target_year = 2026 AND o.target_month = 12
  ORDER BY o.p_fire DESC LIMIT 20;

  -- fires per month in one cell (centered on 2.025S, 113.925E), 2003 to today
  SELECT year, month, value
  FROM read_parquet('"'"'data/processed/monthly_cells/region=southeast_asia/*/*.parquet'"'"',
                    hive_partitioning = true)
  WHERE g_lat_idx = -14 AND g_lon_idx = 759 ORDER BY year, month;

## 8. API (C6 additions) and settings
Same area rules as today: one region, bbox or point + radius_km, 500,000 km2 limit, 400/422
errors, data_version with an ETag, the response cache. A 15 km cell is inside an area when its
center is.

GET /api/outlook?<area> (illustrative values):
  {"query": {"bbox": [110.7, -3.6, 115.9, 0.8], "area_km2": 282742},
   "issued": "2026-10", "latest_data_date": "2026-11-14",
   "unit": "Hotspots (harmonized)", "grid_deg": 0.15, "threshold": 1,
   "months": [
     {"year": 2026, "month": 11, "lead": 1, "model": "climatology",
      "expected": 320.0, "typical_range": [120.0, 610.0],
      "normal_mean": 320.0, "normal_median": 157.0,
      "observed_so_far": {"through_day": 14, "value": 1260.0},
      "cells_likely": 312},
     "... leads 2 and 3 (observed_so_far: null)"],
   "top_cells": [{"lat": -2.025, "lon": 113.925, "lead": 1, "p_fire": 0.94, "expected": 21.3}],
   "season": {"normal_median": [12 numbers], "normal_mean": [12 numbers],
              "peak_month": 9, "busiest_months": [9, 8, 10]},
   "skill": {"top10_capture_pct": 55.0, "brier": 0.08, "test_years": [2015, 2025]},
   "data_version": "...", "synthetic": false}
- typical_range = p25-p75 of the area's monthly totals over the baseline years.
- cells_likely counts cells with p_fire >= 0.5; top_cells lists 10 per lead.

Other endpoints:
- GET /api/outlook/map?<area>&lead=1 -> {grid_deg, issued, target: {year, month}, model,
  cells: [{lat, lon, p_fire, expected, mean_clim}]}, kept cells only. Coordinates to 3
  decimals, chances to 2, counts to 1. Under 250 KB for a 500,000 km2 area.
- GET /api/outlook.csv?<area>: every kept cell x 3 leads.
- GET /api/cells.csv and /api/cells.parquet ?<area>&start=&end=: the C12 rows for the area
  and dates, with lat/lon centers and the value_* columns. Months without fire have no row.
  Build the Parquet in memory (con.execute(sql).arrow() -> pyarrow -> bytes), no temp file, so
  it works on the read-only data mount. Cap at 2,000,000 rows.
- The outlook endpoints don't take cover: anything but all is a 400 with field "cover".
- /api/methods?region= gains grid (cells by mask reason, the masked share of fire) and outlook
  (the rules and the backtest-lite numbers).
- /api/coverage gains per region outlook: {issued, targets: ["2026-11", "2026-12", "2027-01"]}.
- Add monthly_cells and outlook to write_data_versions; the outlook endpoints use them for the ETag.

Settings (config.py and instructions.md section 5):
| Setting | Default | Why |
|---|---|---|
| OUTLOOK_GRID_DEG | 0.15 | 3 x GRID_DEG; startup refuses a value that isn't a whole multiple of GRID_DEG |
| MASK_NONBURNABLE_CLASSES | (15, 16, 17, 255) | ice, barren, water, fill (plus nodata) |
| MASK_MIN_BURNABLE_PCT | 5.0 | below this in every year, the cell is dropped |
| OUTLOOK_FIRE_THRESHOLD | 1 | the event behind p_fire (VIIRS years only) |
| OUTLOOK_LEADS | 3 | months ahead |
| OUTLOOK_CLIM_SHRINK_M | 3 | years of neighbourhood weight |
| OUTLOOK_NBR | 2 | neighbourhood radius in cells (5 x 5) |
| OUTLOOK_TEST_YEARS | (2015, 2025) | backtest years |

## 9. Frontend
Usual rules (frontend-tasks.md): tokens, CSS Modules, zod schemas in api/schemas.ts, only
client.ts calls fetch, mocks from the real app, keyboard-usable, contrast, color never carries
meaning alone.

Side panel tabs: Comparisons · Outlook · Methods. Outlook takes the unshipped Watchlist's slot,
stored in the hash as tab=outlook.

Outlook tab, top to bottom:
1. Heading "What'"'"'s coming?" and a 12 px --muted line: "Outlook (experimental) from data through
   31 Oct 2026. Based on past fire patterns, not a weather forecast."
2. Three month cards: the month ("November 2026 · in progress"); expected hotspots (mono
   32/600) and "typical range 120-610"; "Typical November (median): 157"; for the month in
   progress, "So far (1-14 Nov): 1,260".
3. "Where?": the 10 cells most likely to see fire in the selected month, each as rank ·
   "2.03°S, 113.93°E" · "94% chance" · "about 21 hotspots", with a month switch
   (Nov | Dec | Jan) and a "Show on map" button that moves the map to the cell.
4. "When does this area burn?": a 12-bar chart of the typical (median) month, the peak in --ink
   and the rest --muted, and "Busiest months: Sep, Aug, Oct".
5. "How reliable is this?": stat tiles "Fire caught by the top 10% of cells" and "Tested on
   2015-2025", then a footnote with the caveat and a link to Methods.

Map: the footer gets a segmented "History | Outlook" control (hash layer=). Outlook mode adds the
month switch (hash lead=1..3). Cells are 0.15 deg rectangles; masked cells aren't drawn.
- Chance colors: the existing 7 YlOrRd colors on fixed bins 0-5, 5-15, 15-30, 30-50, 50-70,
  70-90, 90-100% (a chance of exactly 5% falls in the second bin).
- Popup: "December 2026 · 72% chance of fire activity · about 6 hotspots".
- Footer note: "15 km cells. Sea, lakes, barren land and ice are left out."
- The legend explains "fire activity": at least 1 hotspot in the cell that month.

Downloads: "Outlook CSV" and "Monthly 15 km cells: CSV · Parquet", with the note "One row per
cell and month with fire; months without a row had none."

Methods tab, a short new section "How the outlook works": the grid and the mask in two sentences
with the masked numbers, the method in plain words (the usual pattern per cell and month, the
VIIRS-years rule for chances), and the backtest-lite numbers.

## 10. Files
firecal/outlook/: __init__.py, grid.py (index helpers in Python and DuckDB, the center-in-box
helper), surface.py (C10, reusing the GeoTIFF reader in firecal/landcover/ingest.py), cells.py
(C11), monthly.py (C12), climatology.py (C13), issue.py (C14), backtest.py (C16), cli.py
(python -m firecal.outlook build-grid | build-monthly | issue | backtest --region <name>).
Plus contracts.py, config.py, devdata.py (a synthetic C11 with a few masked cells),
docs/instructions.md, docs/decisions.md (take the next free numbers; record the mask classes,
the climatology-only cut and the VIIRS-years rule).
Tests, reports, branches and times: as in the 13:50 message, steps 2 and 3.
