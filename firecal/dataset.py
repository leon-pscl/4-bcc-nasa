"""Dataset layer: Hive-partitioned Parquet, incremental state and C7 data versions.

Every dataset lives in `data/processed/<name>/` and is partitioned by `region` and
`year` (DuckDB `COPY ... PARTITION_BY (region, year)`). A state file records, per
partition, a fingerprint of the inputs it was built from; only partitions whose
inputs changed are rebuilt.
"""

import hashlib
import json
import os
import shutil
from pathlib import Path

DETECTIONS = "detections"
CELLDAYS = "celldays"
HARMONIZED = "harmonized_daily"

STATE_FILE = "_state.json"
DATA_VERSION_FILE = "data_version.json"


def processed_root(settings):
    return Path(settings.DATA_PROCESSED)


def dataset_dir(settings, name):
    return processed_root(settings) / name


def state_path(settings):
    return processed_root(settings) / STATE_FILE


def load_state(settings):
    p = state_path(settings)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def save_state(settings, state):
    p = state_path(settings)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(p) + ".tmp"
    Path(tmp).write_text(json.dumps(state, indent=2, sort_keys=True))
    os.replace(tmp, p)


def fingerprint(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode())
        h.update(b"|")
    return h.hexdigest()


def partition_key(region, year):
    return f"{region}/{year}"


def partitions_of(settings, name):
    """Return {partition_key: {'region':.., 'year':..}} for a dataset."""
    root = dataset_dir(settings, name)
    out = {}
    if not root.exists():
        return out
    for region_dir in root.glob("region=*"):
        region = region_dir.name.split("=", 1)[1]
        for year_dir in region_dir.glob("year=*"):
            year = year_dir.name.split("=", 1)[1]
            out[partition_key(region, year)] = {"region": region, "year": int(year)}
    return out


def write_partition(con, sql, settings, name, region, year):
    """Write one (region, year) partition of a dataset.

    The target partition directory is wiped first so stale files from earlier
    builds can never survive. The temp staging dir is unique per call.
    """
    root = dataset_dir(settings, name)
    root.mkdir(parents=True, exist_ok=True)
    # clean orphaned staging dirs left by interrupted writes
    for d in root.glob("_part_*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="_part_", dir=str(root)))
    con.execute(
        f"COPY ({sql}) TO '{tmp.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD, "
        f"PARTITION_BY (region, year))"
    )
    target = root / f"region={region}" / f"year={year}"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    for f in tmp.rglob("*.parquet"):
        os.replace(f, target / f.name)
    for d in sorted(tmp.rglob("*"), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    if tmp.exists():
        shutil.rmtree(tmp)


def read_dataset(settings, name, regions=None):
    """SQL fragment reading a dataset (all partitions or a region subset)."""
    root = dataset_dir(settings, name)
    if not root.exists():
        return "(SELECT NULL WHERE FALSE)"
    if regions:
        parts = [f"'{root.as_posix()}/region={r}/**/*.parquet'" for r in regions]
        return "read_parquet([" + ", ".join(parts) + "])"
    return f"read_parquet('{root.as_posix()}/region=*/**/*.parquet')"


def data_version(settings, name):
    """C7 data version for a dataset: hash of the partition fingerprints."""
    state = load_state(settings)
    ds = state.get(name, {})
    keys = sorted(ds.keys())
    h = hashlib.sha256()
    for k in keys:
        h.update(k.encode())
        h.update(str(ds[k]).encode())
    return h.hexdigest()[:16]


def write_data_versions(settings, names):
    """Write data_version.json for the given datasets."""
    versions = {n: data_version(settings, n) for n in names}
    p = processed_root(settings) / DATA_VERSION_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(p) + ".tmp"
    Path(tmp).write_text(json.dumps(versions, indent=2, sort_keys=True))
    os.replace(tmp, p)
    return versions
