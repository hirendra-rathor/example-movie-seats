# Milestone 3 implementation report

> **Recorded response.** This is the Claude Code implementation report as presented in the
> session after the milestone 3 implementation commit. The title is a level-one heading here;
> the text is otherwise unchanged.

---

I implemented the milestone 3 proposal in commit `5bed9eb` on `claude/release`, building on milestone 2's `bcc365b`. The commit holds the application code, tests, `Dockerfile`, `.dockerignore` and the README's new run instructions.

### What changed

| Module | Result |
| --- | --- |
| `movie_seats/database.py` (changed) | Migration step 3 adds `reservations.expires_at` and an index over held deadlines. |
| `movie_seats/reservations.py` (changed) | Each hold stores `expires_at`, its creation second plus the hold time. Every write first expires due holds and releases their seats under the write lock; reads report a passed deadline as `expired`. `start()` gives earlier holds one hold time from the first start and sweeps. `expired` is final: confirm and cancel raise `TransitionRefused`, and a key replay returns the expired hold. |
| `movie_seats/app.py` (changed) | Reads `MOVIE_SEATS_HOLD_SECONDS` (default 600; a non-positive or non-integer value stops startup). The lifespan runs the migration, then `start()`, before uvicorn accepts requests. Reservation bodies include `expires_at`, which is `null` once a reservation is confirmed or cancelled. The seat map states the hold time. |
| `Dockerfile`, `.dockerignore` (new) | `python:3.12.13-slim` with uv `0.11.16` installs the locked runtime dependencies. A non-root user runs uvicorn on port 8000 with the database at `/data/movie-seats.sqlite3`, and a health check calls `/health`. |
| `README.md` (changed) | Documents the database and hold-time variables, the container commands and the opt-in container check. The introduction, skill descriptions, links and diagram are unchanged. |

### Verification

- `uv run --locked python -m pytest -q`: **79 passed, 1 skipped** (9.98 s); the skipped test is the opt-in container check.
- `MOVIE_SEATS_CONTAINER_TESTS=1 uv run --locked python -m pytest -q`: **80 passed** (16.97 s), including an image build and a container replacement.
- The four race checks passed in 8 repeated runs after the final change.
- **Container rehearsal** with a 60 s hold time:
  - I ran the milestone 2 build (`bcc365b`) from a temporary worktree on a copy of the milestone 2 rehearsal database and held C1, C2 under key `milestone-2-hold`.
  - I seeded a new volume with that file and started container 1. The file reported `user_version` 3. The milestone 1 reservation `c2bb69ce-…` was still `confirmed`. The milestone 2 hold received `expires_at` 19:49:54, 60 s after startup, and a new hold for A1, A2 returned **201** with the same deadline.
  - I removed container 1 at 19:49:03 and started container 2 on the same volume at 19:50:06, after both deadlines had passed.
  - The first `GET /seats` showed only A3 and A4 booked. Both holds read `expired`, confirming the new one returned **409** `expired`, and C1, C2 could be held again (**201**). The stored rows showed `expired`, so the startup sweep had written them, not only derived them.
- Headless Chrome screenshots show container 1's seat map, container 2's seat map and an expired reservation.

### Departures from the proposal

No behavior departs from the proposal. One implementation detail emerged from a failing check: a refused confirm or cancel at first rolled back the expiry sweep along with the refusal. Refusals are now raised after the sweep commits, so stored status matches what callers see. The rehearsal used `claude-`-prefixed Docker names and host port 8010 rather than the README's `movie-seats` names and port 8000, because another build was working on the same machine, and a 60 s hold time to keep the wait short. I removed the rehearsal container, volume and image afterward.

### Limitations

- Deadlines trust the host clock; tests control time with an injected clock or short real waits and don't exercise clock adjustments.
- Deadlines are kept to the second. Creation time is truncated, so the effective hold is between one second short of the hold time and the full hold time.
- No background timer runs. Stored status changes at the next write or start, while reads already report `expired`.
- The container check is opt-in because it needs Docker and pulls base images; the default suite skips it.
- Base images are pinned by tag, not digest. Several containers writing one volume at the same time weren't exercised.
