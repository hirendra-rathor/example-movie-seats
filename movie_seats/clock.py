"""Absolute UTC deadlines, represented without floating-point rounding."""

from datetime import datetime, timedelta, timezone
from time import time_ns

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def utc_now_us() -> int:
    return time_ns() // 1_000


def timestamp(microseconds: int | None) -> str | None:
    if microseconds is None:
        return None
    return (EPOCH + timedelta(microseconds=microseconds)).isoformat(timespec="microseconds").replace("+00:00", "Z")
