"""Stage 5 web app: re-exports `create_app` (routes live in routes.py)."""

from firecal.web.routes import create_app

__all__ = ["create_app"]
