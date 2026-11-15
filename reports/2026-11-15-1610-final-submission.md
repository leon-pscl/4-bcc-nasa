# Report: outlook steps 2-4 complete — v2-southeast-asia-outlook, 2026-11-15 16:10
Task: inbox/claude-2026-11-15-1350-outlook-override.md (spec inbox/task-fire-outlook.md)
Status: steps 1-4 done and merged; CI green; tag pushed; snapshot on E:. Keeping the 22:30 freeze.

## Final tag / commit / CI / snapshot
- Tag: **v2-southeast-asia-outlook** (annotated) -> 26457b5 (26457b5d8dd02001c64835cb452512ee3804f0db), pushed.
- CI: #43692374391 (pascual, 26457b5) success; #43692056292 (0bd90de) success; #132744901700 (docs/readme) success; #43691840045 (P6 wiring) success; #132742361466 (outlook/app) success; #132727816142 (outlook/data) success.
- Snapshot: **E:\snapshots\v2-southeast-asia-outlook** — hard links of E:\datasets\processed (168 files: detections, harmonized_daily, celldays, cell_cover, cell_surface, grid_cells, monthly_cells, climatology, outlook, runs, validation + top-level files incl. monthly_cells.meta.json and the five-key data_version.json); manifest.csv with SHA-256 + bytes (168 rows). ~1.86 GB.

## GitHub release notes (for the team lead to paste)

# Burning Calendar — v2-southeast-asia-outlook

Judges' submission, NASA Space Apps 2026. Harmonized MODIS+VIIRS fire calendar for
Southeast Asia, 2003-01-01 to 2026-11-14, plus the new **outlook (experimental)**:
a per-cell, per-month estimate of the next three months, learned only from where and
when fires happened before. It is not a weather model and not a fire danger forecast.

## What's new since v1.0.2-southeast-asia
- **Outlook (experimental)**: a 15 km grid (86,328 cells; 26,015 kept after masking
  sea/lakes/barren/ice; wetlands kept) with a per-cell chance of fire activity and an
  expected count for the next three months. Issued monthly (latest: 2026-10 -> targets
  Nov 2026, Dec 2026, Jan 2027). Climatology only; chances from VIIRS years (2013+).
- **Backtest on 2015-2025**: the top 10% of predicted cells held **62.35%** of a month's
  fire; Brier score 0.1132 (2015: 63.0% · 2019: 63.9% · 2023: 63.4%).
- **/api**: /api/outlook, /api/outlook/map, /api/outlook.csv, /api/cells.csv,
  /api/cells.parquet (plus /api/methods grid+outlook and /api/coverage outlook).
- **UI**: Outlook tab (side panel) with month cards, top-10 cell list with "Show on
  map", the 12-month "When does this area burn?" chart, backtest tiles; History|Outlook
  map switch with chance bins (a 5% chance falls in the second bin).
- **Pipeline**: `pipeline update` now rebuilds changed monthly cells and re-issues the
  outlook after harmonize (tolerated on failure).
- Data snapshot: snapshots/v2-southeast-asia-outlook (168 files, manifest.csv with
  SHA-256).

## Numbers worth having in front of you
- Region-wide 2026 (through Nov 14): 585,315 hotspots; peak month Sep (66,520).
- Central Kalimantan 2026: Aug 12,815 · Sep 15,716 · Oct 14,083 · Nov 1-14 1,261
  (61.6% in forest); 1,015 outlook cells, 970 kept.
- Masked cells hold 0.04% of all recorded fire.
- Harmonized calibration r ~0.99, bias ~-2% (methods tab).

## Known limits (also in the README)
- Climatology only: no weather/fuel/ENSO; it is a seasonal pattern, not a drought rating.
- pre-2012 MODIS: ±13% typical error globally (±5.5% here on held-out years).
- NRT files carry no `type` column: ~12.1% of 2026 NRT detections sit in cells with
  known static sources; they remain until the next standard-processing re-ingest.
- Outlook cells are 3x3 fine cells; edge partial cells carry their part's area and counts.

## How to run it
docker compose up --build, with the snapshot's `processed/` copied to ./data.

## Merges since v1.0.2
- outlook/data (94cf7ce): C10-C14 grid/mask/monthly/climatology/issue, C16 backtest-lite.
- outlook/app (82fa4ef): API endpoints, Outlook tab, map Outlook layer, downloads, methods.
- outlook/pipeline-wiring (0bd90de): outlook rebuild inside `pipeline update`.
- docs/readme (26457b5): judges' README.

## Item-by-item vs the 13:50 message
- Step 1 (item 17): NRT rows were NOT missing (verified in detections/celldays/harmonized;
  the harmonized record here is 100% VIIRS after Feb 2012). No ingest/rebuild performed;
  data left as it was; safety tag v1.0.2-southeast-asia pushed (034ac48, CI success) and
  snapshot E:\snapshots\v1.0.2-southeast-asia taken. Measured: 242,342 (12.1%) of 2026 NRT
  detections are in cells with SP type 1/2 detections; top 10 cells in the step-1 report.
  Central Kalimantan: 2026 total 47,005; Aug 12,815 / Sep 15,716 / Oct 14,083 / Nov 1-14
  1,261; forest share 61.6%; region-wide 2026 585,315.
- Step 2 (outlook/data, 18:30): all reference numbers exact (86,328 cells; fine_cells
  85,738/263/326/1 + 774,200; area 23,186,978 km2; CK 1,015). Mask on land only (wetlands
  kept). C12 1,591,365 rows / 11.2 MB; kept+masked=C4 holds per year; masked fire 0.042%.
  Backtest pooled 62.35% / Brier 0.1132. Wetlands kept: CK 970/1,015 cells, 99.9% of fire.
- Step 3 (outlook/app, 21:00): merged at 16:10 with CI green; not green late items: none —
  everything merged, nobody blocked.
- Step 4 (submission): README rewritten (judge-facing, with screenshot); v2 tag; snapshot.

## Deviations / risks carried
- Commit message in outlook/data (3cff842) says fine_cells "259" for the 6-cell group;
  correct count is 263 (report and tests carry the right numbers).
- data_version.json was briefly rewritten with only two keys during the outlook CLI wiring
  (16:0x); repaired within minutes, identical for the three legacy datasets.
- f52bae0 was an in-progress frontend WIP push (tests red at the time); e7d09a0 is the
  tested state and everything merged after it is green.
- Commit c5df924-style "in progress" was avoided everywhere else; outlook/app landed with
  CI green.
- 2026 NRT fire in granule-months near the S-NPP end (Nov 2) is SNPP-only through Nov 2,
  then NOAA-20: correct, but November 2026 is partial and flagged (partial_month).
- state['files'] lost the 3 VIIRS NRT fingerprints at some point before tonight (the 5
  other manual files are recorded); ingest dedups by uid so no duplicates can result, but
  the next bulk ingest will re-stage them once (flag for the owner).
- The 2026-NRT-in-type1/2-cells number (242,342) is measured from the published data and
  is a lower bound on flares; NRT itself can't be filtered tonight.
- Step 1 condition never met, so per the message's own rule the tag v1.0.2 was taken anyway.
