# Milestone 1 implementation report

> **Recorded response.** This is the Claude Code implementation report as presented in the
> session after the milestone 1 implementation commit. The title is a level-one heading here;
> the text is otherwise unchanged.

---

I implemented the milestone 1 proposal in commit `5bcba37` on `claude/release`. The commit holds application code and tests only; the recording files stay out of it.

### What changed

| Module | Result |
| --- | --- |
| `movie_seats/screening.py` (new) | Seat layout `screening-1` with A1–A4, B1–B4 and C1–C4 in row order. |
| `movie_seats/database.py` (new) | `connect()` opens a connection that manages its own transactions and waits up to 5 s for the write lock. `prepare_database()` switches the file to WAL, creates schema version 1 and refuses a newer version with `SchemaVersionError`. The path comes from `MOVIE_SEATS_DATABASE`, defaulting to `instance/movie-seats.sqlite3`. |
| `movie_seats/reservations.py` (new) | `ReservationBook` with `seat_statuses()`, `place_hold()` and `get_reservation()`. `place_hold()` validates the selection, runs `BEGIN IMMEDIATE`, checks the requested seats, then inserts and commits or rolls back and raises `SeatsUnavailable`. A unique-constraint violation maps to the same conflict, and a lock timeout raises `ReservationBookBusy`. |
| `movie_seats/app.py` (changed) | The lifespan prepares the database. New routes: `GET /seats`, `POST /holds` (201 with `Location`) and `GET /reservations/{reservation_id}`, with the 409, 422, 404 and 503 bodies from the proposal. The entry page now renders the seat map and keeps its `/docs` link. `/health` is unchanged. |

### Verification

- `uv run --locked python -m pytest -q`: **26 passed** (2.45 s).
- The two race checks passed in 15 repeated runs.
- Live rehearsal with the README command, `uv run --locked uvicorn movie_seats.app:create_app --factory --host 127.0.0.1 --port 8000`, on the default database:
  - `GET /seats` listed twelve available seats.
  - Two `curl` processes sent `POST /holds` for A3, A4 and for A4, B1 at the same time. A3, A4 received **201** with reservation `c2bb69ce-b48d-4e7c-afd8-19266549b01a`; A4, B1 received **409** with `unavailable_seats: ["A4"]`.
  - `GET /seats` then showed only A3 and A4 held; B1 stayed available.
  - `["a3"]` and `["B1", "B1"]` returned **422** naming the seat; an unknown ID returned **404**.
  - After I stopped and restarted uvicorn, `GET /reservations/c2bb69ce-…` returned **200** with the identical body, and A3 and A4 were still held.
- Headless Chrome screenshots show the seat map after the hold, the seat map after the restart and the API documentation page.

### Departures from the proposal

No behavior departs from the proposal. I added checks beyond the proposed table: `tests/test_database.py` [component] covers schema creation, re-preparing a file without losing reservations, and refusing a newer schema; one [component] and one [integration] check cover the 503 lock timeout. The seat map's held markers are checked in `tests/test_api.py`; `tests/test_health.py` is unchanged and still passes.

### Limitations

- The race checks control when both holds start waiting, not SQLite's internal scheduling. Timing decided the live winner; the unique constraint covers schedules the checks don't produce.
- Several uvicorn workers or processes sharing one file rely on the same SQLite lock but weren't exercised.
- A lost 201 reply can't be recovered yet; that is the second prompt.
