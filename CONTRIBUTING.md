# Contributing to rosbridge-mcp

Thanks for your interest in contributing!

## Getting started

1. Fork and clone the repository.
2. Install in development mode: `pip install -e ".[dev]"`
3. Run the test suite: `pytest` (no ROS required — tests use an in-process mock rosbridge server).

## Pull requests

- Keep PRs focused: one feature or fix per PR.
- Add or update tests for any behavior change.
- Make sure `pytest` passes locally and CI is green.
- Use clear commit messages (Conventional Commits style is appreciated, e.g. `feat:`, `fix:`, `docs:`).

## Developer Certificate of Origin (DCO)

By contributing, you certify that you have the right to submit your work under the MIT license ([developercertificate.org](https://developercertificate.org)). Please sign off each commit:

```bash
git commit -s -m "feat: my change"
```

This adds a `Signed-off-by: Your Name <you@example.com>` line to the commit message.

## Reporting issues

Open a GitHub issue with reproduction steps, your ROS 2 distro, rosbridge_suite version, and the MCP client you are using.
