import os
import tempfile
from datetime import date

import pandas as pd

from firecal.config import Settings
from firecal.analytics.area import Area
from firecal.analytics.summary import summary


def test_current_month_same_span():
    with tempfile.TemporaryDirectory() as d:
        os.environ["DATA_PROCESSED"] = d
        settings = Settings()
        rows = []
        # baseline years 2018-2022 November 1 per day
        for y in range(2018, 2023):
            for day in range(1, 31):
                rows.append({"cell_lat_idx": 0, "cell_lon_idx": 0, "tile_id": "0_0",
                            "date_local": date(y, 11, day), "value": 1.0, "basis": "viirs"})
        # current month Nov 1-10 1 per day (2026)
        for day in range(1, 11):
            rows.append({"cell_lat_idx": 0, "cell_lon_idx": 0, "tile_id": "0_0",
                        "date_local": date(2026, 11, day), "value": 1.0, "basis": "viirs"})
        df = pd.DataFrame(rows)
        df.to_parquet(f"{d}/harmonized_daily.parquet", index=False)
        area = Area.from_bbox(0, 0, 0.05, 0.05)
        res = summary(area, "2018-01-01", "2026-11-30", today=date(2026, 11, 10), settings=settings)
        cm = res["current_month"]
        assert cm["value"] == 10.0
        assert cm["median_same_span"] == 10.0
        assert cm["pct_vs_median"] == 0.0