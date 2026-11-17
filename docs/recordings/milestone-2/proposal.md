# Milestone 2 proposal: confirm or cancel a hold and recover a lost reply

> **Recorded response.** This is the Claude Code design proposal as presented in the session
> for the second build prompt. Editorial note: in the session each figure appeared as a link,
> "Figure 1: overview" and "Figure 2: collaboration", to `docs/recordings/milestone-2/figures/`,
> with the rendered images attached beside the message. Here the same images are embedded from
> this folder's `figures/` directory with descriptive alternative text, and the title is a
> level-one heading. The proposal text is otherwise unchanged.

---

A booking client needs to settle each hold, by confirming the booking or cancelling so others can book the seats, and to retry any request whose reply was lost, even across a restart, without holding seats twice or losing its reservation ID.

![Milestone 2 overview in six perspective columns. Rules for one-way status and one key per hold protect the intentions to settle a hold and to retry safely, which need the capability to settle and recover. The changed Movie Seats API runs changed routes and a changed reservation book that records status and key on the reservation; cancel releases reserved seats; database setup migrates the schema from version 1 to 2. The new Idempotency-Key header is sent with POST /holds. New checks cover key replay, a lost reply across a restart, status transitions and the version 1 upgrade. Blue means changed and green means new.](figures/proposal-overview.png)

**Comparison baseline.** Milestone 1 commit `5bcba37`. `ReservationBook.place_hold()` in `movie_seats/reservations.py` always inserts a new reservation under a fresh UUID, so a retried `POST /holds` after a lost 201 gets 409 for its own seats and the caller can't learn its reservation ID. Reservations stay `held`: no operation changes status, and the `UNIQUE (screening_id, seat_id)` constraint on `reservation_seats` would stop a released seat from being reserved again. `prepare_database()` in `movie_seats/database.py` creates schema version 1 and refuses anything newer; there is no upgrade path.

### Domain

**Intentions.** From your request: a client *settles the hold*, confirming the booking or cancelling so someone else can book the seats, including holds made by the first version; and a client can *retry safely* after a lost reply, even across a restart. Milestone 1's intentions, booking together and finding a hold by ID, remain.

**Concepts.** A reservation's *status* is `held`, `confirmed` (a *booking*) or `cancelled`. A *hold key* is a value the client generates for one hold request and repeats on every retry of it. I propose the conventional `Idempotency-Key` header to carry it.

**Rules.**
- *One-way status:* `held` becomes `confirmed` or `cancelled`, and neither changes again. Repeating the request that produced the current status succeeds without a change; the other request is refused.
- *Cancelling releases seats:* a cancelled reservation's seats are available at once; a confirmed booking keeps them.
- *One key, one hold:* the first successful hold under a key is the only one. A retry with the same key and seats returns that reservation; the same key with different seats is refused.

| Current status | `confirm` | `cancel` |
| --- | --- | --- |
| held | 200, now confirmed | 200, now cancelled; seats released |
| confirmed | 200, unchanged | 409 |
| cancelled | 409 | 200, unchanged |

Two choices are open; each input below separates them:

| Input | Recommended | Alternative |
| --- | --- | --- |
| `POST /holds` without a key, as milestone 1 clients send it | 201 as today; the hold works but can't be recovered by key | 400 until clients add a key, breaking existing callers |
| Key K first got 409 for A4; A4 is later cancelled; the client retries with K | 201: only successful holds are recorded, so the retry is a fresh attempt | 409 again: K replays its first failure forever |

I recommend an optional key, so milestone 1 callers keep working, and recording only successful holds, because nothing was held before and the client still wants the seats. Cancelling a confirmed booking is outside the prompt and gets 409.

### Architecture

The **booking client** changes: today it sends seats only; now it generates a key per hold, such as a UUID, and keeps it until it has the reservation ID. The **Movie Seats API** stays one uvicorn process and gains confirm, cancel and key lookup. The **SQLite database** is upgraded in place from schema version 1 to 2 when the new build starts, before it accepts requests. Every write still runs under SQLite's write lock with `BEGIN IMMEDIATE`, so a confirm and a cancel racing for one hold apply in lock order, and two retries with one key can't both insert.

![Sequence for a lost hold reply. The booking client sends POST /holds for A3 and A4 with Idempotency-Key K; the reservation book checks K and the seats in one write transaction and commits reservation R with K, but the 201 reply is lost. After a restart, GET /holds/K returns R, and a retried POST /holds with K returns 200 with the same R without inserting. The client confirms R, that reply is lost too, and the repeated confirmation finds R confirmed and returns 200 without a change. Blue means changed.](figures/proposal-collaboration.png)

