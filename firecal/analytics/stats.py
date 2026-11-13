"""Shared statistics helpers for analytics."""


def median(values, upper_middle=False):
    """Median of a sequence of numbers, or None if empty.

    With upper_middle=True and an even count, returns the upper of the two
    middle values instead of their mean.
    """
    vals = sorted(v for v in values if v is not None)
    n = len(vals)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return vals[mid]
    if upper_middle:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0
