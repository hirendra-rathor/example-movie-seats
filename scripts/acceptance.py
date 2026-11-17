"""Exercise release checkpoints through real HTTP servers and persistent SQLite.

Run with uv run --locked python scripts/acceptance.py --milestone 1.
Data is temporary by default; --work-dir retains a new scenario database.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import sqlite3
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


def booking(database):
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript((ROOT / "tests/fixtures/release_v1.sql").read_text())
        legacy_id = connection.execute("SELECT id FROM reservations").fetchone()[0]
    body = {"seats": ["A3", "A4"], "request_key": "party-17"}
    with server(database) as base:
        status, legacy = request(base, "GET", f"/reservations/{legacy_id}")
        assert status == 200 and legacy["status"] == "held" and legacy["seats"] == ["A3", "A4"]
        status, cancelled = request(base, "POST", f"/reservations/{legacy_id}/cancel")
        assert status == 200 and cancelled["status"] == "cancelled"
        status, oracle = request(base, "POST", "/reservations", body)
        assert status == 201
        # Keep the reply only as a test oracle. The next request uses the saved key, not its ID.
    with server(database) as base, server(database) as other:
        status, recovered = request(base, "POST", "/reservations", {**body, "seats": ["A4", "A3"]})
        assert status == 200 and recovered == oracle
        assert request(base, "POST", "/reservations", {**body, "seats": ["A1"]})[0] == 409
        path = f'/reservations/{recovered["id"]}'
        status, confirmed = request(base, "POST", path + "/confirm")
        assert status == 200 and confirmed["status"] == "confirmed"
        assert request(other, "POST", path + "/confirm") == (200, confirmed)
        assert request(other, "POST", path + "/cancel")[0] == 409
        assert request(other, "POST", f"/reservations/{legacy_id}/cancel") == (200, cancelled)
        assert request(other, "POST", "/reservations", body) == (200, confirmed)
        barrier = Barrier(2)
        def keyed(base):
            barrier.wait(timeout=5)
            return request(base, "POST", "/reservations", {"seats": ["B1"], "request_key": "concurrent-key"})
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(keyed, [base, other]))
        assert sorted(item[0] for item in outcomes) == [200, 201]
        assert len({item[1]["id"] for item in outcomes}) == 1
        state = request(base, "GET", "/screening")[1]
        assert all(s["status"] == "confirmed" for s in state["seats"] if s["id"] in {"A3", "A4"})
        return {"upgraded_and_cancelled": cancelled, "recovered": recovered, "confirmed": confirmed,
                "same_key_race_statuses": sorted(item[0] for item in outcomes), "screening": state}


def wait_past(deadline):
    remaining = datetime.fromisoformat(deadline).timestamp() - time.time()
    if remaining > 30:
        raise RuntimeError("The acceptance deadline is unexpectedly far away.")
    time.sleep(max(0, remaining) + 0.1)


def expiration(database):
    body = {"seats": ["A3", "A4"], "request_key": "abandoned"}
    with server(database, MOVIE_SEATS_HOLD_SECONDS="6") as base:
        status, abandoned = request(base, "POST", "/reservations", body)
        assert status == 201 and abandoned["expires_at"]
        status, kept = request(base, "POST", "/reservations", {"seats": ["B1", "B2"], "request_key": "kept"})
        assert status == 201
        status, confirmed = request(base, "POST", f'/reservations/{kept["id"]}/confirm')
        assert status == 200 and confirmed["status"] == "confirmed"
    assert time.time() < datetime.fromisoformat(abandoned["expires_at"]).timestamp(), "Server did not stop before the deadline."
    wait_past(abandoned["expires_at"])
    with server(database, MOVIE_SEATS_HOLD_SECONDS="300") as base:
        status, expired = request(base, "GET", f'/reservations/{abandoned["id"]}')
        assert status == 200 and expired["status"] == "expired"
        assert expired["expires_at"] == abandoned["expires_at"]
        assert request(base, "POST", f'/reservations/{abandoned["id"]}/confirm')[0] == 409
        assert request(base, "POST", "/reservations", body) == (200, expired)
        assert request(base, "GET", f'/reservations/{kept["id"]}') == (200, confirmed)
        status, replacement = request(base, "POST", "/reservations", {**body, "request_key": "replacement"})
        assert status == 201 and replacement["id"] != abandoned["id"]
        return {"expired": expired, "confirmed": confirmed, "replacement": replacement,
                "screening": request(base, "GET", "/screening")[1]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--milestone", type=int, choices=[1, 2, 3], required=True)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="movie-seats-acceptance-") as temporary:
        directory = args.work_dir or Path(temporary)
        directory.mkdir(parents=True, exist_ok=True)
        database = directory / "seats.sqlite3"
        if database.exists():
            raise SystemExit("Refusing to overwrite an existing scenario database; choose a new --work-dir.")
        observations = {1: holds, 2: booking, 3: expiration}[args.milestone](database)
        report = {"milestone": args.milestone, "result": "passed",
                  "observed_at": datetime.now(timezone.utc).isoformat(), "observations": observations}
        rendered = json.dumps(report, indent=2) + "\n"
        if args.output:
            args.output.write_text(rendered)
        print(rendered, end="")


if __name__ == "__main__":
    main()
