"""write_partition row-count guard: rows selected must equal rows published."""

import re
from pathlib import Path

import pandas as pd
import pytest


def _tiny_con(real):
    """Fake con that delegates to a real DuckDB connection but runs COPY itself,

    writing only one row into the staging dir the SQL points at — a lossy COPY."""
    class TinyCon:
        def execute(self, sql, *args, **kwargs):
            if isinstance(sql, str) and sql.startswith("COPY"):
                to = re.search(r" TO '([^']+)'", sql).group(1)
                out = Path(to) / "region=x" / "year=2024"
                out.mkdir(parents=True)
                pd.DataFrame({"a": [1], "region": ["x"], "year": [2024]}).to_parquet(
                    out / "data_0.parquet", index=False)
                return None
            return real.execute(sql, *args, **kwargs)
    return TinyCon()


def test_row_mismatch_aborts_and_preserves_target(tmp_path):
    import duckdb
    from firecal.config import Settings
    from firecal.dataset import write_partition

    settings = Settings()
    settings.DATA_PROCESSED = str(tmp_path / "processed")
    target = Path(settings.DATA_PROCESSED) / "detections" / "region=x" / "year=2024"
    target.mkdir(parents=True)
    pd.DataFrame({"a": [101, 102]}).to_parquet(target / "data_0.parquet", index=False)
    canary = (target / "data_0.parquet").read_bytes()

    con = _tiny_con(duckdb.connect())
    with pytest.raises(ValueError, match="row mismatch"):
        write_partition(con, "SELECT 'x' AS region, 2024 AS year, 1 AS a "
                        "UNION ALL SELECT 'x', 2024, 2",
                        settings, "detections", "x", 2024)

    assert (target / "data_0.parquet").read_bytes() == canary, \
        "existing partition was modified by a failed build"


def test_row_match_publishes_and_wipes_target(tmp_path):
    import duckdb
    from firecal.config import Settings
    from firecal.dataset import write_partition

    settings = Settings()
    settings.DATA_PROCESSED = str(tmp_path / "processed")
    con = duckdb.connect()
    write_partition(con, "SELECT 'x' AS region, 2024 AS year, 1 AS a "
                    "UNION ALL SELECT 'x', 2024, 2",
                    settings, "detections", "x", 2024)
    out = Path(settings.DATA_PROCESSED) / "detections" / "region=x" / "year=2024" / "data_0.parquet"
    got = con.execute(f"SELECT COUNT(*) FROM read_parquet('{out.as_posix()}')").fetchone()[0]
    assert got == 2
