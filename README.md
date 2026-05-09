# ContextOps

> **Your Claude Code session is a cloud bill. Audit it.**

ContextOps is a CLI that audits Claude Code sessions and tells you where your
tokens went, in the vocabulary of FinOps. It reads the JSONL transcripts that
Claude Code already writes to `~/.claude/projects/`, runs six heuristic
auditors over them, and prints a cost-explorer-style report with concrete
recommendations.

No proxy. No API keys. No model calls. Pure local file analysis.

```text
╭─────────────────────────── Context Utilization Report ───────────────────────────╮
│                                                                                  │
│     Total tokens billed   1,080,120                                              │
│  Estimated load-bearing     753,359  (69.7%)                                     │
│                   Waste     326,761  (30.3%)   →   $2.27                         │
│              Total cost       $2.47                                              │
│                       /repo/project  ·  claude-opus-4-7  ·  38 turns             │
│                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────╯

╭───────────────────────────── Top waste categories ───────────────────────────────╮
│                                                                                  │
│  █████████████░░░░░░░    63.0%  Bloated CLAUDE.md                                │
│  ███░░░░░░░░░░░░░░░░░    17.4%  Unused MCP / deferred tools                      │
│  ███░░░░░░░░░░░░░░░░░    14.2%  Oversized file reads                             │
│  █░░░░░░░░░░░░░░░░░░░     5.2%  Repeated file reads                              │
│  █░░░░░░░░░░░░░░░░░░░     0.1%  Redundant directory exploration                  │
│  █░░░░░░░░░░░░░░░░░░░     0.1%  Failed-then-retried tool calls                   │
│                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────╯

╭───────────────────────── Rightsizing recommendations ────────────────────────────╮
│                                                                                  │
│  → $0.85  You loaded 13 tools (8 from MCP servers: github, linear, sentry) but   │
│  only called 3 this session. Each unused schema costs ~150 tokens/turn × 38      │
│  turns × 10 unused tools = ~57,000 tokens ($0.85). Disable unused MCP servers.   │
│                                                                                  │
│  → $0.57  You read all 1,800 lines of /repo/vendor/util.js but only ~1 were      │
│  referenced in the next 5 turns. Use Read with offset and limit, or Grep first.  │
│                                                                                  │
│  → $0.45  Your CLAUDE.md is 10,829 tokens × 38 turns. Top sections by size:      │
│  FAQ (~4,180t), Code Style (~3,700t), Examples (~2,925t).                        │
│                                                                                  │
│  → $0.25  You read /repo/src/api.py 3 times; ask Claude to recall it instead.    │
│                                                                                  │
│  → $0.01  You ran LS on /repo/src 3 times. The directory rarely changes.         │
│                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────╯

Estimated savings if all recommendations applied: $2.27 (92% of bill).
```

## FinOps for context windows

The cloud world spent a decade naming the gap between *provisioned* and
*actually used* compute. LLM context windows have the exact same pathology,
and it deserves the same vocabulary.

| FinOps concept        | ContextOps equivalent                                    |
| --------------------- | -------------------------------------------------------- |
| Rightsizing           | Trim oversized file reads / tool outputs                 |
| Reserved instances    | Prompt caching for stable prefixes (CLAUDE.md, tools)    |
| Zombie resources      | File contents read once, then carried forward forever    |
| Overprovisioning      | MCP servers loaded but never invoked this session        |
| Egress costs          | Verbose assistant preambles billed at output rates       |
| Anomaly detection     | Sudden context-length spikes mid-session                 |
| Showback / chargeback | Per-project / per-task token attribution                 |

## Quickstart

```bash
pip install contextops          # or: pip install -e . from a clone
contextops analyze              # audits the most recent Claude Code session
contextops list                 # show recent sessions with their totals
```

By default ContextOps walks `~/.claude/projects/` to find sessions. Override
with `$CLAUDE_HOME` or pass an explicit path:

```bash
contextops analyze --project my-repo
contextops analyze ~/.claude/projects/-home-me-myrepo/abc123.jsonl
```

## The six auditors

ContextOps ships with six independent heuristic auditors. Each one only
looks at signals already present in the JSONL transcript — nothing is sent
over the network.

### 1. Repeated file reads (zombie resources)

