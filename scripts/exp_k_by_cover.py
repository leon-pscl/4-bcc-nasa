"""Experiment: k per tile x month x cover_class, against held-out 2018-2021.

Branch-only experiment (exp/k-cover-class). Does NOT modify the pipeline.

Compares, on the same held-out framework that guards calibration changes
(calibration 2013-2017, validation 2018-2021, outage days excluded on both
sides, VIIRS >= 10 cell-days/month):

  A) baseline: current calibration.parquet (tile x month k, shrink_m=30)
  B) cover-split: k per tile x month x C9 cover_class (forest/farmland/
     other_vegetation/other), same shrinkage hierarchy per class:
     tile x month x class -> tile x class -> all_month x class -> all x class,
     missing class rows fall back to the baseline k hierarchy.

Tag rule: fire's C9 cover (year(D)-1, clamp 2024), matching the API.
"""

import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

import math
import time

import duckdb

CD = "read_parquet('data/processed/celldays/region=southeast_asia/**/*.parquet')"
COV = "read_parquet('data/processed/cell_cover/region=southeast_asia/**/*.parquet')"
CAL = "data/processed/calibration.parquet"
CAL_YEARS = (2013, 2017)
VAL_YEARS = (2018, 2021)
CK_W, CK_S, CK_E, CK_N = 110.7, -3.6, 115.9, 0.8

t0 = time.time()
con = duckdb.connect()
con.execute("PRAGMA threads=4")
con.execute("PRAGMA memory_limit='6GB'")
con.execute("PRAGMA temp_directory='data/processed/_duckdb_tmp'")
print("connected", time.time() - t0, file=sys.stderr, flush=True)

# --- tag celldays with their C9 cover class (fire-date rule) --------------
t0 = time.time()
con.execute(f"""CREATE OR REPLACE TEMP TABLE cd_tag AS
SELECT c.*, COALESCE(cc.cover_class, 'unknown') AS cover_class
FROM {CD} c
LEFT JOIN {COV} cc
  ON cc.region = c.region
 AND cc.cell_lat_idx = c.cell_lat_idx
 AND cc.cell_lon_idx = c.cell_lon_idx
 AND cc.year = LEAST(c.year - 1, 2024)
WHERE platform IN ('Aqua', 'SNPP')
""")
print("cd_tag built", f"{time.time() - t0:.1f}s",
      con.execute("SELECT COUNT(*) FROM cd_tag").fetchone()[0],
      file=sys.stderr, flush=True)
print(con.execute("SELECT cover_class, COUNT(*) FROM cd_tag GROUP BY 1 ORDER BY 2 DESC").fetchall(),
      file=sys.stderr, flush=True)

con.execute(f"CREATE OR REPLACE TEMP VIEW cal_base AS SELECT * FROM read_parquet('{CAL}')")
con.execute("""CREATE OR REPLACE TEMP TABLE outage AS
WITH d AS (SELECT region, date_local, platform FROM cd_tag GROUP BY 1,2,3),
a AS (SELECT region, date_local FROM d WHERE platform='Aqua'),
s AS (SELECT region, date_local FROM d WHERE platform='SNPP')
(SELECT region, date_local FROM a EXCEPT SELECT region, date_local FROM s)
UNION
(SELECT region, date_local FROM s EXCEPT SELECT region, date_local FROM a)
""")
print("outage", con.execute("SELECT COUNT(*) FROM outage").fetchone()[0], file=sys.stderr, flush=True)

CELL_ALL = "TRUE"
CELL_CK = (f"cell_lon_idx*0.05+0.025 >= {CK_W} AND cell_lon_idx*0.05+0.025 < {CK_E} "
           f"AND cell_lat_idx*0.05+0.025 >= {CK_S} AND cell_lat_idx*0.05+0.025 < {CK_N}")


def pairs_baseline(where):
    return con.execute(f"""
        WITH k AS (SELECT region, tile_id, month, k FROM cal_base
                   WHERE platform='Aqua' AND reference='SNPP' AND tile_id <> 'ALL'),
        k_am AS (SELECT region, month, k FROM cal_base
                 WHERE platform='Aqua' AND reference='SNPP' AND tile_id='ALL' AND month BETWEEN 1 AND 12),
        k_all AS (SELECT region, k FROM cal_base
                  WHERE platform='Aqua' AND reference='SNPP' AND tile_id='ALL' AND month = 0),
        aqua_k AS (
          SELECT c.region, EXTRACT(year FROM c.date_local)::INT AS y,
                 EXTRACT(month FROM c.date_local)::INT AS m, COUNT(*)::DOUBLE AS n,
                 COALESCE(k.k, k_am.k, k_all.k) AS kv
          FROM cd_tag c
          LEFT JOIN k ON k.region = c.region AND k.tile_id = c.tile_id
                    AND k.month = EXTRACT(month FROM c.date_local)::INT
          LEFT JOIN k_am ON k_am.region = c.region
                        AND k_am.month = EXTRACT(month FROM c.date_local)::INT
          LEFT JOIN k_all ON k_all.region = c.region
          WHERE c.platform='Aqua' AND ({where})
            AND (c.region, c.date_local) NOT IN (SELECT region, date_local FROM outage)
          GROUP BY 1,2,3,5
        ),
        v AS (
          SELECT region, EXTRACT(year FROM date_local)::INT AS y,
                 EXTRACT(month FROM date_local)::INT AS m, COUNT(*)::DOUBLE AS n
          FROM cd_tag WHERE platform='SNPP' AND ({where})
            AND (region, date_local) NOT IN (SELECT region, date_local FROM outage)
          GROUP BY 1,2,3
        )
        SELECT a.region, a.y, a.m, SUM(a.n * a.kv) AS modis, vi.n AS viirs
        FROM aqua_k a JOIN v vi USING (region, y, m)
        WHERE vi.n >= 10
        GROUP BY 1,2,3,5
    """).fetchall()


