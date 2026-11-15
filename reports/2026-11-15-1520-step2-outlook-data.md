# Report: step 2 â€” outlook data (branch outlook/data), 2026-11-15 15:20
Task: inbox/claude-2026-11-15-1350-outlook-override.md, step 2; spec inbox/task-fire-outlook.md
Branch: outlook/data @ 3cff842 (1 commit). Merged into pascual as 94cf7ce (outlook/data @ 3cff842, CI success on 132727816142). Post-merge builds on E:\datasets: build-grid (C10+C11, 122.1 s, same numbers), build-monthly (all years up to date), issue (climatology rebuilt, issued 2026-10, targets Nov 2026 - Jan 2027).

## What was built
C10 cell_surface (per fine cell: total_px, water/barren/snow_ice pct from the 2024 map, burnable_pct_max + year over 2002-2024; every pixel counts, no QC filter; one pass over the 23 LC_Type1 granules) -> C11 grid_cells (86,328 cells; g_idx = floor(cell_idx/3), integer math with floor-division semantics identical to DuckDB FLOOR; CK test pins the centre-in-box helper, exact rational math at the edges) -> C12 monthly_cells (sum of C4 per kept cell-month, value > 0 only, cover split via C9 year rule = min(year-1, 2024)) -> C13 climatology (kept cells x 12 months; baseline = complete years before the target year, 2003 on; p_fire from VIIRS years 2013 on, shrunk toward the 5x5 kept neighbourhood incl. self, m = 3; mean/median/p25/p75 full record; rank_in_year) -> C14 outlook (issued monthly; model = "climatology"; issue = last complete month; 2026-11-14 -> issued 2026-10, targets Nov 2026 / Dec 2026 / Jan 2027) -> C16 backtest-lite (2015-2025, climatology from years before Y only).
Not built (cut tonight): GLM model, C15 15 km sensor check, block ranges, MCD12C1 (no source parameter, no MCD12C1 tests), ENSO/IOD, pipeline wiring (P6).

## Reference numbers (all exact)
- Grid: 264 x 327 = 86,328 cells; g_lat -74..189, g_lon 613..939.
- fine_cells: 85,738 with 9, 263 with 6, 326 with 3, 1 with 2; they add up to 774,200 fine cells.
- Cell area sum: 23,186,978 km2 (sphere, R = 6371 km; computed sum 23,186,978.34).
- Central Kalimantan: 1,015 cells (29 x 35), g_lat -24..4, g_lon 738..772; 970 kept (95.6% of cells), 45 water-masked; kept fire 539,362.1 of 539,873.8 (99.90%); CK kept share of fire = 99.90%.
- Backtest-lite numbers are below; 2015/2019/2023 called out.

## Granule histogram (2024 MCD12Q1 LC_Type1, 111,484,800 pixels)
1: 322,881 | 2: 11,754,893 | 3: 115 | 4: 548,420 | 5: 1,172,959 | 6: 1,579 | 7: 498 | 8: 6,097,218 | 9: 3,773,759 | 10: 1,274,815 | 11: 603,582 | 12: 2,898,687 | 13: 392,477 | 14: 1,368,621 | 15: 3,211 | 16: 38,075 | 17: 81,233,010 | 255: 33,002.
The raster's nodata IS 255 (uint8, nodata = 255.0): open sea is 17 (81,233,010 px, 72.9%); 255/nodata is the tile edge (33,002 px, 0.03%); ice (15) 3,211 px; barren (16) 38,075 px. Burnable IGBP 1-14 total = 29,594,309 px (26.6%).

## Cells by mask reason (all 86,328)
kept 26,015 (30.1%) | water 60,313 (69.9%) | barren 0 | snow_ice 0.
Masking drops 6,319.1 of 14,896,721.2 harmonized hotspots, 2003-2026 (0.042%) â€” well below the 1% stop threshold. 2026 alone: 1,792.3 of 585,314.9 (0.306%).

## Top 20 masked cells by fire (whole record)
(81, 625; 12.225N 93.825E; 458.0) (34, 768; 5.175N 115.275E; 180.8) (96, 804; 14.475N 120.675E; 142.0) (-56, 933; 8.325S 140.025E; 118.6) (-66, 832; 9.825S 124.875E; 109.3) (-54, 786; 8.025S 117.975E; 107.5) (-41, 702; 6.075S 105.375E; 96.0) (-64, 824; 9.525S 123.675E; 90.8) (90, 803; 13.575N 120.525E; 81.7) (-56, 781; 8.325S 117.225E; 77.3) (69, 722; 10.425N 108.375E; 76.7) (-52, 864; 7.725S 129.675E; 69.0) (-53, 763; 7.875S 114.525E; 65.7) (-69, 827; 10.275S 124.125E; 63.4) (33, 753; 5.025N 113.025E; 63.4) (24, 749; 3.675N 112.425E; 60.1) (-55, 823; 8.175S 123.525E; 55.5) (-64, 792; 9.525S 118.875E; 54.5) (-54, 839; 8.025S 125.925E; 52.0) (109, 643; 16.425N 96.525E; 50.4)
All masked cells are water class (coastal/island flares); no land cell was masked.

