# Movie Seats: the Claude Code build

This folder records how Claude Code built Movie Seats from the
[three build prompts](../build-prompts.md), one milestone at a time. Each chapter keeps the
exact prompt, the design proposal and its figures, the implementation report, a terminal
rehearsal of the acceptance scenario and screenshots of the running service.

## About this build

- **Builder.** Claude Code `2.1.312`, as reported by `claude --version`. The session
  environment identified the model as Claude Opus 5.5 (`claude-opus-5-5`).
- **Design skill.** Design Proposal, invoked as `ca-design-proposal` through Claude Code's
  skill tool. The installed skill's marker file reads `ca-design-proposal:v1`, and its
  `SKILL.md` has SHA-256 `53aa66d233dd8cd4b0ecbcbbe846580db2cbfa0eed1d80da915dfefef9c240b2`.
  No other version information was available.
- **Starting point.** The `claude` and `codex` branches share the starter commit
  `81dfa9ff76104dc66b4604c7ea383043f9ee57e5` (tag `starter`). Claude Code implemented
  and tested each milestone in its own build.
- **Authorization.** The developer's task instruction gave standing authorization to proceed
  from each completed proposal to implementation without a separate approval. No separate
  approval message exists, and none is shown in these chapters.

## How to read the chapters

- **Recorded** material is quoted as it was presented in the session: the proposal and the
  implementation report. Each recorded file says so at the top and notes any change, such as
  image paths adjusted for this folder.
- **Editorial** material is everything else: chapter introductions, notes and captions written
  for this folder.
- **Terminal transcripts** are the commands and output of the acceptance rehearsal, copied from
  the run.
- **Proposal figures** are design diagrams drawn for the proposal. Each has an SVG source and a
  rendered PNG.
- **Screenshots** are captures of the running service in headless Chrome. They are not diagrams.

Each chapter links to its implementation commit on GitHub. Use the same commit ID to
inspect or run that checkpoint in a local checkout.

## Chapters

1. [Hold a complete selection of seats](milestone-1/README.md)
2. [Confirm or cancel a hold and recover a lost reply](milestone-2/README.md)
3. [Release abandoned holds](milestone-3/README.md)
