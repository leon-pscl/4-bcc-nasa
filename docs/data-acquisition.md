# Data acquisition guide

How to get, by hand, the downloadable data the Burning Calendar uses, for its one region,
**Southeast Asia**. Follow it to download everything again from scratch.

| Dataset | Source | What we downloaded | Goes in |
|---|---|---|---|
| Fire hotspots, history | FIRMS **Archive Download** | MODIS, VIIRS S-NPP, NOAA-20, NOAA-21; 2003-01-01 to 2026-11-06; CSV | `data/raw/manual/southeast_asia/` |
| Fire hotspots, recent days | FIRMS **area API** (needs a MAP_KEY) | 2026-11-07 to today, then daily | `data/raw/firms/` (the fetcher writes it) |
| Land cover | NASA **AppEEARS** | MCD12Q1.061, layer LC_Type1, 2002–2024, GeoTIFF | `data/raw/landcover/` |

All paths are relative to the repo root (`C:\Users\Leon\Documents\Github\4-bcc-nasa\`).
`data/raw/` is git-ignored, so nothing here gets committed.

---

## 0. Before you start

### The area

All three downloads use the same box as `config/regions.json`:

| Region | West | South | East | North | As `W,S,E,N` |
|---|---|---|---|---|---|
| `southeast_asia` | 92 | −11 | 141 | 28.5 | `92,-11,141,28.5` |

The downloaded box must match the region box exactly. A larger box adds data the app never
uses. A smaller one makes part of the region look as if it had no fires.

### Accounts

| Account | Used for | Where |
|---|---|---|
| FIRMS sign-in (email + one-time code, or Earthdata Login) | Archive Download | <https://firms.modaps.eosdis.nasa.gov/download/> |
| FIRMS **MAP_KEY** | Area API (recent days) | <https://firms.modaps.eosdis.nasa.gov/api/map_key/> (arrives by email) |
| **Earthdata Login** | AppEEARS (land cover) | <https://urs.earthdata.nasa.gov> |

**Keep the MAP_KEY secret.** It's part of every API URL, so never paste it into chat, logs
or commits. It lives only in `.env` as `FIRMS_MAP_KEY`. When sharing a URL, replace the key
with `KEY`.

---

## 1. FIRMS hotspots: history (Archive Download)

This gives the full 2003-to-last-week record in a few large CSVs, without using any API
transactions.

### 1.1 Submit the request

1. Open <https://firms.modaps.eosdis.nasa.gov/download/> and sign in (email plus code, or
   Earthdata Login).
2. Create a new request and fill in the form:

   | Field | Value |
   |---|---|
   | Area | **Custom Region** (not "World") |
   | Coordinate format | **Lon, Lat**, which reads the box as West, South, East, North |
   | Coordinates | `92,-11,141,28.5` |
   | Fire source | **MODIS C6.1**, **VIIRS S-NPP**, **VIIRS NOAA-20**, **VIIRS NOAA-21** |
   | From / To | `2003-01-01` / **7 days before today** (we used `2026-11-06`) |
   | Format | **CSV** (the default is Shapefile, which the ingest can't read) |
   | Send email confirmation | ticked |

3. Submit. FIRMS creates **one request per satellite**, so you'll see four rows. In the
   request table and emails, SUOMI / suomi = S-NPP, J1 / jpss1 = NOAA-20,
   J2 / jpss2 = NOAA-21.

**Don't touch the "FIRMS WMS Map Key" box** below the request table. "Generate new Map Key"
or "Remove Map Key" would cancel the key in `.env`. You don't need to click Proceed.

Why these settings:

- **NOAA-20 and NOAA-21:** FIRMS lists VIIRS S-NPP data as ending on **2 November 2026**.
  NOAA-20 (from 2018) and NOAA-21 (from 2023) overlap S-NPP and can carry the series
  forward once they're calibrated to it. For now they're stored in detections but not
  harmonized.
- **End date 7 days back:** the archive only holds data older than the last 7 days. The
  area API (section 2) fills the final week.
- **Not "World":** for areas larger than half the globe, FIRMS caps a request at one year
  and a maximum number of fires.

### 1.2 Download the files

FIRMS emails you when each request is ready; the big ones take hours. Each email links to
a zip named `DL_FIRE_<code>_<request id>.zip`. The link contains only the request number,
not your key. Download all of them before the expiry date in the email (45 days for our
requests).

Each zip holds two CSVs. **Both go in the folder:**

- `fire_archive_<code>_<id>.csv`: standard (science-quality) data, most of the record
- `fire_nrt_<code>_<id>.csv`: near-real-time data for the latest months, which standard
  processing hasn't replaced yet

Put them in `data/raw/manual/southeast_asia/`. Keep the zips next to them as the untouched
originals.

**Don't open the CSVs in Excel.** Excel stops at about a million rows and would silently
cut the files short if saved.

### 1.3 What you should end up with

Southeast Asia, requested 2003-01-01 to 2026-11-06 (8 CSVs, about 3.4 GB, about
43.2 million rows):

| Satellite | Request | Code | Part | Size | Rows | Dates |
|---|---|---|---|---|---|---|
| MODIS (Terra + Aqua) | 845004 | `M-C61` | archive | 553 MB | 7,192,065 | 2003-01-01 → 2026-08-31 |
| | | | nrt | 8.6 MB | 101,168 | 2026-09-01 → 2026-11-06 |
| VIIRS S-NPP | 845007 | `SV-C2` | archive | 1.57 GB | 19,933,670 | 2012-01-20 → 2026-07-31 |
| | | | nrt | 50 MB | 608,579 | 2026-08-01 → 2026-11-02 |
| VIIRS NOAA-20 | 845005 | `J1V-C2` | archive | 790 MB | 10,005,522 | 2018-04-01 → 2026-07-31 |
| | | | nrt | 53 MB | 647,615 | 2026-08-01 → 2026-11-06 |
| VIIRS NOAA-21 | 845006 | `J2V-C2` | archive | 319 MB | 4,038,270 | 2023-03-01 → 2026-07-31 |
| | | | nrt | 52 MB | 629,385 | 2026-08-01 → 2026-11-06 |

Checks:

- The archive part ends the month before the NRT part starts: no gap and no overlap.
- Archive files have a `type` column; NRT files don't (those rows are kept).
- Columns otherwise match the area API CSVs.
- `data/raw/manual/southeast_asia/manifest.json` records each file's sha256 and size. To
  check a file by hand in PowerShell: `Get-FileHash <file> -Algorithm SHA256`.
- To count rows without loading a file into memory:
  `duckdb -c "select count(*), min(acq_date), max(acq_date) from read_csv_auto('<file>')"`.

**Don't run the old (pre-Stage S) ingest on these files.** It loads everything into pandas
and runs out of memory at this size.

---

## 2. FIRMS hotspots: recent days (area API)

The archive stops a week before the request date. The area API covers from the next day
(here **2026-11-07**) to today, then the daily updates.

**Cost:** one transaction per requested day per source, whatever the box size. The key
allows 5,000 transactions per 10 minutes; the fetcher stays under 4,000.

### 2.1 With the project's fetcher (normal path)

```powershell
# key in .env as FIRMS_MAP_KEY
python -m firecal.fetch status                                   # key status + data availability
python -m firecal.fetch backfill --region southeast_asia --start 2026-11-07 --dry-run
python -m firecal.fetch backfill --region southeast_asia --start 2026-11-07
python -m firecal.fetch update --region southeast_asia           # each day after that
```

Run one fetch at a time per key: two processes together would go over the limit.

### 2.2 By hand (for a quick check)

```
https://firms.modaps.eosdis.nasa.gov/api/area/csv/KEY/SOURCE/92,-11,141,28.5/DAY_RANGE/YYYY-MM-DD
```

- `DAY_RANGE` is **1 to 5**. FIRMS's page says up to 10, but 10 was rejected. A request
  returns `DATE` to `DATE + DAY_RANGE − 1`. Without a date, it returns the last
  `DAY_RANGE` days.
- `SOURCE` for recent days: `MODIS_NRT`, `VIIRS_SNPP_NRT` (no rows after 2026-11-02),
  `VIIRS_NOAA20_NRT`, `VIIRS_NOAA21_NRT`. `firecal`'s settings list only the MODIS and S-NPP
  sources so far; NOAA-20/21 fetching has to be added before the fetcher pulls them.
- To see where each source starts and ends:
  `https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv/KEY/all`
- The first line of a valid response contains `latitude` and `acq_date`. Anything else
  (for example an invalid-key message) is an error, even with HTTP 200.
- To get the box from a map, draw it on <https://bboxfinder.com> with **Coordinate
  Format = Lng / Lat**; the "Box" value is then `W,S,E,N`. With "Lat / Lng" the order is
  wrong and FIRMS silently returns the wrong area.

---

## 3. Land cover (AppEEARS, MCD12Q1.061)

This is used to split fires by land type (forest, farmland, other vegetation). AppEEARS
crops the 500 m yearly MODIS land cover map to our box and returns GeoTIFFs.

### 3.1 Make the area file

Save this as `southeast_asia_bbox.geojson` (it's the region box):

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": { "name": "southeast_asia" },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[
          [92.0, -11.0], [141.0, -11.0], [141.0, 28.5], [92.0, 28.5], [92.0, -11.0]
        ]]
      }
    }
  ]
}
```

### 3.2 Submit the request

1. Open <https://appeears.earthdatacloud.nasa.gov> and sign in with Earthdata Login.
2. Go to **Extract → Area → Start a new request**.
3. Fill in:

   | Field | Value |
   |---|---|
   | Request name | `southeast_asia_landcover` |
   | Area | upload `southeast_asia_bbox.geojson` |
   | Start / End date | `01-01-2002` / `12-31-2024` |
   | Product | type `MCD12Q1`, choose **MCD12Q1.061** (500 m, yearly) |
   | Layer | **LC_Type1** only (the IGBP land cover type) |
   | File format | **GeoTIFF** |
   | Projection | **Geographic** (WGS84) |
   | "Use calendar date…" | leave unticked |

4. Submit. AppEEARS sends one email when the request starts and another, with the
   download link, when it's done. A box this size can take a few hours. If it's rejected as
   too large, split the box in two (for example at 116.5°E) and make two requests.

### 3.3 Download the files

Download the `.tif` files from the "done" email's link into `data/raw/landcover/`. There's
one per year, 23 in all (2002–2024). Don't rename them: the backend reads AppEEARS's own
names, which include the product, the layer and the year's start day (`doyYYYY001`).

### 3.4 Things to know

- **Classes (IGBP, LC_Type1)** as the backend groups them:

  | Group | Codes |
  |---|---|
  | Forest | 1–5 |
  | Farmland | 12, 14 |
  | Other vegetation | 6–11 |
  | Other | 13, 15, 16 |
  | Excluded | 17 (water), 255 (fill) |

- **Year rule:** a fire on date D uses the map of year(D) − 1, so forest cleared by burning
  isn't already labeled farmland. MCD12Q1.061 runs 2001–2024, so fires in 2025–2026 use
  the 2024 map.
- **2021 onward is less reliable.** NASA warns that the training sites weren't updated, so
  some may have changed, especially after 2021. The backend compares 2021–2024 class
  changes with 2015–2020; if they look abnormal, the rule stops at the 2020 map.
- **Peat:** degraded peat often maps as wetland, grassland or farmland, not forest. The
  label describes the land cover, not the peat.
- **Why not MCD12C1:** MCD12C1 is the same map on our 0.05° grid, but it's only offered as
  global HDF4 files (about 29 GB for 2002–2024), and AppEEARS can't crop it. MCD12Q1 at
  500 m, cropped, is far smaller, and the backend adds it up into 0.05° cells itself.

---

## 4. Other data already in the repo

- `sample-data/modis.csv` and `sample-data/viirs.csv`: FIRMS NRT area API CSVs for East
  Bolivia (box `-64,-18,-60,-14`), UTC 2026-09-26 to 2026-10-01. These are the test
  reference (2,919 rows; see `instructions.md` 2.4), not app data: East Bolivia is a test
  region only. They're committed; don't re-download them.

## 5. Replaced approaches (don't use)

| Approach | Why it was dropped |
|---|---|
| FIRMS yearly country files (`/country/`) | Need a sign-in, follow country borders (every touched country must be downloaded and clipped), bundled as global yearly zips |
| Full-history area API backfill | About 14,000 transactions per region; hours of rate-limited fetching |
| MCD12C1 from Earthdata Search | 29 GB of global HDF4; AppEEARS can't crop it |
