# Movie Seats — Codex implementation

Codex built this movie seat reservation service from three prompts using the Continuous Assurance Design Proposal skill. You can hold a group of seats, confirm or cancel the reservation, and recover the result if a reply is lost. An abandoned hold expires even if the service restarts.

The FastAPI application is in `movie_seats/` and its tests are in `tests/`. Run them with `uv run --locked python -m pytest -q`. The [milestone records](docs/recordings/README.md) document this Codex build. The [Movie Seats walkthrough](https://github.com/hirendra-rathor/example-movie-seats/blob/claude/docs/recordings/README.md) follows the implementation on the `claude` branch.

For the methodology behind this educational example, read [Enforcing Design Methodology with Coding Assistants](https://hirendra-rathor.github.io/articles/enforcing-design-methodology-with-coding-assistants/).

The application and tutorial materials are available under the [MIT License](LICENSE).
