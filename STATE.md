# STATE — 2026-11-18 00:40 Asia/Manila

| task | branch | last commit | CI (run, conclusion) | merged into pascual (hash) | tag | status | waiting on |
|---|---|---|---|---|---|---|---|
| Handoff channel setup | handoff | a5f6cc0 | n/a (no CI on handoff) | n/a | — | done | nothing |
| fix/disk-space (A) | fix/disk-space | 00eac28 | #89, #93, #94 success; merge #96 success | 8ecf10b | — | done | nothing |
| Tag v1-southeast-asia (B) | — | — | #95 success (tag push) | — | v1-southeast-asia → f14a797 | done | nothing |
| Data snapshot v1 (C) | — | — | n/a | n/a | — | done | nothing |
| Raw CSV checks (D) | — | — | n/a | n/a | — | done | nothing |
| fix/map-draw | fix/map-draw | 07ac80a | #90 success; #91 success; #92 success | 3e9e3c6 | — | done | nothing |
| fix/area-key (E(a)) | fix/area-key | 221ae62 | #97 success | not merged | — | done (unmerged) | nothing — merge on request |
| fix/c1-slim 3E (F) | fix/c1-slim | 93f3367 | #98 in progress | not merged | — | waiting | Claude go-ahead to run the migration on E:\datasets (runs right before grid-edge rebuild); confirm #98 green |
| outlook/data (step 2) | outlook/data | 3cff842 | #132727816142 success | 94cf7ce | v1.0.2-southeast-asia (safety tag, pre-outlook) | done | nothing — post-merge builds on E: (build-grid, build-monthly, issue) done |
| outlook/app (step 3) | outlook/app | e7d09a0 | #132742361466 success | 82fa4ef | — | done | nothing |
| outlook/pipeline-wiring (P6) | outlook/pipeline-wiring | cc5d4b1 | #43691840045 success | 0bd90de | — | done | nothing |
| docs/readme (step 4) | docs/readme | c2f6575 | #132744901700 success | 26457b5 | v2-southeast-asia-outlook → 26457b5 | done | nothing |
| Release v2.0.1 (cloud) | releasex | e93b2af | n/a (tag on releasex) | n/a | v2.0.1 → e93b2af | done | owner fast-forward main to v2.0.1 |
| Release v2.1 (Azure merge) | release/v2.1 | 95e80d7 | n/a (merge into pascual) | 95e80d7 | v2.1-southeast-asia-outlook → 95e80d7 | done | owner FF main via `git push origin v2.1-southeast-asia-outlook^{commit}:refs/heads/main`; team-lead uploads processed_data_v2.zip |
| Release v2.1.1 (rows_note) | pascual | 116cae4 | #138 success | 116cae4 | v2.1.1-southeast-asia-outlook → 116cae4 | done | nothing — main since fast-forwarded to v2.2.4 |
| Release v2.2 … v2.2.4 (UI polish, typecheck fix) | pascual | 7ed9934 | #154 success (v2.2.4) | 7ed9934 | v2.2/v2.2.1/v2.2.2/v2.2.3/v2.2.4-southeast-asia-outlook → cd700c0/9c5f675/621d2ec/ff9ff74/7ed9934 | done | nothing — `origin/main` = 7ed9934 |
| cleanup: sample-data, docs refs, FIRMS CSVs | pascual | ab3e552 | no own run (pushed with 6189cad); covered by #157 success | ab3e552 | — | done | nothing |
| cleanup: drop inbox task notes | pascual | 6189cad | #157 success | 6189cad | — | done | nothing |
| fix/clear-errors (calendar cause, hotspots loading) | fix/clear-errors | 9d9f07d | #158 success; merge #159 success | 852f7b3 | — | done | nothing |
| fix/hotspot-error (hotspot query error) | fix/hotspot-error | ef3b72b | #160 success; merge #161 success | ef07e85 | — | done | nothing |

## Data on the PC

- Live deployment checked by the owner 2026-11-18: `/health` ok, `data_version eefaaeca5d9a1664`, latest date 2026-11-14, 75 partitions packaged in `data/processed`, `/api/hotspots` returns rows. (A screenshot showing "Full record end 2026-11-07" came from a different instance, not this one.)
- Latest date in harmonized_daily: 2026-11-14
- data_version: celldays 028172cf74f881b8; detections e1891b9a1dcd7822; harmonized_daily eefaaeca5d9a1664
- Snapshot: E:\snapshots\v1-southeast-asia (hard links of E:\datasets\processed, 133 files, 1.824 GB, made 2026-11-15; manifest.csv with SHA-256 alongside)
- Snapshot v1.0.2: E:\snapshots\v1.0.2-southeast-asia (hard links of E:\datasets\processed, 138 files, manifest.csv with SHA-256)
- Snapshot v2: E:\snapshots\v2-southeast-asia-outlook (hard links incl. outlook datasets, 168 files, ~1.86 GB, manifest.csv with SHA-256)
- Data root: E:\datasets (raw ~60.3 GB, processed ~4.4 GB incl. _staging 2.57 GB)

## Open questions

None.
