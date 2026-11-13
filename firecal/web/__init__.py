"""Stage 5: Flask web app."""

from flask import Flask, jsonify, send_from_directory, send_file
import os


def create_app(settings=None):
    if settings is None:
        from firecal.config import Settings
        settings = Settings.from_env()
    app = Flask(__name__)
    app.config["SETTINGS"] = settings

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.route("/")
    def index():
        dist = os.path.join("frontend", "dist")
        if os.path.exists(os.path.join(dist, "index.html")):
            return send_file(os.path.join(dist, "index.html"))
        return "run npm run build", 200

    @app.route("/api/calendar")
    def calendar():
        return jsonify({"ok": True})

    return app