# Movie Seats

> **Disclaimer:** This repository is a runnable educational example for showcasing the methodology
> of using Continuous Assurance skills. It is not intended as a production application.
> The code, build prompts, and recorded walkthrough are provided
> to demonstrate the methodology and support learning.

The [Continuous Assurance repository](https://github.com/hirendra-rathor/continuous-assurance) provides two skills for applying a design methodology with a coding assistant. The skills use six design perspectives to connect what a user expects with the parts of the system responsible for that behavior and the tests that show whether it works.

- **Design Proposal** helps you compare a requested change with current behavior, review the design decisions, and agree on how to verify the result before implementation.
- **Explore Design** helps you understand how the system works today by tracing a question through its code, tests, and documentation.

For an introduction to the methodology behind these skills, read [Enforcing Design Methodology with Coding Assistants](https://hirendra-rathor.github.io/articles/enforcing-design-methodology-with-coding-assistants/).

Movie Seats uses seat reservations for a movie screening as an example scenario for applying Continuous Assurance skills to software design, implementation, and verification. The [Movie Seats walkthrough](https://hirendra-rathor.github.io/examples/movie-seats/) shows the prompts we gave Claude Code, the proposals and diagrams it produced with the Design Proposal skill, and screenshots of the service at each milestone.

![A booking client asks the Movie Seats service to hold A3 and A4 together. The seat map shows the pair in a twelve-seat screening.](docs/assets/movie-seats-brief.svg)

The walkthrough follows the Claude Code implementation on the [`claude` branch](../../tree/claude). The [`codex` branch](../../tree/codex) contains the implementation Codex built from the same three prompts.

## Work through the example

Install the skills by following the instructions in the [Continuous Assurance repository](https://github.com/hirendra-rathor/continuous-assurance).

From a fresh clone of `main`, use the [three build prompts](docs/build-prompts.md) to work through the Movie Seats example one milestone at a time. First, hold a complete selection of seats. Then confirm or cancel a hold and recover a lost reply. Finally, release abandoned holds across service restarts.

Give your coding assistant one prompt at a time. Review the proposal, ask for any changes you want, and then have the assistant implement the agreed design. Try the behavior yourself and run the tests before moving to the next prompt.

## License

The application and tutorial materials are available under the [MIT License](LICENSE).
