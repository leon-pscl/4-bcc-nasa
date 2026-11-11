import pandas as pd

from firecal.config import Settings
from firecal.ingest.firms_csv import read_firms_csv
from firecal.cells.celldays import build_celldays


def test_legacy_counts_filters_off():
    det = pd.concat([read_firms_csv("sample-data/modis.csv"), read_firms_csv("sample-data/viirs.csv")], ignore_index=True)
    s = Settings()
    s.CONFIDENCE_KEEP = ("low", "nominal", "high")
    cd = build_celldays(det, s)
    # 2026-09-27 MODIS (Terra ∪ Aqua) distinct cells
    day = pd.to_datetime("2026-09-27").date()
    sub = cd[cd["date_local"] == day]
    modis_cells = sub[sub["platform"].isin(["Terra", "Aqua"])]["cell_lat_idx"].count()  # not distinct; use nunique via cell
    # distinct cells per sensor
    modis_distinct = sub[sub["platform"].isin(["Terra", "Aqua"])][["cell_lat_idx", "cell_lon_idx"]].drop_duplicates().shape[0]
    viirs_distinct = sub[sub["platform"] == "SNPP"][["cell_lat_idx", "cell_lon_idx"]].drop_duplicates().shape[0]
    shared = len(set(map(tuple, sub[sub["platform"].isin(["Terra","Aqua"])] [["cell_lat_idx","cell_lon_idx"]].values.tolist())) &
              set(map(tuple, sub[sub["platform"]=="SNPP"][["cell_lat_idx","cell_lon_idx"]].values.tolist())))
    assert modis_distinct == 104
    assert viirs_distinct == 268
    assert shared == 73