Groups `Read` tool calls by absolute path. A second read of the same file,
with no `Edit` or `Write` in between, is treated as redundant — its content
was already in the model's context.

> *You read `src/api.py` 4 times this session (~12,000 tokens, $0.04). Once
> a file is in context, ask Claude to recall it instead of re-reading.
> Frequently-referenced files belong in `CLAUDE.md`.*

### 2. Oversized file reads (rightsizing)

For each `Read` larger than 5K tokens, samples ~30 distinctive substrings
from the result and checks whether they appear in the next 5 assistant
turns. If fewer than 10% are referenced, the read is flagged as oversized.

> *You read all 8,400 lines of `vendor/library.js` but only ~120 lines were
> referenced. Use `Read` with `offset`/`limit`, or `Grep` first to locate
> the relevant section.*

### 3. Redundant directory exploration (zombie resources)

Groups `LS` / `Glob` / `find` calls by normalized target path. Calls after
the first on the same target are charged as redundant.

> *You ran `LS` on `src/` 6 times. The directory structure rarely changes
> mid-session — Claude can recall it from the first call.*

### 4. Unused MCP / deferred tools (overprovisioning)

Compares the set of tools exposed to the session (via Claude Code's
`deferred_tools_delta` attachments) against the set of tools actually
invoked. Each unused tool schema is charged a conservative ~150 tokens per
assistant turn.

> *You loaded MCP servers exposing 24 tools, but only used 3 (`Read`,
> `Edit`, `Bash`). Each unused schema costs ~150 tokens/turn × 47 turns
> = ~7K tokens. Disable unused MCP servers for this project.*

### 5. Bloated `CLAUDE.md` (reserved capacity / rightsizing)

Reads the project's `CLAUDE.md`, multiplies its token count by the number
of assistant turns, and breaks it down by section so you can see *which
parts* dominate. If prompt caching is observed in `usage` blocks, the cost
is recomputed at cache-read rates.

> *Your CLAUDE.md is 4,200 tokens × 38 turns = ~160K tokens, $0.48. Three
> sub-sections (Code Style, Examples, FAQ) account for 60% of its size.*

### 6. Failed-then-retried tool calls (waste avoidance)

Detects consecutive same-name tool calls where the first returned an error
and the second's input matches at ≥80% similarity (`SequenceMatcher`).
Both are billed.

> *3 tool calls failed and were retried unchanged this session (~$0.08
> wasted). Have Claude inspect the environment (e.g. `which python`)
> before retrying.*

## How accurate are the numbers?

ContextOps is built to **undercount, not overcount**. Heuristics that can't
be sure stay quiet. Every finding includes a one-line `how detected`
methodology so you can argue with it.

Token counts use a `len(text) // 4` estimator by default. Pricing constants
live in [`contextops/pricing.py`](contextops/pricing.py) and are easy to
override. If the per-finding total ever exceeds the actual bill, ContextOps
clamps waste to total — better silent under-reporting than embarrassing
inflation.

## Architecture

```
~/.claude/projects/<project-id>/<session>.jsonl
                  │
                  ▼
        ┌──────────────────┐
        │  Session loader  │  contextops/session.py
        └────────┬─────────┘
                 │
                 ▼
        ┌──────────────────┐
        │     Auditors     │  contextops/auditors/*.py
        └────────┬─────────┘
                 │  list[Finding]
                 ▼
        ┌──────────────────┐
        │  Report renderer │  contextops/report.py
        └──────────────────┘
```

The on-disk session format is documented in
[`docs/session_format.md`](docs/session_format.md).

## Roadmap

- **Auto-fix mode** — propose CLAUDE.md trims, generate per-project MCP
  enablement diffs.
- **Anomaly detection** — flag context-length spikes and per-turn cost
  outliers across a session.
- **Showback view** — aggregate spend across all your projects, with
  per-project / per-week breakdowns.
- **OpenAI / generic provider support** — generic transcript ingestion
  for Codex CLI and similar tools.
- **Web dashboard** — same auditors, web UI, optional team mode.

## Development

```bash
git clone https://github.com/desmartinguillaume-a11y/contextops
cd contextops
pip install -e ".[dev]"
pytest
```

## License

[MIT](LICENSE). Contributions welcome.

---

*Run `contextops analyze` and find out where your tokens went.*
