"""Calendar PNG rendering."""

import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from firecal.analytics import calendar as cal_mod
from firecal.config import Settings


def render_calendar_png(area, start, end, settings=None):
    if settings is None:
        settings = Settings()
    data = cal_mod.calendar_matrix(area, start, end, settings=settings)
    values = data["values"]
    years = data["years"]
    fig, ax = plt.subplots(figsize=(10, len(years) * 0.3 + 2))
    ax.axis("off")
    cmap = plt.cm.YlOrRd
    # draw cells
    for i, y in enumerate(years):
        for m in range(12):
            v = values[i][m]
            if v is None:
                continue
            ax.text(m, -i, f"{v:.0f}", ha="center", va="center", fontsize=6)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()