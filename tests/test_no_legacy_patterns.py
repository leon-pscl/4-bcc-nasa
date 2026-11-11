import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "firecal"


def test_no_iterrows_or_apply_axis1():
    for p in ROOT.rglob("*.py"):
        text = p.read_text()
        assert "iterrows(" not in text, f"iterrows in {p}"
        # apply with axis=1
        for line in text.splitlines():
            if ".apply(" in line and "axis=1" in line:
                raise AssertionError(f"apply axis=1 in {p}: {line}")