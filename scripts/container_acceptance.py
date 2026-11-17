"""Verify real Compose container replacement with an isolated retained data volume.

The unique test project is removed, including its own volume, on completion.
It never stops or deletes the user's ordinary Movie Seats project or data.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.error import URLError
from uuid import uuid4

from acceptance import ROOT, request, wait_past


def run(output=None):
    project = "movie-seats-check-" + uuid4().hex[:10]
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {**os.environ, "MOVIE_SEATS_PORT": str(port), "MOVIE_SEATS_HOLD_SECONDS": "6"}
    base = f"http://127.0.0.1:{port}"

    def compose(*args):
        result = subprocess.run(["docker", "compose", "-p", project, *args], cwd=ROOT,
                                env=env, text=True, capture_output=True, timeout=300)
        if result.returncode:
            raise RuntimeError(result.stdout[-4000:] + result.stderr[-4000:])
        return result.stdout.strip()

    def ready():
        for _ in range(100):
            try:
                if request(base, "GET", "/health")[0] == 200:
                    return
            except (URLError, ConnectionError):
                pass
            time.sleep(0.2)
        raise RuntimeError("Container did not become ready.\n" + compose("logs", "--no-color"))

    try:
        print("Building the locked image and starting an isolated Compose project...", flush=True)
        compose("up", "--build", "-d")
        ready()
        first_container = compose("ps", "-q", "movie-seats")
        image = subprocess.check_output(["docker", "inspect", "--format", "{{.Image}}", first_container], text=True).strip()
        user_id = compose("exec", "-T", "movie-seats", "id", "-u")
        assert user_id == "10001"
        body = {"seats": ["A3", "A4"], "request_key": "container-abandoned"}
        status, held = request(base, "POST", "/reservations", body)
        assert status == 201
        status, kept = request(base, "POST", "/reservations", {"seats": ["B1", "B2"], "request_key": "container-kept"})
        assert status == 201
        status, confirmed = request(base, "POST", f'/reservations/{kept["id"]}/confirm')
        assert status == 200
        print("Removing the container while retaining its named volume...", flush=True)
        compose("down")
        assert time.time() < datetime.fromisoformat(held["expires_at"]).timestamp(), "Container did not stop before expiry."
        wait_past(held["expires_at"])
        compose("up", "-d", "--force-recreate")
        ready()
        second_container = compose("ps", "-q", "movie-seats")
        assert second_container != first_container
        status, expired = request(base, "GET", f'/reservations/{held["id"]}')
        assert status == 200 and expired["status"] == "expired"
        assert expired["expires_at"] == held["expires_at"]
        assert request(base, "POST", f'/reservations/{held["id"]}/confirm')[0] == 409
        assert request(base, "POST", "/reservations", body) == (200, expired)
        assert request(base, "GET", f'/reservations/{kept["id"]}') == (200, confirmed)
        status, replacement = request(base, "POST", "/reservations", {**body, "request_key": "container-replacement"})
        assert status == 201 and replacement["id"] != held["id"]
        report = {"result": "passed", "observed_at": datetime.now(timezone.utc).isoformat(),
                  "image_id": image, "runtime_uid": user_id, "container_replaced": True,
                  "same_named_volume": True, "expired": expired, "confirmed": confirmed, "replacement": replacement}
        if output:
            output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        return report
    finally:
        compose("down", "--volumes", "--remove-orphans", "--rmi", "local")
        print("Removed only the isolated test project, its volume and its local image tag.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    run(parser.parse_args().output)
