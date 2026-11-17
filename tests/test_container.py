"""End-to-end check of the Movie Seats container image built from the Dockerfile.

Build the image, serve holds from one container with a data volume, replace
the container after a hold's deadline has passed, and read the reservations
from the new container. Opt-in: set MOVIE_SEATS_CONTAINER_TESTS=1 with a
running Docker daemon, because the check builds an image and pulls base images.
"""

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOLD_SECONDS = 3


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


pytestmark = [
    pytest.mark.skipif(
        os.environ.get("MOVIE_SEATS_CONTAINER_TESTS") != "1",
        reason="set MOVIE_SEATS_CONTAINER_TESTS=1 to build and run the container image",
    ),
    pytest.mark.skipif(
        os.environ.get("MOVIE_SEATS_CONTAINER_TESTS") == "1" and not docker_available(),
        reason="the Docker daemon is not reachable",
    ),
]


def docker(*args: str) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def request(base_url, method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base_url + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def start_container(image: str, name: str, volume: str) -> str:
    docker(
        "run", "--detach", "--name", name,
        "--publish", "127.0.0.1::8000",
        "--volume", f"{volume}:/data",
        "--env", f"MOVIE_SEATS_HOLD_SECONDS={HOLD_SECONDS}",
        image,
    )
    host_port = docker("port", name, "8000/tcp").splitlines()[0].rsplit(":", 1)[1]
    base_url = f"http://127.0.0.1:{host_port}"
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if request(base_url, "GET", "/health")[0] == 200:
                return base_url
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    raise RuntimeError(docker("logs", name))


@pytest.fixture
def container_names():
    suffix = uuid.uuid4().hex[:8]
    names = {
        "image": f"movie-seats-test:{suffix}",
        "volume": f"movie-seats-test-{suffix}",
        "first": f"movie-seats-test-{suffix}-1",
        "second": f"movie-seats-test-{suffix}-2",
    }
    yield names
    for container in (names["first"], names["second"]):
        subprocess.run(["docker", "rm", "--force", container], capture_output=True)
    subprocess.run(["docker", "volume", "rm", names["volume"]], capture_output=True)
    subprocess.run(["docker", "image", "rm", names["image"]], capture_output=True)


def test_replacement_container_keeps_bookings_and_frees_expired_holds(container_names):
    names = container_names
    docker("build", "--tag", names["image"], str(PROJECT_ROOT))
    docker("volume", "create", names["volume"])

    first = start_container(names["image"], names["first"], names["volume"])
    _, hold = request(first, "POST", "/holds", {"seats": ["A3", "A4"]})
    _, booking = request(first, "POST", "/holds", {"seats": ["B1"]})
    request(first, "POST", f"/reservations/{booking['reservation_id']}/confirm")
    docker("rm", "--force", names["first"])

    time.sleep(HOLD_SECONDS + 1)  # The hold's deadline passes while no container runs.

    second = start_container(names["image"], names["second"], names["volume"])
    _, seat_map = request(second, "GET", "/seats")
    _, found_booking = request(second, "GET", f"/reservations/{booking['reservation_id']}")
    _, found_hold = request(second, "GET", f"/reservations/{hold['reservation_id']}")

    taken = {seat["seat"]: seat["status"] for seat in seat_map["seats"] if seat["status"] != "available"}
    assert taken == {"B1": "booked"}
    assert found_booking["status"] == "confirmed"
    assert found_hold["status"] == "expired"
