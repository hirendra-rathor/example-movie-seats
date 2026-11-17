# Movie Seats service image. Reservations live in the /data volume, so a replacement
# container started on the same volume keeps them.
FROM python:3.12.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project
COPY movie_seats ./movie_seats

RUN useradd --system --uid 10001 --no-create-home movie-seats \
    && mkdir /data \
    && chown movie-seats /data

ENV PATH="/app/.venv/bin:$PATH" \
    MOVIE_SEATS_DATABASE=/data/movie-seats.sqlite3
VOLUME ["/data"]
USER movie-seats
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
CMD ["uvicorn", "movie_seats.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
