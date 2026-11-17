# Milestone 1 proposal: hold a complete selection of seats

> **Recorded response.** This is the Claude Code design proposal as presented in the session
> for the first build prompt. Editorial note: in the session each figure appeared as a link,
> "Figure 1: overview" and "Figure 2: collaboration", to `docs/recordings/milestone-1/figures/`,
> with the rendered images attached beside the message. Here the same images are embedded from
> this folder's `figures/` directory with descriptive alternative text, and the title is a
> level-one heading. The proposal text is otherwise unchanged.

---

A booking client needs to hold a group's complete seat selection at the Movie Seats screening, every requested seat or none, and to find that hold again by its reservation ID even after the service restarts.

![Milestone 1 overview in six perspective columns. The booking client calls the changed Movie Seats API, which runs the changed create_app routes; they delegate to a new reservation book that claims all seats in one transaction, backed by new reservation, reserved-seat and schema-version state in a new SQLite database. New tests cover the race for A4, the HTTP contract and a restart lookup. Gray means context, blue means changed and green means new.](figures/proposal-overview.png)

**Comparison baseline.** I compared against the starter commit `81dfa9f` on `claude/release`. In `movie_seats/app.py`, `create_app()` serves a placeholder page at `/` and `GET /health`. There are no seats, reservations or database yet. `pyproject.toml` already pins FastAPI and uvicorn, and `.gitignore` already excludes `instance/`. Apart from the health route and the app factory, everything below is new.

### Domain

**Intentions.** Both come from your request. People booking together get their *complete selection*, never part of a group. A caller can *recover its hold* by reservation ID after a restart.

**Concepts.** The *screening* has a fixed *seat layout* of twelve seats: A1–A4, B1–B4 and C1–C4. A *hold* claims seats for a *reservation*, identified by its *reservation ID*. A seat is *available* when no reservation holds it.

**Rules.**
- *All or nothing:* a hold claims every requested seat or none, and reports which requested seats were unavailable.
- *One holder per seat:* no seat belongs to two reservations. When two requests overlap, the one that obtains the database write lock first is decided first; the other is then judged against the committed result. Arrival order at the HTTP layer doesn't decide it, and the second caller waits at most 5 s.
- *Valid selection:* one or more distinct seats from the layout. An invalid selection holds nothing.

The prompt leaves near-miss input open:

| Input | Exact labels (recommended) | Lenient labels |
| --- | --- | --- |
| `["a3"]` | 422, unknown seat `a3` | 201, holds A3 |
| `["A3", "A3"]` | 422, duplicate seat `A3` | 201, holds A3 once |

I recommend exact labels: a terminal caller sees its mistake instead of holding something it didn't spell, and the contract stays easy to state. Nothing in this milestone releases a seat; confirmation, cancellation and expiry belong to the later prompts.

### Architecture

The **booking client**, a terminal using `curl`, calls the **Movie Seats API**, one uvicorn process running the FastAPI app. Today that process keeps no state. Proposed: it owns the reservation rules and keeps reservations in a **SQLite database** file, `instance/movie-seats.sqlite3` by default or the path in `MOVIE_SEATS_DATABASE`. FastAPI runs synchronous handlers on a worker thread pool, so two holds can genuinely overlap. Each operation opens its own SQLite connection, and the database's write lock serializes the decision, which also holds if several processes later share the file.

![Sequence for two overlapping holds. Client 1 asks for A3 and A4 and client 2 for A4 and B1. Inside the Movie Seats API process the create_app routes call the reservation book; call 1 takes the SQLite write lock with BEGIN IMMEDIATE, finds A3 and A4 free, inserts and commits, and client 1 receives 201 with the reservation ID. Call 2 waits for the lock, then finds A4 held, rolls back, and client 2 receives 409 naming A4 while B1 stays available. After a restart a new process reads the same reservation from the SQLite file and returns 200. Gray means context, blue means changed and green means new.](figures/proposal-collaboration.png)

### Subsystem Design

Package `movie_seats`:

| Package or module | Components | Today → Proposed |
| --- | --- | --- |
| `app.py` (changed) | `create_app` and routes | Placeholder page and `/health` → also prepares the database at startup, maps reservation-book results to HTTP responses and renders a read-only seat map at `/`. |
| `screening.py` (new) | Seat layout | Missing → the screening ID and the twelve seat labels in row order. |
| `reservations.py` (new) | Reservation book | Missing → lists availability, places all-or-nothing holds and looks up reservations. |
| `database.py` (new) | Database setup | Missing → opens connections (5 s busy timeout, foreign keys, WAL journal) and creates schema version 1. |

