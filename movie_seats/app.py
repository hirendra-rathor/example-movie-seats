"""Create the Movie Seats starter HTTP application."""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse


def create_app() -> FastAPI:
    """Build the starter application with an entry page and health endpoint."""
    app = FastAPI(title="Movie Seats", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return """<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Movie Seats</title>
</head>
<body>
    <main>
        <h1>Movie Seats</h1>
        <p>The starter is running. Follow the three build prompts to add reservations.</p>
        <p><a href="/docs">API documentation</a></p>
    </main>
</body>
</html>
"""

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "movie-seats"}

    return app
