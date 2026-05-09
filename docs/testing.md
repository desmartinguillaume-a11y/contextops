# Testing strategy

ContextOps ships with three layers of tests, all run by `pytest`.

## 1. Unit tests, one file per auditor

Each auditor has at least two tests: one positive (it fires when expected)
and one negative (it stays silent when expected). All use the
`SessionBuilder` DSL in `tests/conftest.py` to assemble synthetic JSONL
sessions — no real session data ever ends up in the repo.

| File                                       | What it covers                                   |
| ------------------------------------------ | ------------------------------------------------ |
| `test_session.py`                          | Loader: events → typed `Session` model           |
| `test_repeated_file_reads.py`              | Auditor 1                                        |
| `test_oversized_file_reads.py`             | Auditor 2                                        |
| `test_redundant_exploration.py`            | Auditor 3                                        |
| `test_unused_mcp_tools.py`                 | Auditor 4                                        |
| `test_bloated_claude_md.py`                | Auditor 5                                        |
| `test_failed_then_retried.py`              | Auditor 6                                        |
| `test_report.py`                           | Renderer + the waste-cap safeguard               |

## 2. Loader robustness — `test_loader_robustness.py`

Real sessions are messy. These tests guarantee the loader never crashes
on inputs we'd see in the wild:

- Empty / blank-line-only files
- Malformed JSON lines mixed with valid ones
- Truncated last line (sessions appended live)
- Unknown event types (`skill_listing`, `todo_reminder`, `system`, …)
- Assistant turns missing `usage`
- User content as a string, list of blocks, or list with unknown blocks
- `tool_result.content` as a list of text blocks (multimodal API shape)
- Unicode and replacement characters

Plus parametric tests over `Pricing.for_model(...)` to make sure no model
ID falls through to a NameError.

## 3. End-to-end CLI smoke tests — `test_cli_smoke.py`

Invokes the installed `contextops` entry point via subprocess (no Python
imports, no `Typer.testing.CliRunner`). Confirms the binary actually
works the way users will:

- `contextops version` and `contextops --help` succeed
- `contextops analyze` against a synthetic session prints the report
- `contextops analyze` with an empty `$CLAUDE_HOME` exits non-zero with
  a useful message
- `contextops analyze --project NAME` matches by substring
- `contextops list` handles the empty-home case

## 4. Performance — `test_perf.py`

Builds a ~5 MB synthetic session (4000 turns, mix of `Read`, `LS`, plain
text), then asserts `load + audit` finishes in under 3 seconds on CI
hardware. Real laptops are 5–10× faster.

## CI

`.github/workflows/test.yml` runs the full suite on Python 3.10, 3.11,
and 3.12 on every push and PR.

## Verifying the on-disk session format on a new platform

The single largest unknown for ContextOps is whether the JSONL format we
parse matches what real Claude Code users have on disk. Different
versions, OSes, and harnesses (Agent SDK vs. local CLI) may differ.

To verify on a new machine, run the bundled inspector:

```bash
python scripts/inspect_session_format.py
# or, pointing at a specific directory:
python scripts/inspect_session_format.py ~/.claude/projects
```

It walks the candidate session directories, picks the three most recent
`.jsonl` files, and prints (with home-directory paths redacted) the
event-type counts, tool-call counts, declared-tool counts, content
shapes, and one trimmed example of each event type. The output is small
enough to paste into a GitHub issue when reporting an unexpected format.

Output gets sent **nowhere** — the script is stdlib-only and reads files,
prints to stdout, and exits.

## Honest gaps (todo for v0.2)

- Snapshot tests of the rendered report would catch unintended visual
  regressions; punting until the renderer settles.
- We don't yet exercise a session that uses the alternate
  top-level `toolUseResult` field observed in some Claude Code 2.1 user
  events; the loader currently only consults `message.content`.
- We don't flag `isApiErrorMessage` assistant turns (failed model calls
  that may still be billed).
- Pricing constants are calibrated by hand; we don't have a fixture per
  model that round-trips a known bill.
