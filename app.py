"""
app.py -- interactive web dashboard for the MODIS / VIIRS comparison.

It reuses every step from compare.py (same numbers as `python compare.py`)
and exposes them over HTTP so the browser can draw maps, charts and tables.

Run locally:   python app.py          ->  http://127.0.0.1:8000
Run in Docker: docker compose up --build -> http://127.0.0.1:8000
"""

import threading
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file

import compare

BASE_DIR = Path(__file__).resolve().parent
SAMPLE_DIR = BASE_DIR / "sample-data"
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"

# Grid sizes offered in the UI (degrees).
GRID_CHOICES = [0.01, 0.02, 0.05, 0.1, 0.2]

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB uploads

# ---------------------------------------------------------------------------
# Cached analysis.  The dashboard re-reads the CSVs only when something that
# affects the result changes (files, grid size or day mode).
# ---------------------------------------------------------------------------
_CACHE = {"key": None, "bundle": None}
_LOCK = threading.Lock()
_STATE = {"source": "sample", "modis": SAMPLE_DIR / "modis.csv", "viirs": SAMPLE_DIR / "viirs.csv"}


def _signature(grid_size, day_mode):
    """Anything that changes the numbers goes into this key."""
    def stamp(path):
        path = Path(path)
        return (str(path), path.stat().st_mtime, path.stat().st_size) if path.exists() else (str(path), 0, 0)

    return (stamp(_STATE["modis"]), stamp(_STATE["viirs"]), float(grid_size), day_mode)


def get_bundle(grid_size, day_mode):
    """Return the cached analysis, rebuilding it only when needed."""
    key = _signature(grid_size, day_mode)
    with _LOCK:
        if _CACHE["key"] != key:
            _CACHE["bundle"] = compare.analysis_bundle(
                _STATE["modis"], _STATE["viirs"], grid_size=grid_size, day_mode=day_mode
            )
            _CACHE["key"] = key
        return _CACHE["bundle"]


def _settings():
    """Read grid size + day mode from the request (query args or JSON body)."""
    payload = request.get_json(silent=True) or {}
    source = payload or request.args

    raw_grid = source.get("grid", GRID_CHOICES[2])
    try:
        grid = float(raw_grid)
    except (TypeError, ValueError):
        grid = compare.GRID_SIZE
    if grid not in GRID_CHOICES:
        grid = min(GRID_CHOICES, key=lambda c: abs(c - grid))

    day_mode = source.get("day_mode", "local")
    day_mode = day_mode if day_mode in ("local", "utc") else "local"
    return grid, day_mode


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    """Tiny liveness probe (used by Docker healthchecks and local tooling)."""
    return jsonify({"status": "ok", "source": _STATE["source"]})


@app.route("/api/state")
def api_state():
    """What data is loaded right now + the UI settings."""
    return jsonify(
        {
            "source": _STATE["source"],
            "modis_file": Path(_STATE["modis"]).name,
            "viirs_file": Path(_STATE["viirs"]).name,
            "grid_choices": GRID_CHOICES,
            "default_grid": compare.GRID_SIZE,
            "valid_extensions": [".csv"],
        }
    )


@app.route("/api/analyze", methods=["GET", "POST"])
def api_analyze():
    """Run (or reuse) the analysis and send the whole report as JSON."""
    grid, day_mode = _settings()
    bundle = get_bundle(grid, day_mode)
    report = dict(bundle["report"])
    report["source"] = _STATE["source"]
    return jsonify(report)


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """Accept a new pair of NASA FIRMS CSVs and switch to them."""
    modis = request.files.get("modis")
    viirs = request.files.get("viirs")
    if not modis or not viirs:
        return jsonify({"error": "Both modis.csv and viirs.csv are required."}), 400

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    modis_path = UPLOAD_DIR / "modis.csv"
    viirs_path = UPLOAD_DIR / "viirs.csv"
    modis.save(modis_path)
    viirs.save(viirs_path)

    # Quick sanity check: the files must at least look like FIRMS data.
    for path in (modis_path, viirs_path):
        header = path.read_text(encoding="utf-8", errors="replace").splitlines()[0].lower()
        if "latitude" not in header or "longitude" not in header or "acq_date" not in header:
            # reject the upload and keep whatever was loaded before
            modis_path.unlink(missing_ok=True)
            viirs_path.unlink(missing_ok=True)
            _STATE.update({"source": "sample", "modis": SAMPLE_DIR / "modis.csv", "viirs": SAMPLE_DIR / "viirs.csv"})
            with _LOCK:
                _CACHE["key"] = None
            return jsonify({"error": f"{path.name} does not look like a NASA FIRMS CSV."}), 400

    _STATE.update({"source": "upload", "modis": modis_path, "viirs": viirs_path})
    with _LOCK:
        _CACHE["key"] = None
    return jsonify({"ok": True, "source": "upload"})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Go back to the bundled sample files."""
    _STATE.update({"source": "sample", "modis": SAMPLE_DIR / "modis.csv", "viirs": SAMPLE_DIR / "viirs.csv"})
    with _LOCK:
        _CACHE["key"] = None
    return jsonify({"ok": True, "source": "sample"})


@app.route("/api/download/<name>")
def api_download(name):
    """Save the outputs with compare.py and hand them to the browser."""
    grid, day_mode = _settings()
    bundle = get_bundle(grid, day_mode)

    allowed = {"combined.csv", "calendar.csv", "calendar.png"}
    if name not in allowed:
        abort(404)

    # Writes all three files; cheap enough for a local tool and it keeps the
    # single source of truth in compare.py.
    compare.save_outputs(bundle["df"], bundle["calendar"], OUTPUT_DIR)
    path = OUTPUT_DIR / name
    if not path.exists():
        abort(404)
    as_attachment = request.args.get("inline") != "1"
    return send_file(path, as_attachment=as_attachment, download_name=name)


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "Files are too large (max 32 MB)."}), 413


if __name__ == "__main__":
    # Development server.  In Docker we run gunicorn instead (see Dockerfile).
    app.run(host="0.0.0.0", port=8000, debug=True)
