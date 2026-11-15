# STATE — 2026-11-15 12:50 Asia/Manila

| task | branch | last commit | CI (run, conclusion) | merged into pascual (hash) | tag | status | waiting on |
|---|---|---|---|---|---|---|---|
| Handoff channel setup | handoff | (this commit) | n/a (no CI on handoff) | n/a | — | done | nothing |
| fix/disk-space (A: C2 guard + merge) | fix/disk-space | 0f01de1 | #89 success, #93 success | not merged | — | working | nothing |
| Tag v1-southeast-asia (B) | — | — | — | — | v1-southeast-asia → f14a797 (pending) | working | nothing |
| Data snapshot v1 (C) | — | — | — | — | — | working | nothing |
| Raw CSV checks (D) | — | — | — | — | — | working | nothing |
| fix/map-draw | fix/map-draw | 07ac80a | #90 success; #91 (pascual) success; #92 (v1.0.1-southeast-asia) success | 3e9e3c6 | — | done | nothing |
| fix/area-key (E(a)) | fix/area-key | — | — | — | — | waiting | A (fix/disk-space merge) |
| fix/c1-slim 3E (F) | fix/c1-slim | — | — | — | — | waiting | A (fix/disk-space merge) + Claude go-ahead to migrate E:\datasets |

## Data on the PC

- Latest date in harmonized_daily: 2026-11-14
- data_version: celldays 028172cf74f881b8; detections e1891b9a1dcd7822; harmonized_daily eefaaeca5d9a1664
- Snapshot: none yet (E:\snapshots does not exist); plan: E:\snapshots\v1-southeast-asia (task C)
- Data root: E:\datasets (raw ~60.3 GB, processed ~4.4 GB incl. _staging 2.57 GB)

## Open questions

None.
