"""Dataset layer: Hive-partitioned Parquet, incremental state and C7 data versions.

Every dataset lives in `data/processed/<name>/` and is partitioned by `region` and
`year` (DuckDB `COPY ... PARTITION_BY (region, year)`), except `cell_cover`, which is
partitioned by `year` only (it is region-agnostic). A state file records, per
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
COVER = "cell_cover"
SERIES_DAYS_FILE = "series_days.parquet"

STATE_FILE = "_state.json"
DATA_VERSION_FILE = "data_version.json"
WRITER_LOCK = "_writer.lock"
# bump when pipeline logic changes in a way that must invalidate partition fingerprints
PIPELINE_VERSION = 5


def processed_root(settings):
    return Path(settings.DATA_PROCESSED)


def acquire_writer_lock(settings):
    """One pipeline writer at a time, via an OS lock held for the life of the process.

    Windows: msvcrt.locking(LK_NBLCK) on one byte. Everywhere else: fcntl.flock LOCK_NB.
    There is no PID check, so there is no stale lock to clean up: the OS releases the
    lock when the process exits, however it exits. Raises SystemExit if another writer
    holds it, so the second process exits with a clear message.
    """
    lock_path = processed_root(settings) / WRITER_LOCK
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise SystemExit(
            f"another pipeline process holds {lock_path}; only one writer runs at a time")
    return fd


def release_writer_lock(fd):
    """Unlock and close the file descriptor from acquire_writer_lock."""
    if fd is None:
        return
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


def dataset_dir(settings, name):
    return processed_root(settings) / name


def _tree_size(path):
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def validate_duckdb_temp_dir(settings):
    """Refuse a DUCKDB_TEMP_DIR the sweep must not empty. Raises SystemExit.

    The sweep deletes everything inside DUCKDB_TEMP_DIR, so a wrong setting must
    not point at (or sit inside/above) real data. Allowed: a dedicated folder
    whose last name contains "duckdb", e.g. /tmp/duckdb.
    """
    temp = getattr(settings, "DUCKDB_TEMP_DIR", None)
    if not temp:
        return
    t = os.path.normcase(os.path.realpath(temp))
    name = Path(t).name.lower()
    if "duckdb" not in name:
        raise SystemExit(
            f"refusing DUCKDB_TEMP_DIR={temp!r}: last folder name must contain 'duckdb'")
    if Path(t).anchor == t:  # filesystem root ("/" or a drive root)
        raise SystemExit(f"refusing DUCKDB_TEMP_DIR={temp!r}: filesystem root")
    refused = {os.path.normcase(os.path.realpath(p)) for p in
               ("/", "/tmp", str(Path.home()), settings.DATA_RAW, settings.DATA_PROCESSED)}
    for other in list(refused):
        if t == other:
            raise SystemExit(f"refusing DUCKDB_TEMP_DIR={temp!r}: equals {other!r}")
    for other in (os.path.normcase(os.path.realpath(settings.DATA_RAW)),
                  os.path.normcase(os.path.realpath(settings.DATA_PROCESSED))):
        sep = os.sep
        if t.startswith(other + sep):
            raise SystemExit(f"refusing DUCKDB_TEMP_DIR={temp!r}: inside {other!r}")
        if other.startswith(t + sep):
            raise SystemExit(f"refusing DUCKDB_TEMP_DIR={temp!r}: above {other!r}")


def sweep_leftovers(settings, log=print):
    """Delete leftovers from killed/crashed runs. Call after taking the writer lock.

    Removes `_part_*` staging dirs anywhere under DATA_PROCESSED, `_staging/`,
    stray `*.tmp` files, and the contents of the DuckDB temp dir. Returns
    (items_removed, bytes_freed); logs one summary line.
    """
    root = processed_root(settings)
    validate_duckdb_temp_dir(settings)
    removed = 0
    freed = 0
    if root.exists():
        for p in sorted(root.rglob("_part_*"), key=lambda p: len(p.parts), reverse=True):
            if p.is_dir() and p.exists():
                freed += _tree_size(p)
                shutil.rmtree(p, ignore_errors=True)
                removed += 1
        staging = root / "_staging"
        if staging.is_dir():
            freed += _tree_size(staging)
            shutil.rmtree(staging, ignore_errors=True)
            removed += 1
        for p in list(root.rglob("*.tmp")):
            if p.is_file():
                try:
                    freed += p.stat().st_size
                    p.unlink()
                    removed += 1
                except OSError:
                    pass
    temp_dir = getattr(settings, "DUCKDB_TEMP_DIR", None)
    if temp_dir and os.path.isdir(temp_dir):
        for child in Path(temp_dir).iterdir():
            freed += _tree_size(child) if child.is_dir() else child.stat().st_size
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                try:
                    child.unlink()
                except OSError:
                    pass
            removed += 1
    log(f"sweep: removed {removed} item(s), freed {freed / 1e9:.2f} GB")
    return removed, freed


def state_path(settings):
    return processed_root(settings) / STATE_FILE


def validation_path(settings, region):
    """Per-region validation file (Stage 7: C5)."""
    d = processed_root(settings) / "validation"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{region}.json"


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


def write_partition(con, sql, settings, name, region, year, post_check=None):
    """Write one (region, year) partition of a dataset.

    The partition is first built in a unique staging dir. `post_check(con, tmp_dir)`,
    when given, runs on the staging copy and must raise on bad data; the target
    partition is only wiped after the check passes, so a failed build never touches
    the existing data. The target partition directory is wiped first so stale files
    from earlier builds can never survive.
    """
    root = dataset_dir(settings, name)
    root.mkdir(parents=True, exist_ok=True)
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="_part_", dir=str(root)))
    con.execute(
        f"COPY ({sql}) TO '{tmp.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD, "
        f"PARTITION_BY (region, year))"
    )
    try:
        # rows written must equal rows the SQL selected; otherwise the target
        # must not be touched. An empty staging dir is a valid empty partition.
        src_n = con.execute(f"SELECT COUNT(*) FROM ({sql})").fetchone()[0]
        if src_n > 0:
            files = list(tmp.rglob("*.parquet"))
            if not files:
                shutil.rmtree(tmp, ignore_errors=True)
                raise ValueError(f"write_partition: SQL selected {src_n} rows but staging holds 0 files "
                                 f"({name}/{region}/{year}) — refusing to publish")
            stg = f"read_parquet('{tmp.as_posix()}/region=*/year=*/*.parquet')"
            dst_n = con.execute(f"SELECT COUNT(*) FROM {stg}").fetchone()[0]
            if src_n != dst_n:
                shutil.rmtree(tmp, ignore_errors=True)
                raise ValueError(
                    f"write_partition row mismatch: selected {src_n} rows, staging holds {dst_n} "
                    f"({name}/{region}/{year}) — refusing to publish")
        if post_check is not None:
            post_check(con, tmp)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    target = root / f"region={region}" / f"year={year}"
    # the staging copy must contain exactly this partition and nothing else; a
    # stray file from another partition would otherwise be moved into the target
    strays = [f for f in tmp.rglob("*.parquet")
              if f.parent.name != f"year={year}" or f.parent.parent.name != f"region={region}"]
    if strays:
        shutil.rmtree(tmp, ignore_errors=True)
        raise ValueError(f"write_partition: staged file(s) for the wrong partition: {strays}")
    if target.exists():
        for old in target.glob("*.parquet"):
            try:
                old.unlink()
            except OSError:
                pass
        shutil.rmtree(target, ignore_errors=True)
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
    if name == COVER:
        if regions is None:
            return f"read_parquet('{root.as_posix()}/**/*.parquet')"
        # cover has no region partition; pages already restrict by cell idx
        return f"read_parquet('{root.as_posix()}/**/*.parquet')"
    if regions:
        parts = [f"read_parquet('{root.as_posix()}/region={r}/**/*.parquet')" for r in regions]
        if len(parts) == 1:
            return parts[0]
        # DuckDB 2.0.0 mishandles a list containing **-globs: use a plain UNION ALL
        return "(" + " UNION ALL ".join(f"SELECT * FROM {p}" for p in parts) + ")"
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
