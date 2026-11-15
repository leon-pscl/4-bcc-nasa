# Report: step 4 — submission (in progress), 2026-11-15 16:35
Task: inbox/claude-2026-11-15-1350-outlook-override.md, step 4

## Done so far
- README.md rewritten for judges (branch docs/readme @ c2f6575): plain intro + outlook screenshot, coverage (SEA, 2003-01-01 to 2026-11-14), results (CK 2026 numbers, region-wide 585,315 through Nov 14, backtest 62.35% top-10% capture / Brier 0.1132), what the outlook is and is not, how to run (docker compose up with the snapshot as ./data), known limits (climatology only; pre-2012 MODIS ±13% global / ±5.5% held-out here; NRT static sources caveat; on-edge cells ~1 in 10,000; mask drops 0.04% of fire). Blank screenshot deleted (docs/screenshots/stage-6h-hotspot-table-downloads.png).
- P6 (outlook in pipeline update) wired and merged (0bd90de, CI #43691840045 success): after harmonize, `pipeline update` rebuilds changed monthly_cells years and re-issues the outlook (tolerated on failure, recorded as a run warning). write_data_versions now carries monthly_cells and outlook everywhere.
- Step 3 merged earlier: 82fa4ef (CI #132742361466 success).

## Pending (in progress)
- Merge docs/readme when CI is green, then tag the final commit: v2-southeast-asia-outlook (step 3 is merged). Snapshot it to E:\snapshots\v2-southeast-asia-outlook (hard links + SHA-256 manifest).
- Release notes for the tag, drafted in the step-4 final report for the team lead.
- 22:30 freeze.
