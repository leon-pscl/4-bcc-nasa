"""Summary analytics."""

import pandas as pd


def summary(area, start, end, today, harmonized_path):
    cal = None
    try:
        from firecal.analytics.calendar import calendar_matrix
        cal = calendar_matrix(area, start, end, today, harmonized_path)
    except Exception:
        pass
    return {"calendar": cal, "today": str(today)}