"""Unit checks for exact, complete seat-selection semantics in domain.selection."""

import pytest

from movie_seats.domain import Problem, SEATS, selection


def test_selection_canonicalizes_without_mutating_input():
    seats = ["A4", "A3"]
    assert selection(seats) == ("A3", "A4")
    assert seats == ["A4", "A3"]
    assert selection(list(SEATS)) == SEATS


@pytest.mark.parametrize("seats", [[], ["A3", "A3"], ["A0"], ["a1"], [" A1"], [1], [True], "A1", None, ["A1"] * 13])
def test_invalid_selection_is_rejected(seats):
    with pytest.raises(Problem) as caught:
        selection(seats)
    assert caught.value.status == 422
