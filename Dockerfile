FROM ghcr.io/astral-sh/uv:0.11.16 AS uv_binary
FROM python:3.12.13-slim

COPY --from=uv_binary /uv /usr/local/bin/uv
WORKDIR /srv/movie-seats
ENV UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-cache \
    && useradd --system --user-group --uid 10001 movie-seats \
    && install -d -o movie-seats -g movie-seats /data
COPY movie_seats ./movie_seats
ENV PATH="/srv/movie-seats/.venv/bin:$PATH" \
    MOVIE_SEATS_DB=/data/movie-seats.sqlite3
USER movie-seats
EXPOSE 8000
CMD ["uvicorn", "movie_seats.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
