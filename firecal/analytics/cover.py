"""Land-cover predicate for the `cover` query parameter (C9, D21/D22)."""

from firecal.dataset import read_dataset, COVER

COVER_PARAM_VALUES = ("all", "forest", "farmland", "other")
_CLASS_BY_PARAM = {"forest": "('forest')", "farmland": "('farmland')",
                   "other": "('other_vegetation', 'other')"}


def cover_class_sql(alias):
    """cover_class inline enum for the given table alias."""
    return _CLASS_BY_PARAM  # unused convenience for callers building matches


def cover_exists(settings, cover, alias):
    """EXISTS predicate restricting fire cells to the requested class.

    `cover` is one of all|forest|farmland|other. `alias` is the table alias of
    the harmonized/detections/cell-days table being filtered (must carry
    cell_lat_idx, cell_lon_idx, date_local). Cover year is year(D)-1, clamped to
    2024 (C9, D21) — fires in 2025+ use the 2024 granule.
    """
    if cover == "all":
        return "TRUE"
    if cover not in _CLASS_BY_PARAM:
        raise ValueError(f"unknown cover: {cover}")
    cov = read_dataset(settings, COVER)
    if cov.startswith("(SELECT NULL"):
        return "FALSE"  # no cover data yet: the filter can honestly match nothing
    cover_year = (f"LEAST(CAST(EXTRACT(year FROM {alias}.date_local) AS INTEGER) - 1, 2024)")
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
    cover_year = (f"LEAST(CAST(EXTRACT(year FROM {alias}.date_local) AS INTEGER) - 1, 2024)")
    classes = _CLASS_BY_PARAM[cover]
    return (f"EXISTS (SELECT 1 FROM {cov} c "
            f"WHERE c.cell_lat_idx = CAST(FLOOR({alias}.latitude / {grid}) AS INTEGER) "
            f"AND c.cell_lon_idx = CAST(FLOOR({alias}.longitude / {grid}) AS INTEGER) "
            f"AND c.year = {cover_year} "
            f"AND c.cover_class IN {classes})")


def cover_param_note():
    return ("cover restricts fire cells to the IGBP class group: forest (IGBP 1-5), "
            "farmland (IGBP 12,14), other (IGBP 6-11 plus water/urban/ice/unclassified); "
            "cover year is year(fire)-1, clamped to 2024.")
