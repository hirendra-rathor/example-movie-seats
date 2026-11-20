# Movie Seats — the Codex build

Codex built Movie Seats from the [three prompts](../build-prompts.md), beginning at the shared `starter` commit. Each chapter links to the implementation commit and the recorded checks. To follow the same chapters offline, open the [HTML walkthrough](../walkthrough/index.html) in a browser from your checkout.

| Milestone | Recording | Implementation |
| --- | --- | --- |
| 1. Hold a complete selection | [Prompt, proposal, authorization and result](01-holds/README.md) | `edaddef6b4f46260ad0694930af343e4f2dafe11` |
| 2. Confirm, cancel and recover replies | [Prompt, proposal, authorization and result](02-booking/README.md) | `9af1797ea2e4851319dd4ecc26d104b455d3a570` |
| 3. Release abandoned holds | [Prompt, proposal, authorization and result](03-expiration/README.md) | `0e994e4e7c1220ea5568f68b32fe685abf4adb78` |

## What is recorded

The milestone prompts are copied verbatim from the build guide. Each proposal and implementation response is captured when presented in chat. The `.txt` response sources preserve the exact user-visible text, including the local image URLs used by the chat renderer. Their Markdown counterparts change only those image URLs to portable relative paths. Index pages and these recording notes are editorial navigation, not transcript.

The user granted standing authorization to proceed from each completed proposal to implementation. The preliminary draft was discarded at the user's request before implementation; only the restarted proposals are included. No separate approval message is invented.

Each proposal used the installed Design Proposal skill against that milestone’s source. The [skill record](skill-binding.json) identifies the version by file hash. The [release verification](../walkthrough/validation.json) records the tooling check that blocked Design Graph construction and independent review after milestone three.

Overview and collaboration images are explanatory proposal diagrams. Other images are browser screenshots of working application responses. Each milestone includes structured acceptance observations, screenshot provenance, editable SVG figures and their data. Render a proposal's SVG files with `python docs/recordings/render_diagrams.py docs/recordings/01-holds`; PNG files are exported display copies. The [capture utility](capture_browser.cjs) uses Playwright and Chromium and captures the service without altering its page content.

The recorded application checks use Python 3.12.13 and the repository's locked uv environment. A temporary writable uv cache was used in this sandbox. Test databases and scenario databases are isolated from working application data. Hidden reasoning and internal tool logs are excluded.
