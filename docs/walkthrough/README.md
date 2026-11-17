# Maintain the offline walkthrough

Open [index.html](index.html) directly in a browser. No server, network connection, or running Movie Seats application is required. The reader includes all three recorded prompts, proposals, standing authorization notes, implementation reports, original diagrams and working-application screenshots.

The chapter and stage navigation is editorial. Proposal and implementation prose is rendered from the [recordings](../recordings/README.md). Exact response-source files are linked from each stage. Figure inspection supports fit-to-width and full-resolution scrolling; screenshots and explanatory diagrams are labeled separately.

## Rebuild

From the repository root, run:

```sh
uv run --locked python docs/walkthrough/render.py
uv run --locked python docs/walkthrough/validate.py
```

The renderer uses only Python's standard library. [template.html](template.html), [reader.css](reader.css), and [reader.js](reader.js) maintain the page structure, appearance, navigation and image viewer. The generated HTML embeds the recorded prose and observations, references repository-local images, and performs no fetch requests. The Markdown renderer supports the constructs used in these recordings; add support before introducing a different Markdown construct.

## Browser verification

[verify.cjs](verify.cjs) uses Playwright and Chromium to check all chapter/stage combinations, image decoding, diagram zoom, keyboard behavior, prompt copying, a mobile viewport, and lack of external requests with networking disabled. Install those browser tools separately from the application's locked Python environment. Set `CHROME_PATH` to use an existing Chrome executable; otherwise Playwright uses its bundled Chromium.

```sh
node docs/walkthrough/verify.cjs
```

The script writes screenshots to a temporary directory and records its observed check summary in [browser-verification.json](browser-verification.json). [validation.json](validation.json) records the final application, documentation and repository checks. External source links are optional navigation and require connectivity; they are not dependencies of the offline reader.

## Source checkpoints

The starter and each milestone implementation/recording pair are preserved as the first seven commits. This reader and the final README form commit 8. Future presentation refinements may be consolidated after milestone 3's recording without rewriting those first seven commits. The new implementation identifiers are local until explicitly published.
