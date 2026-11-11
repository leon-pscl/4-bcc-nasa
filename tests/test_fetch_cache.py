import tempfile
from pathlib import Path

from firecal.fetch.cache import (
    write_atomic, raw_path, append_manifest, load_manifest, is_cached, bbox_slug,
)


def test_atomic_and_manifest():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        p = raw_path(root, "MODIS_SP", (1, 2, 3, 4), "2024-01-01", 5)
        write_atomic(p, "latitude,acq_date\n")
        assert p.exists()
        append_manifest(root, {"source": "MODIS_SP", "bbox": [1.0, 2.0, 3.0, 4.0], "date": "2024-01-01", "day_range": 5})
        m = load_manifest(root)
        assert len(m) == 1
        assert is_cached(root, "MODIS_SP", (1, 2, 3, 4), "2024-01-01", 5, m)


def test_bbox_slug():
    assert "m" in bbox_slug((-64.0, -18.0, -60.0, -14.0))