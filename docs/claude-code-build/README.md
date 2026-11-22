# Movie Seats: Claude Code build

This folder records the independent Claude Code implementation of the three milestones in the [build guide](../build-prompts.md). The Movie Seats walkthrough uses this build. Each chapter contains the prompt, the proposal and its diagrams, the authorization to implement, the implementation report, terminal checks, and screenshots of the working service.

## Milestones

| Milestone | Recording |
| --- | --- |
| 1. Hold a complete selection of seats | [Milestone 1 chapter](milestone-1-hold-a-complete-selection-of-seats.md) |
| 2. Confirm or cancel a hold and recover a lost reply | [Milestone 2 chapter](milestone-2-confirm-or-cancel-a-hold-and-recover-a-lost-reply.md) |
| 3. Release abandoned holds | [Milestone 3 chapter](milestone-3-release-abandoned-holds.md) |

## Starting point

The `claude` and `codex` branches share the `starter` commit, `81dfa9f`. Claude Code built Movie Seats from the starter and the three prompts. Each milestone has an implementation commit followed by a recording commit. Each chapter links to the implementation it describes.

## How these recordings were made

- **Recorded responses.** Quoted passages reproduce the proposal and implementation report presented during the build. The proposal images use paths in this edition. The branch was named `claude/release` during the session.
- **Prompts and authorization.** The prompt blocks use Claude Code’s `/ca-design-proposal` command. The developer gave standing authorization to implement each completed proposal.
- **Terminal checks and images.** Each chapter preserves the commands and output from its acceptance rehearsal. The proposal diagrams are available as SVG and PNG. The screenshots show the running service at the point described in their captions.

## Build environment

| Item | Value | Evidence |
| --- | --- | --- |
| Coding assistant | Claude Code 2.1.312 | `claude --version` during the build |
| Model | Claude Opus 5.5 (`claude-opus-5-5`) | Recorded session environment |
| Design Proposal skill | `ca-design-proposal:v1` · `SKILL.md` SHA-256 `53aa66d233dd8cd4b0ecbcbbe846580db2cbfa0eed1d80da915dfefef9c240b2` | Installed marker and skill file |
| Python, FastAPI, pytest | 3.12.13, 0.162.4, 9.2.0 | [Python version](../../.python-version) and [dependency lock](../../uv.lock) |
| Screenshots | Headless Chrome | Recorded acceptance rehearsals |
