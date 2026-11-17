"""Exercise release checkpoints through real HTTP servers and persistent SQLite.

Run with uv run --locked python scripts/acceptance.py --milestone 1.
Data is temporary by default; --work-dir retains a new scenario database.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from threading import Barrier
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def request(base, method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


@contextmanager
def server(database, **settings):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "MOVIE_SEATS_DB": str(database), **settings}
    with tempfile.TemporaryFile(mode="w+") as log:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "movie_seats.app:create_app",
                                    "--factory", "--host", "127.0.0.1", "--port", str(port)],
                                   cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(150):
                if process.poll() is not None:
                    log.seek(0)
                    raise RuntimeError(log.read())
                try:
                    if request(base, "GET", "/health")[0] == 200:
                        break
                except (URLError, ConnectionError):
                    time.sleep(0.05)
            else:
                raise RuntimeError("Uvicorn did not become ready.")
            yield base
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def holds(database):
    with server(database) as base:
        status, held = request(base, "POST", "/reservations", {"seats": ["A3", "A4"]})
        assert status == 201 and held["seats"] == ["A3", "A4"]
    with server(database) as first, server(database) as second:
        assert request(first, "GET", f'/reservations/{held["id"]}') == (200, held)
        status, overlap = request(first, "POST", "/reservations", {"seats": ["A2", "A3"]})
        assert status == 409
        state = request(first, "GET", "/screening")[1]
        assert next(s for s in state["seats"] if s["id"] == "A2")["status"] == "available"
        barrier = Barrier(2)
        def attempt(base):
            barrier.wait(timeout=5)
            return request(base, "POST", "/reservations", {"seats": ["B1"]})
        with ThreadPoolExecutor(max_workers=2) as pool:
            race = list(pool.map(attempt, [first, second]))
        assert sorted(result[0] for result in race) == [201, 409]
        return {"recovered": held, "overlap": {"status": status, "body": overlap},
                "race_statuses": sorted(result[0] for result in race),
                "screening": request(first, "GET", "/screening")[1]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--milestone", type=int, choices=[1], required=True)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="movie-seats-acceptance-") as temporary:
        directory = args.work_dir or Path(temporary)
        directory.mkdir(parents=True, exist_ok=True)
        database = directory / "seats.sqlite3"
        if database.exists():
            raise SystemExit("Refusing to overwrite an existing scenario database; choose a new --work-dir.")
        observations = holds(database)
        report = {"milestone": args.milestone, "result": "passed",
                  "observed_at": datetime.now(timezone.utc).isoformat(), "observations": observations}
        rendered = json.dumps(report, indent=2) + "\n"
        if args.output:
            args.output.write_text(rendered)
        print(rendered, end="")


if __name__ == "__main__":
    main()