# --- cover-split k -----------------------------------------------------------
con.execute(f"""CREATE OR REPLACE TEMP TABLE cov_counts AS
SELECT region, tile_id, EXTRACT(month FROM date_local)::INTEGER AS month,
       cover_class, platform, COUNT(*) AS n
FROM cd_tag
WHERE EXTRACT(year FROM date_local) BETWEEN {CAL_YEARS[0]} AND {CAL_YEARS[1]}
  AND platform IN ('Aqua', 'SNPP')
GROUP BY 1,2,3,4,5
""")
con.execute("""CREATE OR REPLACE TEMP TABLE cov_pairs AS
WITH a AS (SELECT tile_id, month, region, cover_class, SUM(n) AS aqua
           FROM cov_counts WHERE platform='Aqua' GROUP BY 1,2,3,4),
     s AS (SELECT tile_id, month, region, cover_class, SUM(n) AS viirs
           FROM cov_counts WHERE platform='SNPP' GROUP BY 1,2,3,4)
SELECT COALESCE(a.region, s.region) AS region, COALESCE(a.tile_id, s.tile_id) AS tile_id,
       COALESCE(a.month, s.month) AS month, COALESCE(a.cover_class, s.cover_class) AS cover_class,
       COALESCE(a.aqua, 0) AS aqua, COALESCE(s.viirs, 0) AS viirs
FROM a FULL OUTER JOIN s USING (region, tile_id, month, cover_class)
""")
con.execute("""CREATE OR REPLACE TEMP TABLE cov_cal AS
WITH tile_tot AS (SELECT region, cover_class, tile_id, SUM(aqua) AS aqua, SUM(viirs) AS viirs
                  FROM cov_pairs GROUP BY 1,2,3),
month_tot AS (SELECT region, cover_class, month, SUM(aqua) AS aqua, SUM(viirs) AS viirs
              FROM cov_pairs GROUP BY 1,2,3),
all_tot AS (SELECT region, cover_class, SUM(aqua) AS aqua, SUM(viirs) AS viirs
            FROM cov_pairs GROUP BY 1,2),
base AS (
  SELECT p.region, p.tile_id, p.month, p.cover_class, p.aqua, p.viirs,
         tt.aqua AS t_aqua, tt.viirs AS t_viirs,
         mt.aqua AS m_aqua, mt.viirs AS m_viirs,
         gt.aqua AS g_aqua, gt.viirs AS g_viirs
  FROM cov_pairs p
  LEFT JOIN tile_tot tt USING (region, cover_class, tile_id)
  LEFT JOIN month_tot mt USING (region, cover_class, month)
  LEFT JOIN all_tot gt USING (region, cover_class)
)
SELECT region, tile_id, month, cover_class, aqua, viirs, t_aqua, m_aqua,
       (t_viirs + 30 * (g_viirs::DOUBLE / NULLIF(g_aqua, 0)))
         / NULLIF(t_aqua + 30, 0) AS tile_k
FROM base
""")
con.execute("""CREATE OR REPLACE TEMP TABLE k_cover AS
SELECT region, 'Aqua' AS platform, 'SNPP' AS reference, tile_id, month, cover_class,
       CASE WHEN aqua > 0 THEN (viirs + 30 * tile_k) / (aqua + 30) ELSE tile_k END AS k,
       CASE WHEN aqua >= 30 THEN 'tile_month'
            WHEN t_aqua >= 30 THEN 'tile'
            WHEN m_aqua >= 30 THEN 'all_month'
            ELSE 'all' END AS level
FROM cov_cal
""")
print("k_cover rows", con.execute("SELECT COUNT(*) FROM k_cover").fetchone()[0],
      file=sys.stderr, flush=True)
print(con.execute("SELECT cover_class, level, COUNT(*) FROM k_cover GROUP BY 1,2 ORDER BY 1,2").fetchall(),
      file=sys.stderr, flush=True)


