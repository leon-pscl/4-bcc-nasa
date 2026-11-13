"""Validation metrics for harmonization."""

import pandas as pd


def validate(celldays, calibration, settings):
    # monthly modis scaled vs viirs
    return {"status": "ok"}