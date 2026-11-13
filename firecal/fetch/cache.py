"""Atomic cache + manifest for FIRMS responses."""

import hashlib
import json
import os
from pathlib import Path


def bbox_slug(bbox):
    parts = []
    for v in bbox:
        s = f"{v:.4f}".replace("-", "m")
        parts.append(s)
    return "_".join(parts)


def cache_path(raw_dir, source, bbox, date, day_range):
    d = Path(raw_dir) / "firms" / source / bbox_slug(bbox)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{date}_{day_range}d.csv"


def write_atomic(path, content):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(content)
    os.replace(tmp, path)


def manifest_append(manifest_path, entry):
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def is_fetched(manifest_path, source, bbox, date, day_range):
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        return False
    for line in manifest_path.read_text().splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        if (e.get("source") == source and e.get("bbox") == list(bbox)
                and e.get("date") == date and e.get("day_range") == day_range):
            return True
    return False