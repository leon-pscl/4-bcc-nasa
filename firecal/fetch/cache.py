"""C0 raw cache helpers."""

import hashlib
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path


def bbox_slug(bbox) -> str:
    parts = []
    for v in bbox:
        s = f"{round(float(v), 4):.4f}".rstrip("0").rstrip(".")
        s = s.replace("-", "m")
        parts.append(s)
    return "_".join(parts)


def raw_path(root, source, bbox, date_str, day_range) -> Path:
    slug = bbox_slug(bbox)
    return Path(root) / "firms" / source / slug / f"{date_str}_{day_range}d.csv"


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    os.replace(tmp, path)


def manifest_path(root) -> Path:
    return Path(root) / "firms" / "manifest.jsonl"


def load_manifest(root) -> list:
    p = manifest_path(root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def append_manifest(root, entry: dict) -> None:
    p = manifest_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def is_cached(root, source, bbox, date_str, day_range, manifest=None) -> bool:
    if manifest is None:
        manifest = load_manifest(root)
    for e in manifest:
        if (e.get("source") == source and e.get("date") == date_str
                and e.get("day_range") == day_range and e.get("bbox") == [round(float(x), 4) for x in bbox]):
            return True
    p = raw_path(root, source, bbox, date_str, day_range)
    return p.exists()


def count_rows(body: str) -> int:
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if not lines:
        return 0
    return max(0, len(lines) - 1)


def chunk_end(date_str, day_range) -> date:
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    return d + timedelta(days=day_range - 1)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()