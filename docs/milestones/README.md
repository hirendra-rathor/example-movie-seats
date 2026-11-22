# Movie Seats · the Codex build

Three prompts develop the shared starter into a service for holding and booking movie seats. Each chapter contains the recorded proposal, the implementation report, screenshots of the running API, and commands for repeating the checks.

The test counts in the chapters come from the original build sessions. Each milestone has an implementation commit followed by a recording commit with the original responses, figures, screenshots, and acceptance data. [Codex branch history](../../../../commits/codex/)

| Milestone | Reading and evidence |
| --- | --- |
| 1 · Hold a complete selection of seats | [Atomic seat holds and lookup after a restart](01-holds.md) |
| 2 · Confirm or cancel a hold and recover a lost reply | [Request keys, confirmation, and cancellation](02-booking.md) |
| 3 · Release abandoned holds | [Expiration across restarts and container replacement](03-expiration.md) |

Codex used the installed `ca-design-proposal` skill under the developer’s standing authorization. The first milestone’s recording commit lists the skill files in `docs/recordings/skill-binding.json`. The recorded SHA-256 digest for `SKILL.md` is `53aa66d233dd8cd4b0ecbcbbe846580db2cbfa0eed1d80da915dfefef9c240b2`.

> I authorize you to proceed from each completed proposal to implementation without
> asking me for a separate approval. Record this as standing authorization from this
> instruction; do not invent a separate user approval message.

The final release check recorded a skill-installation mismatch that blocked Design Graph construction and its independent review.

[Build prompts](../build-prompts.md)
