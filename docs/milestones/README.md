# Movie Seats · the Codex build

Three prompts develop the shared starter into a service for holding and booking movie seats. Each chapter contains the recorded proposal, the implementation report, screenshots of the running API, and commands for repeating the checks.

The proposals, reports, and diagrams use milestone tags for Git revisions. For milestone 1, `codex-milestone-1` identifies the implementation and `codex-milestone-1-recording` identifies the original responses, figure sources, screenshot provenance, and acceptance data. Each chapter links to both tags.

| Milestone | Reading and evidence |
| --- | --- |
| 1 · Hold a complete selection of seats | [Atomic seat holds and lookup after a restart](01-holds.md) |
| 2 · Confirm or cancel a hold and recover a lost reply | [Request keys, confirmation, and cancellation](02-booking.md) |
| 3 · Release abandoned holds | [Expiration across restarts and container replacement](03-expiration.md) |

Codex used the [recorded version of the Design Proposal skill](../../../../blob/codex-milestone-1-recording/docs/recordings/skill-binding.json) under the developer’s standing authorization.

> I authorize you to proceed from each completed proposal to implementation without
> asking me for a separate approval. Record this as standing authorization from this
> instruction; do not invent a separate user approval message.

The final release check recorded a skill-installation mismatch that blocked Design Graph construction and its independent review.

[Build prompts](../build-prompts.md)
