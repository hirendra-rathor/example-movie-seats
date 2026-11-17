"""End-to-end checks for the Movie Seats service run by uvicorn.

Start the real server process on a local port, send overlapping holds over
HTTP at the same moment, recover a discarded reply by its hold key, restart
the process and look the holds up again, and start on a milestone 1 file.
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(base_url, method, path, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        base_url + path, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


@contextmanager
def running_server(database_path):
    port = free_port()
    env = {**os.environ, "MOVIE_SEATS_DATABASE": str(database_path)}
    process = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "movie_seats.app:create_app", "--factory",
            "--host", "127.0.0.1", "--port", str(port),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                if request(base_url, "GET", "/health")[0] == 200:
                    break
            except OSError:
                pass
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("uvicorn did not start")
            time.sleep(0.1)
        yield base_url
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_overlapping_holds_over_http_then_lookup_after_restart(database_path):
    with running_server(database_path) as base_url:
        start = threading.Barrier(2)

        def hold(seats):
            start.wait()
            return request(base_url, "POST", "/holds", {"seats": seats})

        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(hold, [["A3", "A4"], ["A4", "B1"]]))

        assert sorted(status for status, _ in replies) == [201, 409]
        (_, winner), = [reply for reply in replies if reply[0] == 201]
        (_, loser), = [reply for reply in replies if reply[0] == 409]
        assert loser["unavailable_seats"] == ["A4"]
        _, seat_map = request(base_url, "GET", "/seats")
        held = [seat["seat"] for seat in seat_map["seats"] if seat["status"] == "held"]
        assert held == winner["seats"]

    with running_server(database_path) as base_url:
        status, found = request(base_url, "GET", f"/reservations/{winner['reservation_id']}")

    assert status == 200
    assert found == winner
    assert found["status"] == "held"


def test_lost_hold_reply_is_recovered_by_key_after_restart(database_path):
    key = {"Idempotency-Key": "7d4c1f0e-lost-reply"}
    with running_server(database_path) as base_url:
        request(base_url, "POST", "/holds", {"seats": ["B2", "B3"]}, key)  # The reply is discarded.

    with running_server(database_path) as base_url:
        found_status, found = request(base_url, "GET", "/holds/7d4c1f0e-lost-reply")
        retry_status, retried = request(base_url, "POST", "/holds", {"seats": ["B2", "B3"]}, key)
        reservation_id = found["reservation_id"]
        confirmations = [request(base_url, "POST", f"/reservations/{reservation_id}/confirm") for _ in range(2)]
        _, seat_map = request(base_url, "GET", "/seats")

    assert (found_status, retry_status) == (200, 200)
    assert retried == found
    assert found["seats"] == ["B2", "B3"]
    assert [status for status, _ in confirmations] == [200, 200]
    assert confirmations[1][1]["status"] == "confirmed"
    booked = [seat["seat"] for seat in seat_map["seats"] if seat["status"] == "booked"]
    assert booked == ["B2", "B3"]


def test_server_upgrades_a_version_1_file_and_settles_its_hold(version_1_file):
    with running_server(version_1_file) as base_url:
        found_status, found = request(base_url, "GET", "/reservations/v1-hold")
        confirm_status, confirmed = request(base_url, "POST", "/reservations/v1-hold/confirm")

    assert (found_status, found["status"], found["seats"]) == (200, "held", ["A3", "A4"])
    assert (confirm_status, confirmed["status"]) == (200, "confirmed")
