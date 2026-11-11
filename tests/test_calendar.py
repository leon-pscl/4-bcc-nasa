import os
import tempfile
from datetime import date

import pandas as pd

from firecal.config import Settings
from firecal.analytics.area import Area
from firecal.analytics.calendar import calendar_matrix


def test_january_median_includes_zero_months():
    with tempfile.TemporaryDirectory() as d:
        os.environ["DATA_PROCESSED"] = d
        settings = Settings()
        # one cell at (0,0) grid 0.05 -> center 0.025; bbox covers it
        rows = []
        for y in range(2016, 2023):  # 7 baseline years (current 2026? use today default; baseline excludes current year)
            if y in (2016, 2017):
                rows.append({"cell_lat_idx": 0, "cell_lon_idx": 0, "tile_id": "0_0",
                            "date_local": date(y, 1, 15), "value": 10.0, "basis": "viirs"})
        df = pd.DataFrame(rows)
        df.to_parquet(f"{d}/harmonized_daily.parquet", index=False)
        area = Area.from_bbox(0, 0, 0.05, 0.05)
        res = calendar_matrix(area, "2016-01-01", "2022-12-31", today=date(2026, 1, 1), settings=settings)
        jan_idx = 0
        assert res["monthly_median"][jan_idx] == 0.0
        # January 2023 not in range; use 2016 row? anomaly for a zero? Check 2016 value 10 -> anomaly 10
        # Find a year with 0 value in matrix for January (2018)
        yi = res["years"].index(2018)
        assert res["values"][yi][0] == 0.0
        assert res["anomaly"][yi][0] == 0.0
        assert res["anomaly_pct"][yi][0] is None