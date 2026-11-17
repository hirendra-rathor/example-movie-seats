# Milestone 2 implementation report

> **Recorded response.** This is the Claude Code implementation report as presented in the
> session after the milestone 2 implementation commit. The title is a level-one heading here;
> the text is otherwise unchanged.

---

I implemented the milestone 2 proposal in commit `bcc365b` on `claude/release`, building on milestone 1's `5bcba37`. The commit holds application code and tests only.

### What changed

| Module | Result |
| --- | --- |
| `movie_seats/database.py` (changed) | Schema changes are numbered `MIGRATIONS`. A new file runs steps 1 and 2; a version 1 file runs only step 2, which adds `reservations.request_key` with a partial unique index, rebuilds `reservation_seats` with a `released` flag and a unique index over unreleased rows, and copies every seat row. All of it, including `user_version = 2`, commits in one transaction. |
| `movie_seats/reservations.py` (changed) | `place_hold(seats, request_key)` returns a `HoldResult` and, inside the write transaction, replays a recorded key (same seats in any order) or raises `HoldKeyReused`. New `find_by_key`, `confirm` and `cancel` apply the transition table; cancel marks the reservation's seats released. Seat status adds `booked`. A shared transaction helper takes the write lock up front and maps a lock timeout to `ReservationBookBusy`. |
| `movie_seats/app.py` (changed) | `POST /holds` reads the optional `Idempotency-Key` header and answers 200 for a replay. New routes: `GET /holds/{key}`, `POST /reservations/{reservation_id}/confirm` and `POST /reservations/{reservation_id}/cancel`, with the 404, 409 and 422 bodies from the proposal. The seat map shows held seats in amber and booked seats in dark blue. |

### Verification

- `uv run --locked python -m pytest -q`: **58 passed** (5.60 s), including all milestone 1 checks.
- The five race checks (overlapping holds, one key from two threads, confirm against cancel, and the HTTP race) passed in 10 repeated runs.
- Live rehearsal with the README command on the **actual milestone 1 database** from the previous rehearsal:
  - Before startup the file reported `user_version` 1 and held reservation `c2bb69ce-…`. After startup it reported 2.
  - `GET /reservations/c2bb69ce-…` returned the milestone 1 hold unchanged. Confirming it twice returned **200** `confirmed` both times.
  - A `POST /holds` for B1, B2 with key `4b9d2e81-…` had its reply discarded; `/seats` showed A3, A4 booked and B1, B2 held.
  - After a restart, `GET /holds/4b9d2e81-…` returned reservation `eef506c4-…`, and retrying `POST /holds` with the key and the seats in reverse order returned **200** with the same reservation. The key with only B1 returned **422**.
  - Cancelling `eef506c4-…` twice returned **200** `cancelled` both times; confirming it then returned **409**, and cancelling the confirmed `c2bb69ce-…` returned **409**. An unused key returned **404**. `/seats` finally showed only A3 and A4 booked.
- Headless Chrome screenshots show the seat map with booked and held seats, the seat map after the cancellation and the API documentation.

### Departures from the proposal

No behavior departs from the proposal. Additions: an [end-to-end] check starts uvicorn on a version 1 file and confirms its hold, and a malformed key in `GET /holds/{key}` returns 422 like the header does. The version 1 fixture in `tests/conftest.py` spells out the milestone 1 schema rather than calling the production migration, so it keeps describing the file that build actually wrote. Held seats on the seat map changed from dark blue to amber so booked seats can take the darker style.

### Limitations

- Keys are global and there is no authentication: anyone who knows a key or a reservation ID can read the reservation, and anyone with the ID can settle it.
- A replay returns the reservation's current state, not a byte-for-byte copy of the first reply.
- The rehearsal discarded a reply after the server sent it; it didn't cut a connection mid-request. Both look the same to the server, which commits before replying.
- `GET /holds/{key}` answers 404 both when a hold failed and when the request never arrived; in both cases nothing is held and a retry is safe.