def pairs_cover(where):
    return con.execute(f"""
        WITH k_c AS (
          SELECT region, tile_id, month, cover_class, k FROM (
            SELECT region, tile_id, month, cover_class, k,
                   ROW_NUMBER() OVER (PARTITION BY region, tile_id, month, cover_class
                                      ORDER BY CASE level WHEN 'tile_month' THEN 1
                                                           WHEN 'tile' THEN 2
                                                           WHEN 'all_month' THEN 3 ELSE 4 END) = 1 AS keep
            FROM k_cover
          ) WHERE keep
        ),
        ka AS (SELECT region, tile_id, month, k FROM cal_base
               WHERE platform='Aqua' AND reference='SNPP' AND tile_id <> 'ALL'
                 QUALIFY ROW_NUMBER() OVER (PARTITION BY region, tile_id, month
                                            ORDER BY CASE level WHEN 'tile_month' THEN 1
                                                                 WHEN 'tile' THEN 2
                                                                 WHEN 'all_month' THEN 3 ELSE 4 END) = 1),
        kb AS (SELECT region, month, k FROM cal_base
               WHERE platform='Aqua' AND reference='SNPP' AND tile_id='ALL' AND month BETWEEN 1 AND 12),
        kc2 AS (SELECT region, k FROM cal_base
                WHERE platform='Aqua' AND reference='SNPP' AND tile_id='ALL' AND month = 0),
        aqua_k AS (
          SELECT c.region, EXTRACT(year FROM c.date_local)::INT AS y,
                 EXTRACT(month FROM c.date_local)::INT AS m, COUNT(*)::DOUBLE AS n,
                 COALESCE(kc.k, ka.k, kb.k, kc2.k) AS kv
          FROM cd_tag c
          LEFT JOIN k_c kc ON kc.region = c.region AND kc.tile_id = c.tile_id
                          AND kc.month = EXTRACT(month FROM c.date_local)::INT
                          AND kc.cover_class = c.cover_class
          LEFT JOIN ka ON ka.region = c.region AND ka.tile_id = c.tile_id
                    AND ka.month = EXTRACT(month FROM c.date_local)::INT
          LEFT JOIN kb ON kb.region = c.region AND kb.month = EXTRACT(month FROM c.date_local)::INT
          LEFT JOIN kc2 ON kc2.region = c.region
          WHERE c.platform='Aqua' AND ({where})
            AND (c.region, c.date_local) NOT IN (SELECT region, date_local FROM outage)
          GROUP BY 1,2,3,5
        ),
        v AS (
          SELECT region, EXTRACT(year FROM date_local)::INT AS y,
                 EXTRACT(month FROM date_local)::INT AS m, COUNT(*)::DOUBLE AS n
          FROM cd_tag WHERE platform='SNPP' AND ({where})
            AND (region, date_local) NOT IN (SELECT region, date_local FROM outage)
          GROUP BY 1,2,3
        )
        SELECT a.region, a.y, a.m, SUM(a.n * a.kv) AS modis, vi.n AS viirs
        FROM aqua_k a JOIN v vi USING (region, y, m)
        WHERE vi.n >= 10
        GROUP BY 1,2,3,5
    """).fetchall()


def metrics(pairs):
    sel = [p for p in pairs if p[1] in range(VAL_YEARS[0], VAL_YEARS[1] + 1)]
    if not sel:
        return None
    modis = [p[3] for p in sel]
    viirs = [p[4] for p in sel]
    n = len(sel)
    mv = sum(viirs) / n
    mm = sum(modis) / n
    cov = sum((v - mv) * (m - mm) for v, m in zip(viirs, modis)) / n
    sv = math.sqrt(sum((v - mv) ** 2 for v in viirs) / n)
    sm = math.sqrt(sum((m - mm) ** 2 for m in modis) / n)
    r = cov / (sv * sm) if sv and sm else 0.0
    bias = (mm - mv) / mv * 100 if mv else 0.0
    per_year = {}
    for y in range(VAL_YEARS[0], VAL_YEARS[1] + 1):
        sub = [(m, v) for (_, yy, _, m, v) in sel if yy == y]
        if sub:
            mv2 = sum(v for _, v in sub) / len(sub)
            mm2 = sum(m for m, _ in sub) / len(sub)
            per_year[y] = (mm2 - mv2) / mv2 * 100 if mv2 else None
        else:
            per_year[y] = None
    return {"r": r, "bias": bias, "per_year": per_year}


def show(title, pairs):
    m = metrics(pairs)
    if m is None:
        print(title, "no data")
        return
    py = m["per_year"]
    vals = [v for v in py.values() if v is not None]
    spread = max(vals) - min(vals) if vals else None
    tyerr = sorted(abs(v) for v in vals)[len(vals) // 2] if vals else None
    print(f"{title}: r={m['r']:.4f} bias={m['bias']:+.2f}% typ_year_err={tyerr:.2f}% spread(max-min)={spread:.2f}")
    print(f"    per-year bias 2018-2021: {{ {', '.join(f'{y}: {v:+.2f}%' for y, v in py.items())} }}")


print()
base_all = pairs_baseline(CELL_ALL)
base_ck = pairs_baseline(CELL_CK)
show("baseline  region-wide", base_all)
show("baseline  central_kalimantan", base_ck)

cov_all = pairs_cover(CELL_ALL)
cov_ck = pairs_cover(CELL_CK)
show("cover-split region-wide", cov_all)
show("cover-split central_kalimantan", cov_ck)
con.close()