`place_hold` validates the selection against the layout, runs `BEGIN IMMEDIATE`, and selects any requested seats that are already reserved. It then either inserts the reservation and its seats and commits, or rolls back and raises `SeatsUnavailable`. A unique constraint on the reserved seat backs this up; if it ever fires, the caller sees the same 409.

### Subsystem Interfaces

All three JSON endpoints are new; `GET /health` is unchanged.

| Interface | Request | Responses |
| --- | --- | --- |
| `GET /seats` | none | 200 `{screening_id, seats: [{seat, status}]}`, with status `available` or `held`, in layout order. |
| `POST /holds` | `{"seats": ["A3", "A4"]}` | 201 with the reservation body and `Location: /reservations/{id}`; 409 `{detail, unavailable_seats}`; 422 `{detail, invalid_seats}`; 503 if the lock wait times out. |
| `GET /reservations/{id}` | none | 200 `{reservation_id, screening_id, status: "held", seats, created_at}`; 404 for an unknown ID. |

Reservation IDs are random UUIDs, so they reveal nothing about order or volume. The entry page `/` replaces its placeholder sentence with the seat map and keeps its `/docs` link. If a 201 reply is lost, a retry in this milestone is a new request and gets 409 for its own seats; recovering lost replies is the second prompt's job.

### State Management

| State element | Meaning and representation | Operations |
| --- | --- | --- |
| **Reservation** (new) | `reservations(reservation_id PK, screening_id, status, created_at)`; status is `held`. | Inserted by `POST /holds`; read by lookups. |
| **Reserved seat** (new) | `reservation_seats(reservation_id FK, screening_id, seat_id)`, unique on `(screening_id, seat_id)`. | Inserted in the same transaction as its reservation; read to derive availability. |
| **Schema version** (new) | `PRAGMA user_version = 1`. | Set when the file is created. A newer version stops startup, so later upgrades stay explicit. |

Availability is derived from the layout minus reserved seats and is never stored separately. Because a reservation and its seats commit together, a crash mid-request leaves either the whole hold or nothing. The file survives restarts; deleting it deletes every reservation.

### Verification

| Tests | Layer | Expected assertion |
| --- | --- | --- |
| Race for A4 (`tests/test_reservations.py`) | [component] | While the test holds the write lock, two threads call `place_hold(A3, A4)` and `place_hold(A4, B1)`. After release exactly one succeeds, the other raises naming A4, and only the winner's seats are reserved. If the check ran before taking the lock, both calls would see A4 free and the loser would fail on the constraint or, outside one transaction, leave B1 held. |
| Selection rules (`tests/test_reservations.py`) | [component] | `D1`, `a3`, duplicates and an empty list are rejected; after a 409, B1 is still available. |
| HTTP contract (`tests/test_api.py`) | [integration] | `GET /seats` lists twelve available seats; `POST /holds` for A3, A4 returns 201 with `Location`; the overlapping hold returns 409 naming A4; lookup returns 200; an unknown ID returns 404; a new `create_app` on the same file returns the same reservation. |
| Restart lookup (`tests/test_end_to_end.py`) | [end-to-end] | A real uvicorn process receives concurrent overlapping holds and answers one 201 and one 409. After the process restarts, `GET /reservations/{id}` returns A3 and A4 held. |
| Health and page (`tests/test_health.py`) | [integration], context | The health body is unchanged; the page keeps its heading and `/docs` link. |

Run `uv run --locked python -m pytest -q`. I'll also rehearse the scenario by hand with `curl` against uvicorn and capture the seat map. The race check controls when both calls start waiting, not SQLite's internal scheduling, so it demonstrates the outcome under contention; the unique constraint covers schedules it doesn't produce.

### Decisions

1. Exact seat labels (recommended) or lenient normalization.
2. A 409 names the unavailable seats (recommended). It reveals that someone holds them, not who.
3. The database lives at `instance/movie-seats.sqlite3`, overridable with `MOVIE_SEATS_DATABASE`.

You gave standing authorization to proceed from each completed proposal to implementation, so I'm implementing this design with the recommended choices. Tell me if you'd like any of them changed.
