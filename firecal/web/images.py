"""Calendar PNG rendering (Stage 5), matching the UI's binned ramps (section 8).

Sequential counts use ColorBrewer YlOrRd, 7 classes, quantile-binned on the
non-zero monthly values; zero gets a neutral color outside the ramp, and
out-of-range months are left blank. Cell text color is picked from the
background luminance.
"""

import io

import numpy as np

YLORRD = ["#ffffb2", "#fed976", "#feb24c", "#fd8d3c", "#fc4e2a", "#e31a1c", "#b10026"]
ZERO_COLOR = "#f5f5f5"
MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _bin_edges(nz):
    edges = np.quantile(nz, np.linspace(0, 1, 8))
    edges = np.unique(edges)
    if edges.size < 2:
        edges = np.array([nz.min(), nz.max() if nz.max() > nz.min() else nz.min() + 1e-9])
    edges[0], edges[-1] = nz.min(), nz.max()
    return edges


def render_calendar_png(years, values):
    """values: one row per year, one cell per month; None = out of range."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm, to_rgb

    grid = np.array([[np.nan if v is None else float(v) for v in row]
                     for row in values], dtype=float)
    finite = grid[np.isfinite(grid)]
    nz = finite[finite > 0]

    fig, ax = plt.subplots(figsize=(12, max(4, len(years) * 0.35)))

    if nz.size:
        edges = _bin_edges(nz)
        cmap = ListedColormap(YLORRD)
        norm = BoundaryNorm(edges, len(YLORRD))
        nonzero = np.where(grid > 0, grid, np.nan)
        masked = np.ma.masked_invalid(nonzero)
        cmap.set_bad(alpha=0.0)
        ax.imshow(masked, cmap=cmap, norm=norm)
        im = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap)
        fig.colorbar(im, ax=ax, label="Hotspots (harmonized)")
        for i in range(len(years)):
            for j in range(12):
                v = grid[i, j]
                if np.isnan(v):
                    continue
                cell_rgb = to_rgb(ZERO_COLOR) if v == 0 else cmap(norm(v))[:3]
                if v == 0:
                    ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1,
                                               facecolor=ZERO_COLOR, zorder=2))
                r, g, b = cell_rgb[:3]
                lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=6,
                        color="#1a1a1a" if lum > 0.5 else "#ffffff", zorder=3)
    else:
        ax.imshow(np.full_like(grid, np.nan), cmap=ListedColormap([ZERO_COLOR]))

    ax.set_xticks(range(12))
    ax.set_xticklabels(MONTH_LABELS)
    ax.set_yticks(range(len(years)))
    ax.set_yticklabels(years)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
