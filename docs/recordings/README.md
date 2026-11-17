# The fresh Movie Seats build

These recordings document the new build on `codex/release`, beginning at the approved `starter` checkpoint. Implementation and recording are separate commits. Commit links resolve on GitHub only after the user publishes this run; the same identifiers work locally now.

| Milestone | Recording | Implementation |
| --- | --- | --- |
| 1. Hold a complete selection | [Prompt, proposal, authorization and result](01-holds/README.md) | `edaddef6b4f46260ad0694930af343e4f2dafe11` |
| 2. Confirm, cancel and recover replies | [Prompt, proposal, authorization and result](02-booking/README.md) | `9af1797ea2e4851319dd4ecc26d104b455d3a570` |

## What is recorded

The milestone prompts are copied verbatim from the build guide. Each proposal and implementation response is captured when presented in chat. The `.txt` response sources preserve the exact user-visible text, including the local image URLs used by the chat renderer. Their Markdown counterparts change only those image URLs to portable relative paths. Index pages and these recording notes are editorial navigation, not transcript.

The user granted standing authorization to proceed from each completed proposal to implementation. The preliminary draft was discarded at the user's request before implementation; only the restarted proposals are included. No separate approval message is invented.

Every proposal uses the installed Design Proposal skill, identified by [the installed-file hashes](skill-binding.json), against the current release source. No historical implementation, historical response, or assurance construction record is part of these release checkpoints. No working Design Graph was needed.

Overview and collaboration images are explanatory proposal diagrams. Other images are browser screenshots of working application responses. Each milestone includes structured acceptance observations, screenshot provenance, editable SVG figures and their data. Render a proposal's SVG files with `python docs/recordings/render_diagrams.py docs/recordings/01-holds`; PNG files are exported display copies. The [capture utility](capture_browser.cjs) uses Playwright and Chromium and captures the service without altering its page content.

The recorded application checks use Python 3.12.13 and the repository's locked uv environment. A temporary writable uv cache was used in this sandbox. Test databases and scenario databases are isolated from working application data. Hidden reasoning and internal tool logs are excluded.
