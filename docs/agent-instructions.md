I'm working on the NASA Space Apps challenge "Harmonization of MODIS and VIIRS Hot Spots". I've attached two CSVs downloaded from the NASA FIRMS area API for the same box in eastern Bolivia (west -64, south -18, east -60, north -14):

- modis.csv (source MODIS_NRT). Columns: latitude, longitude, brightness, scan, track, acq_date, acq_time, satellite (Terra/Aqua), instrument, confidence (0-100 number), version, bright_t31, frp, daynight
- viirs.csv (source VIIRS_SNPP_NRT). Same columns, except brightness is bright_ti4, bright_t31 is bright_ti5, and confidence is a letter: l, n or h

Write a Python script (pandas, plain and well commented, I'm a beginner) that does the following:

1. Load both files and add a column `sensor` ("MODIS" or "VIIRS").
2. Build a UTC datetime from acq_date plus acq_time (acq_time is HHMM as an integer, e.g. 18 = 00:18, 1947 = 19:47).
3. Convert to local solar time: local = utc + (longitude / 15) hours. Use the local date as the row's "day".
4. Harmonize confidence: map MODIS 0-29 to low, 30-79 to nominal, 80-100 to high. Map VIIRS l/n/h to low/nominal/high. Keep the original value in its own column too.
5. Put both sensors on a shared grid: cell = (floor(lat / GRID), floor(lon / GRID)), with GRID = 0.05 degrees as a setting at the top of the script.
6. For each local day, find the set of cells that burned for each sensor. Count the cells seen by both, MODIS only and VIIRS only, plus the raw row count per sensor. Flag days where only one sensor has data.
7. Print a summary:
   - rows per sensor
   - average pixel area (scan x track) per sensor
   - the low/nominal/high percentage split per sensor
   - the share of MODIS cells also seen by VIIRS, using only days where both sensors have data
8. Save outputs:
   - combined.csv: all rows with sensor, utc, local time, day, harmonized confidence, cell
   - calendar.csv: one row per day with both / modis_only / viirs_only / modis_rows / viirs_rows
9. Make a simple chart (matplotlib): one horizontal stacked bar per day for both / MODIS only / VIIRS only, saved as calendar.png. Use fixed colors per category: both = green, MODIS only = blue, VIIRS only = orange.

Check your results against these numbers. They came from the same files:
- 654 MODIS rows and 2,265 VIIRS rows
- average pixel area of about 2.3 km² for MODIS and 0.21 km² for VIIRS
- MODIS confidence split of about 1% low / 59% nominal / 40% high; VIIRS about 10% low / 87% nominal / 2.5% high
- local days 27-28 Sep: about 59% of MODIS cells also seen by VIIRS
- 27 Sep: 73 both, 31 MODIS only, 195 VIIRS only

If a number is off, explain why before changing anything. Keep everything in one file I can run with `python compare.py`, and tell me how to install what it needs.