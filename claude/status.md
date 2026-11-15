# Status

## 2026-11-15 — disk space before cleanup (section 1 of the disk-space task, against `pascual` @ f14a797)

Data lives on `E:/datasets` (`.env`: `DATA_RAW=E:/datasets/raw`, `DATA_PROCESSED=E:/datasets/processed`),
not in the repo. Numbers measured read-only on 2026-11-15.

### Processed (`E:/datasets/processed`)

| Folder | GB |
|---|---|
| `detections` | 1.65 |
| `_staging` | 2.57 |
| `celldays` | 0.14 |
| `harmonized_daily` | 0.05 |
| `cell_cover` | 0.01 |
| `runs`, `validation`, `_duckdb_tmp`, `calibration.parquet`, json files | ~0.00 |
| **Total** | **~4.4** (of which **_staging is 2.57, i.e. ~58%**) |

Leftover `_part_*` folders: ~0.14 GB in `detections/` + `harmonized_daily/` (15 + 10 folders).

### Detections per column (`parquet_metadata('.../detections/*/*/*.parquet')`, `total_compressed_size`)

| Column | GB |
|---|---|
| uid | 0.784 |
| latitude | 0.207 |
| longitude | 0.180 |
| acq_datetime_utc | 0.079 |
| frp | 0.077 |
| brightness | 0.075 |
| bright_t31 | 0.074 |
| date_local | 0.038 |
| scan | 0.031 |
| track | 0.028 |
| confidence_raw | 0.012 |
| rest (type, daynight, confidence_class, version, platform, sensor, processing, source_file) | ~0.01 |

`uid` (md5 hex text) alone is ~47% of the table. The five float64 value columns
(`frp`, `scan`, `track`, `brightness`, `bright_t31`) total ~0.285 GB.

### Raw (`E:/datasets/raw`)

| Folder | GB |
|---|---|
| `manual` (zips 10.96, extracted CSVs 49.10, txt ~0.00) | 60.06 |
| `landcover` | 0.21 |
| `firms`, `firms_country` | 0.01 |
| **Total** | **~60.3** |

### Other

- `data/_quarantine` (in repo): 0.03 GB, `raw/firms/{MODIS_SP,VIIRS_SNPP_SP}/...` (D22 leftovers).
- Docker: daemon was not running; `C:\Users\Leon\AppData\Local\Docker\wsl\disk\docker_data.vhdx` = 3.88 GB, `main\ext4.vhdx` = 0.09 GB (before `docker system df`).

### After (fix/disk-space, before section 2 runs)

The fixes stop new waste; no bytes are deleted until the team lead runs section 2
(or the next pipeline run sweeps). Projected once the sweep runs at the next start:

| What | Freed |
|---|---|
| `_staging` (2.57 GB) | deleted by the next run's sweep / end of ingest |
| `_part_*` leftovers (~0.14 GB) | deleted by the next run's sweep |
| DuckDB spill | next run empties `DUCKDB_TEMP_DIR` after the lock |

**Processed total after the sweep: ~1.71 GB** (detections 1.65 + celldays 0.14 +
harmonized 0.05 + cell_cover 0.01 + ~0.00 rest), i.e. **~2.7 GB reclaimed** with no
data change. Raw stays ~60.3 GB until section 2 step 5 (delete extracted CSVs: 49.10 GB).
Detections column sizes are unchanged by this branch; 3E (`fix/c1-slim`) targets `uid` (0.784 GB).
