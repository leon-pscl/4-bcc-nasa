"""Shared statistics helpers for analytics."""


def median(values):
    """Median of a sequence of numbers, or None if empty."""
    vals = sorted(v for v in values if v is not None)
    n = len(vals)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def complete_years_before(rec_start, rec_end, exclude_year):
    """Complete years of the record [rec_start, rec_end] before exclude_year."""
    import pandas as pd
    out = []
    if rec_start is None or rec_end is None:
        return out
    rec_start, rec_end = pd.Timestamp(rec_start), pd.Timestamp(rec_end)
    for y in range(rec_start.year, rec_end.year + 1):
        if y >= exclude_year:
            continue
        if rec_start <= pd.Timestamp(y, 1, 1) and pd.Timestamp(y, 12, 31) <= rec_end:
            out.append(y)
    return out
