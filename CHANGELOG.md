# Changelog

All notable changes to ContextOps are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-05-10

Initial public release.

### Added

- **`contextops analyze`** — audit a Claude Code session JSONL and print a
  cost-explorer-style report (Rich-rendered, no network).
- **`contextops list`** — list recent Claude Code sessions with token totals
  and per-session cost.
- **`contextops fix`** — propose a safe, multi-session-evidenced patch to
  disable unused MCP servers in `.claude/settings.local.json`. Conservative
  defaults (`--min-sessions 5`, `--threshold 0.8`); dry-run by default;
  `--apply` writes the file.
- **Six independent heuristic auditors:**
  1. Repeated file reads (zombie resources)
  2. Oversized file reads (rightsizing)
  3. Redundant directory exploration (zombie resources)
  4. Unused MCP / deferred tools (overprovisioning)
  5. Bloated `CLAUDE.md` (reserved capacity / rightsizing)
  6. Failed-then-retried tool calls (waste avoidance)
- **Pricing module** — Anthropic model pricing constants with prompt-cache
  awareness; easy to override.
- **Robust JSONL session loader** — silently skips malformed records,
  unknown event types, and missing fields rather than crashing.
- **Test suite** — 41 unit / robustness / CLI smoke / performance tests
  passing on Python 3.10 / 3.11 / 3.12.
- **Documentation** — `docs/session_format.md`, `docs/testing.md`,
  `docs/publishing.md`, `docs/hn_post.md`.
- **Screenshot capture script** — `scripts/capture_screenshot.py` renders
  `analyze` output to a static SVG suitable for the README.

### Notes

- Token estimation uses `len(text) // 4` by default. Pricing constants
  live in `contextops/pricing.py` and are easy to override.
- If the per-finding waste total ever exceeds the actual billed total, the
  report clamps waste to total — undercounting is the design choice.
- The `fix` command's safety floor is hard-coded to be conservative; tune
  via `--min-sessions` and `--threshold` if you have a different usage
  rhythm.

[Unreleased]: https://github.com/desmartinguillaume-a11y/contextops/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/desmartinguillaume-a11y/contextops/releases/tag/v0.1.0
