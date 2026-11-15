"""DuckDB connections from Settings. Every connection goes through here.

web:      DUCKDB_WEB_MEMORY_LIMIT (default 1GB), DUCKDB_WEB_THREADS (default 2)
pipeline: DUCKDB_PIPELINE_MEMORY_LIMIT (default 2GB), DUCKDB_PIPELINE_THREADS (default 4),
          temp_directory=DUCKDB_TEMP_DIR (default /tmp/duckdb, not the bind mount),
          max_temp_directory_size=DUCKDB_MAX_TEMP_DIRECTORY_SIZE (default 20GB)
"""

import os
import re

_LIMIT_RE = re.compile(r"\d+\s*(B|KB|MB|GB|TB)", re.IGNORECASE)


def connect(settings, role="web"):
    import duckdb

    if role == "web":
        limit = getattr(settings, "DUCKDB_WEB_MEMORY_LIMIT", "1GB")
        threads = int(getattr(settings, "DUCKDB_WEB_THREADS", 2))
        temp = None
    else:
        limit = getattr(settings, "DUCKDB_PIPELINE_MEMORY_LIMIT", "2GB")
        threads = int(getattr(settings, "DUCKDB_PIPELINE_THREADS", 4))
        temp = getattr(settings, "DUCKDB_TEMP_DIR", "/tmp/duckdb")
    limit = str(limit).strip()
    if not _LIMIT_RE.fullmatch(limit):
        raise ValueError(f"invalid DuckDB memory_limit: {limit!r}")
    if role != "web":
        max_temp = str(getattr(settings, "DUCKDB_MAX_TEMP_DIRECTORY_SIZE", "20GB")).strip()
        if not _LIMIT_RE.fullmatch(max_temp):
            raise ValueError(f"invalid DuckDB max_temp_directory_size: {max_temp!r}")
    threads = max(1, threads)
    con = duckdb.connect()
    con.execute(f"PRAGMA threads={threads}")
    con.execute(f"PRAGMA memory_limit='{limit}'")
    if temp:
        os.makedirs(temp, exist_ok=True)
        con.execute(f"PRAGMA temp_directory='{temp.replace(os.sep, '/')}'")
        con.execute(f"SET max_temp_directory_size='{max_temp}'")
    return con
