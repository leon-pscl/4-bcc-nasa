import os
import time

from firecal.analytics.area import Area
from firecal.analytics.calendar import calendar_matrix
from firecal.config import Settings


def test_calendar_performance():
    os.environ["DATA_PROCESSED"] = "data/synthetic/processed"
    settings = Settings()
    settings.DATA_PROCESSED = "data/synthetic/processed"
    area = Area.from_bbox(-64, -18, -60, -14)
    t = time.time()
    calendar_matrix(area, "2003-01-01", "2024-01-31", settings=settings)
    print("calendar_matrix seconds:", round(time.time() - t, 3))
    assert time.time() - t < 2.0