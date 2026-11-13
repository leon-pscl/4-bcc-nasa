"""Export hotspot rows."""

import pandas as pd


def hotspot_rows(area, start, end, harmonized_path=None, detections_path=None, all_sensors=False):
    if detections_path and os_path_exists(detections_path):
        df = pd.read_parquet(detections_path)
        # filter area by lat/lon? simple: all rows
        yield df
    else:
        yield pd.DataFrame()


def os_path_exists(p):
    import os
    return os.path.exists(p)