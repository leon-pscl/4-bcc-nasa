"""Flask app factory."""

from flask import Flask, send_from_directory
from pathlib import Path

from firecal.config import Settings


def create_app(settings=None):
    if settings is None:
        settings = Settings()
    app = Flask(__name__)
    app.config["SETTINGS"] = settings

    from firecal.web.routes import register_routes
    register_routes(app, settings)

    # serve frontend dist if present
    dist = Path("frontend/dist")
    if dist.exists():
        @app.route("/")
        def index():
            return send_from_directory(dist, "index.html")

        @app.route("/assets/<path:p>")
        def assets(p):
            return send_from_directory(dist / "assets", p)
    else:
        @app.route("/")
        def index():
            return "Run npm run build in frontend/ (or use npm run dev).", 200

    return app