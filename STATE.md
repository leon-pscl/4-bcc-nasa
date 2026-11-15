# STATE — 2026-11-15 16:25 Asia/Manila

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
| outlook/pipeline-wiring (P6) | outlook/pipeline-wiring | cc5d4b1 | #43691840045 in progress | — | — | in progress | CI green, then merge |

## Data on the PC

- Latest date in harmonized_daily: 2026-11-14
- data_version: celldays 028172cf74f881b8; detections e1891b9a1dcd7822; harmonized_daily eefaaeca5d9a1664
- Snapshot: E:\snapshots\v1-southeast-asia (hard links of E:\datasets\processed, 133 files, 1.824 GB, made 2026-11-15; manifest.csv with SHA-256 alongside)
- Data root: E:\datasets (raw ~60.3 GB, processed ~4.4 GB incl. _staging 2.57 GB)

## Open questions

None.
