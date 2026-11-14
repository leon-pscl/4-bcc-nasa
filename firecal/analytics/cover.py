"""Land-cover predicate for the `cover` query parameter (C9, D21/D22)."""

from firecal.dataset import read_dataset, COVER

_max_year_cache = {}


def _max_year(settings):
    """Latest cover map year available in C9 (MAX(year)); cached per dataset path."""
    from firecal.dataset import read_dataset, COVER
    cov = read_dataset(settings, COVER)
    if cov.startswith("(SELECT NULL"):
        return None
    if cov not in _max_year_cache:
        import duckdb
        con = duckdb.connect()
        try:
            con.execute("PRAGMA threads=2")
            row = con.execute(f"SELECT MAX(year) FROM {cov}").fetchone()
            _max_year_cache[cov] = int(row[0]) if row and row[0] is not None else None
        finally:
            con.close()
    return _max_year_cache[cov]


COVER_PARAM_VALUES = ("all", "forest", "farmland", "other")
_CLASS_BY_PARAM = {"forest": "('forest')", "farmland": "('farmland')",
                   "other": "('other_vegetation', 'other')"}


def cover_class_sql(alias):
    """cover_class inline enum for the given table alias."""
    return _CLASS_BY_PARAM  # unused convenience for callers building matches


def _cover_year_expr(settings, year_expr):
    maxy = _max_year(settings)
    if maxy is None:
        return "NULL"
    return f"LEAST(CAST({year_expr} AS INTEGER) - 1, {maxy})"


def cover_exists(settings, cover, alias):
    """EXISTS predicate restricting fire cells to the requested class.

    `cover` is one of all|forest|farmland|other. `alias` is the table alias of
    the harmonized/detections/cell-days table being filtered (must carry
    cell_lat_idx, cell_lon_idx, date_local). Cover year is year(D)-1, clamped to
    the latest map year present in C9 (C9, D21).
    """
    if cover == "all":
        return "TRUE"
    if cover not in _CLASS_BY_PARAM:
        raise ValueError(f"unknown cover: {cover}")
    cov = read_dataset(settings, COVER)
    if cov.startswith("(SELECT NULL"):
        return "FALSE"  # no cover data yet: the filter can honestly match nothing
    cover_year = _cover_year_expr(settings, f"EXTRACT(year FROM {alias}.date_local)")
    classes = _CLASS_BY_PARAM[cover]
    return (f"EXISTS (SELECT 1 FROM {cov} c "
            f"WHERE c.cell_lat_idx = {alias}.cell_lat_idx "
            f"AND c.cell_lon_idx = {alias}.cell_lon_idx "
            f"AND c.year = {cover_year} "
            f"AND c.cover_class IN {classes})")


def cover_exists_latlon(settings, cover, alias):
    """EXISTS predicate for tables carrying latitude/longitude/date_local."""
    if cover == "all":
        return "TRUE"
    if cover not in _CLASS_BY_PARAM:
        raise ValueError(f"unknown cover: {cover}")
    grid = getattr(settings, "GRID_DEG", 0.05)
    cov = read_dataset(settings, COVER)
    if cov.startswith("(SELECT NULL"):
        return "FALSE"
    cover_year = _cover_year_expr(settings, f"EXTRACT(year FROM {alias}.date_local)")
    classes = _CLASS_BY_PARAM[cover]
    return (f"EXISTS (SELECT 1 FROM {cov} c "
            f"WHERE c.cell_lat_idx = CAST(FLOOR({alias}.latitude / {grid}) AS INTEGER) "
            f"AND c.cell_lon_idx = CAST(FLOOR({alias}.longitude / {grid}) AS INTEGER) "
            f"AND c.year = {cover_year} "
            f"AND c.cover_class IN {classes})")


def cover_param_note():
    return ("cover restricts fire cells to the IGBP class group: forest (IGBP 1-5), "
            "farmland (IGBP 12,14), other (IGBP 6-11 plus water/urban/ice/unclassified); "
            "cover year is year(fire)-1, clamped to the latest map year present in C9.")
