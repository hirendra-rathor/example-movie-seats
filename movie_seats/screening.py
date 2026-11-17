"""The seat layout for the one screening Movie Seats sells."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Screening:
    """A screening and its seats, listed in the order a seat map shows them."""

    screening_id: str
    rows: tuple[tuple[str, ...], ...]

    @property
    def seats(self) -> tuple[str, ...]:
        return tuple(seat for row in self.rows for seat in row)

    def has_seat(self, seat: str) -> bool:
        return seat in self.seats


SCREENING = Screening(
    screening_id="screening-1",
    rows=(
        ("A1", "A2", "A3", "A4"),
        ("B1", "B2", "B3", "B4"),
        ("C1", "C2", "C3", "C4"),
    ),
)
