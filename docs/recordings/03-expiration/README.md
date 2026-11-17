# Milestone 3: release abandoned holds

[Recording index](../README.md) · [Implementation checkpoint](https://github.com/hirendra-rathor/example-movie-seats/commit/0e994e4e7c1220ea5568f68b32fe685abf4adb78)

This navigation and the captions below are editorial. The linked prompt and response files preserve the exchange from this fresh run.

1. [Actual milestone prompt](prompt.md), unchanged from the build guide.
2. [Proposal presented before implementation](proposal.md), with the six-perspective overview and collaboration diagram.
3. [Standing authorization](authorization.md), quoted from the user's instruction.
4. [Implementation report](implementation.md), with observed results and working-application screenshots.

[Exact proposal response source](proposal-response.txt) · [Exact implementation response source](implementation-response.txt) · [Checkpoint and checks](checkpoint.json) · [Acceptance observations](acceptance.json) · [Screenshot provenance](screenshots.json)

The proposal figures are explanatory diagrams: [overview SVG](assets/overview.svg) and [collaboration SVG](assets/collaboration.svg), with PNG display copies. [Figure data](figures.json) and the [renderer](../render_diagrams.py) preserve their editable sources. Screenshots show the running JSON API in Chromium and are labeled separately in the implementation report.

To revisit this source locally, use `git switch --detach 0e994e4e7c1220ea5568f68b32fe685abf4adb78` in a separate checkout. This checkpoint's tests and process acceptance script are included in the implementation commit.

[Previous milestone](../02-booking/README.md) · [Container replacement result](container-acceptance.json) · [Milestone 1 regression](milestone-1-regression.json) · [Milestone 2 regression](milestone-2-regression.json)

![Working application screenshot: a new hold owns A3+A4 while B1+B2 remain confirmed.](assets/screening.png)

![Working application screenshot: the replacement A3+A4 hold has a different ID and its own deadline.](assets/reservation-3.png)