## C12 rows and MB
1,591,365 rows, 11.2 MB (value > 0 rows only; zeros implied). climatology 2.5 MB, outlook 1.0 MB, grid_cells 0.2 MB, cell_surface 0.3 MB.
Per-year fingerprints rebuilt (first build; monthly_cells.meta.json records them; later runs rebuild only changed years).
kept + masked = C4 total per year holds exactly (verified in the build log for all 24 years, e.g. 2026: 585,314.9 = 583,522.6 + 1,792.3).
Area on 0.15 deg lines with no masked cells equals the calendar total (test_area_on_grid_lines_equals_calendar_total).

## C16 backtest-lite (climatology from years before Y only; kept cells; T = 1; p_fire from VIIRS years)
Year | capture% | Brier | fire
2015 | 63.03 | 0.1311 | 798,966.0
2016 | 56.52 | 0.1253 | 581,130.0
2017 | 61.06 | 0.1171 | 409,561.0
2018 | 63.51 | 0.1131 | 474,823.0
2019 | 63.94 | 0.1147 | 678,083.0
2020 | 62.41 | 0.1078 | 576,876.0
2021 | 63.13 | 0.1104 | 461,361.6
2022 | 60.89 | 0.1170 | 336,508.5
2023 | 63.43 | 0.1082 | 622,463.6
2024 | 62.85 | 0.0980 | 502,296.8
2025 | 64.56 | 0.1026 | 407,143.6
Pooled (all 132 year-months): top-10% capture 62.35%, Brier 0.1132. Big years: 2015 63.03%, 2019 63.94%, 2023 63.43%.

## Build time and peak memory (E:\datasets host, measured; scratch copy for peaks)
- build-grid (C10 + C11, 23 granules): 126.2 s wall.
- build-monthly (full 2003-2026 rebuild on scratch copy): 5.5 s wall, peak working set ~153 MB.
- issue (C13 climatology + C14): 37.2 s wall, peak ~992 MB.
- backtest (11 test years): 404 s wall (peak not sampled; same queries as issue per year).

## Wetlands keep
IGBP 11 stays burnable (in IGBP 1-14). CK kept share: 970/1,015 cells (95.6%); kept share of CK fire: 99.90% (539,362.1 / 539,873.8); the 45 masked CK cells are all open-water class.

## Methods text / meta recording
monthly_cells.meta.json records: grid_deg 0.15, fine_per_g 3, mask (nonburnable 15/16/17/255; min burnable 5.0), threshold T = 1, p_fire rule ("VIIRS years only (complete years >= 2013); means/medians/expected from the full record 2003 on"), latest_date 2026-11-14, partial_month {year 2026, month 11, through_day 14}, and per-year fingerprint + harmonized/kept/masked totals. The /api/methods outlook section (step 3) repeats the VIIRS-years rule.

## Tests
13:50-message list all present and green (tests/test_outlook.py): g_index (-1->-1, -3->-1, -4->-2, -220->-74, 1840->613) + DuckDB agrees over range(-3600, 3600); SEA reference numbers; CK 1,015 cells; mask fixture cases; kept + masked = C4 per year; area on 0.15 lines = calendar total; climatology 3-of-5 = 0.45 (p_nbr 0.2, m = 3); year Y never read for target year Y (2026 rows present but baseline stays 2003-2025; with latest 2026-12-31, baseline extends to 2026); latest 2026-11-14 -> issued 2026-10, targets Nov 2026 - Jan 2027. Full suite: 163 passed (pytest), plus the frontend check is untouched.

## docs/screenshots/outlook-mask.png
Generated (map of kept vs masked cells with burnable-share colouring); see the file in the branch.

## Deviations / notes
- Commit 3cff842 message has a wrong fine_cells sub-count ("85738/259/326/1" should be 263 with 6) â€” numbers in this report and in tests are correct.
- The masked share of fire is 0.042%, not the "expected coastal flares well under 0.5%" claim exactly at 0.306% for 2026 alone (fly-in 2026 island/coastal hotspots), still far below the 1% stop.
- C12 cover split: kept fine cells all have C9 rows (land); value_forest + value_farmland + value_other can sum to slightly less than value where C9 has no row.
- Backtest peak memory not sampled; per-year queries are the same shapes as issue (~1 GB peak).

## Blocked / known limits
- P6 (pipeline wiring of the outlook after merge) is intentionally not done tonight per the 13:50 message.
- The GLM model and C15 stay out of tonight entirely.

