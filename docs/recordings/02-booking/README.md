# Milestone 2: finish bookings and recover replies

[Recording index](../README.md) · [Implementation checkpoint](https://github.com/hirendra-rathor/example-movie-seats/commit/9af1797ea2e4851319dd4ecc26d104b455d3a570)

This navigation and the captions below are editorial. The linked prompt and response files preserve the exchange from this fresh run.

1. [Actual milestone prompt](prompt.md), unchanged from the build guide.
2. [Proposal presented before implementation](proposal.md), with the six-perspective overview and collaboration diagram.
3. [Standing authorization](authorization.md), quoted from the user's instruction.
4. [Implementation report](implementation.md), with observed results and working-application screenshots.

[Exact proposal response source](proposal-response.txt) · [Exact implementation response source](implementation-response.txt) · [Checkpoint and checks](checkpoint.json) · [Acceptance observations](acceptance.json) · [Screenshot provenance](screenshots.json)

The proposal figures are explanatory diagrams: [overview SVG](assets/overview.svg) and [collaboration SVG](assets/collaboration.svg), with PNG display copies. [Figure data](figures.json) and the [renderer](../render_diagrams.py) preserve their editable sources. Screenshots show the running JSON API in Chromium and are labeled separately in the implementation report.

To revisit this source locally, use `git switch --detach 9af1797ea2e4851319dd4ecc26d104b455d3a570` in a separate checkout. This checkpoint's tests and process acceptance script are included in the implementation commit.

[Milestone 1 process scenario rerun](previous-scenario.json) · [Previous milestone](../01-holds/README.md)

![Working application screenshot: confirmed A3+A4 remain unavailable.](assets/screening.png)
