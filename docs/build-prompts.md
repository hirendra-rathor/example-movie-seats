# Movie Seats prompts used by Claude Code

The prompts below use Claude Code’s `/ca-design-proposal` command. Only the skill prefix differs from the [prompts in the original build guide](../../../blob/starter/docs/build-prompts.md).

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

Give me a design proposal [use /ca-design-proposal].
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

Give me a design proposal [use /ca-design-proposal].
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

Give me a design proposal [use /ca-design-proposal].
```
