# Milestone 3 proposal: release abandoned holds

> **Recorded response.** This is the Claude Code design proposal as presented in the session
> for the third build prompt. Editorial note: in the session each figure appeared as a link,
> "Figure 1: overview" and "Figure 2: collaboration", to `docs/recordings/milestone-3/figures/`,
> with the rendered images attached beside the message. Here the same images are embedded from
> this folder's `figures/` directory with descriptive alternative text, and the title is a
> level-one heading. The proposal text is otherwise unchanged.

---

Booking clients need seats from abandoned holds to return to sale at a deadline the holder is told in advance, even across downtime, and the operator needs upgrades and container replacements to keep every earlier reservation.

![Milestone 3 overview in six perspective columns. The intention to free abandoned seats needs timed holds, constrained by the rule that downtime counts; the intention to upgrade safely needs durable storage provided by a new data volume. A new container runs the changed Movie Seats API, whose changed routes and reservation book expire due holds under the write lock, set deadlines on reservations and release reserved seats; database setup migrates to version 3. New runtime settings set the hold time. New checks cover the version 2 upgrade, restarts and container swaps, HTTP expiry and the expiry boundary. Gray means context, blue means changed and green means new.](figures/proposal-overview.png)

**Comparison baseline.** Milestone 2 commit `bcc365b`. A hold stores `created_at` but no deadline. In `movie_seats/reservations.py`, `seat_statuses()` treats every unreleased seat of a held reservation as taken, and only `cancel()` releases seats, so an abandoned hold keeps its seats forever. `prepare_database()` applies `MIGRATIONS` up to version 2, `create_app()` reads only `MOVIE_SEATS_DATABASE`, and the repository has no container definition.

### Domain

**Intentions.** From your request: *free abandoned seats*, so an unconfirmed hold ends at a time limit the caller is told and its seats return to sale; and *upgrade safely*, so reservations from earlier versions survive the upgrade and a container replacement. The milestone 1 and 2 intentions remain.

**Concepts.** A hold's *deadline*, `expires_at`, is a UTC wall-clock time fixed when the hold is made: its creation time plus the *hold time*. An *expired* reservation is a hold whose deadline arrived before it was confirmed or cancelled.

**Rules.**
- *Downtime counts:* deadlines are wall-clock instants, so time while the service is stopped counts. A hold is expired from its deadline onward, to the second.
- *Expired is final:* expiry releases the seats; confirm and cancel then get 409 with `status: expired`, and a key replay returns the expired reservation. Confirmed bookings never expire.

With a 600 s hold time, hold R made at 12:00:00 has `expires_at` 12:10:00:

| Request at | R reported as | A3, A4 on `/seats` | `confirm R` |
| --- | --- | --- | --- |
| 12:09:59 | held | held | 200; the booking keeps the seats |
| 12:10:00 | expired | available | 409 expired |
| 12:15:05, after downtime 12:02–12:15 | expired | available | 409 expired |

The prompt leaves two values open:

| Question | Recommended | Alternatives |
| --- | --- | --- |
| Hold time | 600 s, set with `MOVIE_SEATS_HOLD_SECONDS` | Any other fixed value |
| Deadline for a hold made by an earlier build (created 11:00, upgraded at 12:00) | Upgrade time plus hold time: held until 12:10, then expired | From `created_at`: expired at once on upgrade. None: held until someone settles it. |

I recommend the grace period: it preserves earlier holds without keeping abandoned ones forever, and gives their clients one full hold time to confirm.

### Architecture

The **Movie Seats API** stays one uvicorn process. Today its holds never end; now it expires due holds itself, without a background timer. Each write transaction first expires due holds under the write lock, reads treat a passed deadline as expired, and startup runs the same sweep before uvicorn accepts requests. The process can stop at any moment without losing a deadline.

A new **container** runs that process from an image built by a new `Dockerfile`, and a named **data volume** mounted at `/data` holds the SQLite file. Replacing the container reattaches the volume, so reservations and deadlines carry over. The container uses the host's clock, so a wrong clock moves every deadline.

