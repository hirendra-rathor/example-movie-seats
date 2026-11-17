"""Seat-selection rules and failures owned by the reservation service."""

from dataclasses import dataclass
import re

SEATS = tuple(f"{row}{number}" for row in "ABC" for number in range(1, 5))


class Problem(Exception):
    """A caller-visible rejection with a stable code and HTTP status."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code


def selection(seats: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Canonicalize a valid set without silently correcting caller mistakes."""
    if not isinstance(seats, (list, tuple)) or not 1 <= len(seats) <= len(SEATS):
        raise Problem(422, "invalid_selection", "Choose between one and twelve seats.")
    if any(type(seat) is not str or seat not in SEATS for seat in seats):
        raise Problem(422, "invalid_selection", "Use exact seat identifiers from the screening.")
    if len(set(seats)) != len(seats):
        raise Problem(422, "invalid_selection", "A selection cannot contain duplicate seats.")
    return tuple(sorted(seats))


def request_identity(key: str | None) -> str | None:
    if key is not None and (type(key) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", key) is None):
        raise Problem(422, "invalid_request_key", "Use a request key of 1–128 ASCII letters, digits, dots, underscores, colons or hyphens.")
    return key


def transition(current: str, target: str) -> str:
    """Terminal operations can repeat, but cannot reverse one another."""
    if target not in {"confirmed", "cancelled"}:
        raise ValueError("Unknown completion target.")
    if current == "expired":
        raise Problem(409, "reservation_expired", "The hold expired and cannot be completed.")
    if current == "held" or current == target:
        return target
    if current in {"confirmed", "cancelled"}:
        raise Problem(409, "reservation_final", "The reservation already completed with a different outcome.")
    raise RuntimeError(f"Unrecognized reservation state: {current}")


@dataclass(frozen=True)
class Creation:
    reservation: dict
    created: bool
