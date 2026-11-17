"""Seat-selection rules and failures owned by the reservation service."""

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