![Sequence with a 600-second hold time. Container 1 starts on the data volume, migrates to version 3 and expires due holds. At 12:00:00 the booking client holds A3 and A4 as R and the 201 reply reports expires_at 12:10:00; at 12:01:00 it holds and confirms B1 as S. The operator removes container 1 at 12:02:00, and R's deadline passes during the downtime. At 12:15:00 container 2 starts on the same volume and, before accepting requests, expires R and releases A3 and A4. The client then sees A3 and A4 available and B1 booked; confirming R returns 409 expired and S is still confirmed. Gray means context, blue means changed and green means new.](figures/proposal-collaboration.png)

### Subsystem Design

| Package or module | Components | Today → Proposed |
| --- | --- | --- |
| `movie_seats/reservations.py` (changed) | Reservation book | No deadlines → sets `expires_at` on each hold, expires due holds at the start of every write, derives `expired` on reads, and a new `start()` gives earlier holds a deadline and sweeps. |
| `movie_seats/database.py` (changed) | Database setup | Migrates to version 2 → adds step 3. |
| `movie_seats/app.py` (changed) | `create_app` routes | Reads the database path → also reads the hold time; the lifespan runs `start()` after the migration. |
| `Dockerfile`, `.dockerignore` (new) | Container image | Missing → `python:3.12.13-slim` with uv `0.11.16` installs the locked runtime dependencies; a non-root user runs uvicorn on port 8000 with the database at `/data/movie-seats.sqlite3`. |

### Subsystem Interfaces

| Interface | Change |
| --- | --- |
| Reservation body (changed) | Adds `expires_at`, the deadline of a held or expired reservation and `null` otherwise; status adds `expired`. |
| `POST /holds` (changed) | The 201 reply reports `expires_at`. |
| `confirm` and `cancel` (changed) | 409 `{status: expired}` once the deadline has arrived. |
| Runtime settings (new) | `MOVIE_SEATS_HOLD_SECONDS`, a positive integer; an invalid value stops startup. The container listens on port 8000 and keeps data in the volume at `/data`. |

`GET /seats` keeps its shape; seats of an expired hold read as `available`.

### State Management

| State element | Today → Proposed | Operations |
| --- | --- | --- |
| **Reservation** (changed) | No deadline → nullable `expires_at`; status adds `expired`. | A hold sets the deadline; a sweep marks due holds expired. |
| **Reserved seat** (changed) | Released only by cancel → also by expiry. | The sweep releases them in the same transaction. |
| **Schema version** (changed) | 2 → 3. | Step 3 adds `expires_at` and an index over held deadlines; existing rows keep their values. |
| **Data volume** (new) | Missing → a directory that outlives containers. | Mounted at `/data`. |

Earlier holds reach version 3 without a deadline. At startup, `start()` gives each one a deadline, start time plus hold time, in the same transaction as the sweep, so it happens once. A migration failure rolls back as in milestone 2.

### Verification

| Tests | Layer | Expected assertion |
| --- | --- | --- |
| Expiry boundary (`tests/test_reservations.py`) | [component] | With a controlled clock: held at 599 s; expired with seats available at 600 s; a confirm at 599 s keeps the seats; confirm or cancel at 600 s raises expired; a new hold for the seats succeeds; a confirmed booking never expires. |
| Downtime (`tests/test_reservations.py`) | [component] | A book started after the deadline expires the hold in `start()`. |
| Version 2 upgrade (`tests/test_database.py`) | [component] | A version 2 file keeps every row, and an earlier hold gets start time plus hold time; a version 1 file upgrades through 2 to 3. |
| HTTP expiry (`tests/test_api.py`) | [integration] | The 201 `expires_at` equals `created_at` plus the hold time; a late confirm returns 409 expired; an invalid hold time stops startup. |
| Restart (`tests/test_end_to_end.py`) | [end-to-end] | uvicorn with a 2 s hold time: hold and confirm, stop, wait past the deadline, start again; the first `GET /seats` shows the held seats available and the booking kept. |
| Container swap (`tests/test_container.py`) | [end-to-end], opt-in | Builds the image, holds and confirms through one container, removes it, then starts another on the same volume: the booking remains and the expired hold's seats are free. It runs with `MOVIE_SEATS_CONTAINER_TESTS=1` and is skipped otherwise, because it needs Docker and image downloads. |
| Earlier checks | context | Still pass. |

Run `uv run --locked python -m pytest -q`, then the container check with `MOVIE_SEATS_CONTAINER_TESTS=1`. I'll rehearse in a container on the actual milestone 2 database and add container instructions to the README. Tests control time through an injected clock or short real waits, so they don't exercise host clock adjustments.

### Decisions

1. Hold time of 600 s, configurable (recommended).
2. Earlier holds get upgrade time plus hold time (recommended), their creation time, or no deadline.
3. Expired is final, and confirm and cancel return 409 (recommended).

Under your standing authorization I'm implementing this design with the recommended choices; tell me if you want any of them changed.
