# Build Movie Seats in three prompts

Give your coding assistant one request at a time. Each prompt describes what a booking client
should be able to do. Use the assistant’s proposal to review the design decisions and iterate on
them as you see fit.

Use **Design Proposal** (`ca-design-proposal`) to design each milestone with your
coding assistant. To select the skill directly, use `$ca-design-proposal` in Codex
or `/ca-design-proposal` in Claude Code.
[Get the skill](../README.md#work-through-the-example).

## Set up the dev environment

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then clone this repository,
create a branch at its `starter` tag, and run the tests. Use the same branch for all three milestones.

```sh
git clone https://github.com/hirendra-rathor/example-movie-seats.git
cd example-movie-seats
git switch -c build-movie-seats starter
uv run --locked python -m pytest -q
```

uv selects Python 3.12.13 from `.python-version` and installs the dependencies recorded in
`uv.lock` into the local `.venv` directory. The starter serves a placeholder page and a health
endpoint; it does not yet implement reservations. See the [run instructions](../README.md#run-the-example-locally).

Give your assistant one prompt at a time. Review the proposal and its diagrams and ask for any revisions.
When the design fits, reply, “Approved. Implement this milestone and run its checks”.
Try the scenario, run `uv run --locked python -m pytest -q`, and commit the result before the next milestone.

## 1. Hold a complete selection of seats

```text
I’d like to build a small movie booking service called Movie Seats.
Let’s start with one screening configured with twelve seats, A1 through A4,
B1 through B4, and C1 through C4. A booking client should be able to ask
which seats are available and request a hold on one or more of them.
I’d like to use Python and FastAPI for a JSON API I can call from a terminal,
with a local SQLite database for reservations.

People booking together need their complete selection. Two clients might ask
for overlapping seats at the same time, and a caller should get either
every seat it requested or no seats at all. When a hold succeeds, I’d like
the service to return a reservation ID the caller can use to look up the
reservation, even after the service restarts.

Give me a design proposal [use $ca-design-proposal].
```

## 2. Confirm or cancel a hold and recover a lost reply

```text
Movie Seats can now hold seats and return a reservation ID. I’d like a
client to be able to use that ID to confirm the booking or cancel the hold
so someone else can book the seats. This should work for holds made with
the first version too.

A client can lose the reply to a request. I’d like it to be able to retry
safely, even after the service restarts. If the lost reply was for the
original hold, the caller should be able to find out whether its seats were
held and recover the reservation ID. It should also be safe to repeat a
confirmation or cancellation.

Give me a design proposal [use $ca-design-proposal].
```

## 3. Release abandoned holds

```text
Movie Seats now lets clients confirm or cancel a hold. I’d like each new
hold to have a time limit, and I’d like the service to tell the caller when
the hold expires. Once an unconfirmed hold expires, its seats should be
available for booking again. Confirmed bookings should keep their seats.

When we stop the service for maintenance or an upgrade, that downtime
should count toward the hold time. If a deadline passes while the service
is stopped, the seats should be available when it starts accepting requests
again.

Upgrading should preserve reservations made with earlier versions. I’d also
like to run the service in a container and keep those reservations when we
replace the container.

Give me a design proposal [use $ca-design-proposal].
```