### Subsystem Design

Package `movie_seats`:

| Package or module | Components | Today → Proposed |
| --- | --- | --- |
| `reservations.py` (changed) | Reservation book | `place_hold(seats)` and lookups → `place_hold(seats, key)` replays a recorded key inside the write transaction; new `find_by_key`, `confirm` and `cancel` apply the transition table; seat status adds `booked`. |
| `database.py` (changed) | Database setup | Creates version 1 → applies numbered migrations in one transaction: a new file goes through versions 1 and 2, a version 1 file gets only the step to 2. |
| `app.py` (changed) | `create_app` routes | Three JSON routes → three more, the key header on `POST /holds`, and booked seats on the seat map. |

### Subsystem Interfaces

| Interface | Change |
| --- | --- |
| `POST /holds` (changed) | Optional `Idempotency-Key` header: 1–128 URL-safe characters (letters, digits, `-_.~`), such as a UUID. New hold: 201 as today. Recorded key, same seats in any order: 200 with the reservation's current state and the same ID. Same key, different seats: 422. |
| `GET /holds/{key}` (new) | 200 with the reservation held under that key; 404 if none was recorded, meaning nothing is held under it and a retry is safe. |
| `POST /reservations/{id}/confirm` and `/cancel` (new) | 200 with the reservation; 404 for an unknown ID; 409 `{detail, status}` for a refused transition. |
| `GET /seats`, `GET /reservations/{id}` (changed) | Seat status adds `booked`; reservation status adds `confirmed` and `cancelled`. |

A replay returns current state rather than a stored copy of the first reply. A key works like the reservation ID: anyone who knows it can read the reservation, so clients should use unguessable keys.

### State Management

| State element | Today → Proposed | Operations |
| --- | --- | --- |
| **Reservation** (changed) | Status always `held` → `held`, `confirmed` or `cancelled`; new nullable `request_key`, unique where present. | A hold inserts it with its key; confirm and cancel update status; lookups by ID or key read it. |
| **Reserved seat** (changed) | Unique per screening seat forever → new `released` flag; a partial unique index covers only unreleased rows. | Cancel marks the reservation's rows released; holds check unreleased rows. |
| **Schema version** (changed) | 1 → 2. | The migration rebuilds `reservation_seats`, copies every row as unreleased, adds `request_key` and sets version 2, all in one transaction. |

A version 1 file keeps every reservation, ID, timestamp and seat; its holds have no key and become confirmable and cancellable. If the migration fails, the transaction rolls back and the file stays at version 1. A version 1 build refuses the upgraded file instead of misreading it.

### Verification

| Tests | Layer | Expected assertion |
| --- | --- | --- |
| Status transitions (`tests/test_reservations.py`) | [component] | Every cell of the transition table, including repeats. After A3, A4 is cancelled, a hold for A4, B1 succeeds; a confirmed booking's seats stay `booked`. |
| Key replay (`tests/test_reservations.py`, `tests/test_api.py`) | [component], [integration] | The same key twice, including from two threads at once, yields one reservation and the same ID, and the second reply is 200. Different seats under the key give 422; a failed attempt leaves no record. |
| Version 1 upgrade (`tests/test_database.py`) | [component] | A file built with the version 1 schema and a held reservation becomes version 2 with the row intact, and that hold confirms or cancels. A failure mid-migration leaves version 1. |
| HTTP contract (`tests/test_api.py`) | [integration] | Confirm, cancel, 404 and 409 bodies; `GET /holds/{key}` 200 and 404; a replay through a new `create_app` on the same file. |
| Lost reply (`tests/test_end_to_end.py`) | [end-to-end] | Against uvicorn: hold with a key and discard the reply; restart; `GET /holds/{key}` returns the ID; a retried `POST /holds` returns 200 with the same ID; confirming twice returns 200 both times; `/seats` shows `booked`. |
| Milestone 1 checks | [component], [integration], [end-to-end], context | Still pass. |

Run `uv run --locked python -m pytest -q`. For the rehearsal I'll start this build on the actual milestone 1 database from the last rehearsal, which holds A3 and A4 under reservation `c2bb69ce-…`, and confirm that hold. A discarded reply stands in for a lost one: the server commits before it replies, so it can't tell the difference.

### Decisions

1. Keep the key optional (recommended) or require it.
2. Record only successful holds under a key (recommended) or replay failures too.
3. Refuse to cancel a confirmed booking with 409 (recommended).

Under your standing authorization I'm implementing this design with the recommended choices; tell me if you want any of them changed.
