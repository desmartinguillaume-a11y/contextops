# Hacker News post — ContextOps v0.1.0

> **When to post:** Tuesday or Wednesday, ~9 AM ET (15h Paris). The
> empirical sweet spot for HN front-page traction.
> **Before posting:** replace the placeholder screenshot link with the
> real `docs/screenshot.png` URL on GitHub, and double-check the numbers
> in the opening paragraph reflect what the screenshot actually shows.

---

## Title

```
Show HN: ContextOps – FinOps for your Claude Code context window
```

70 characters, no emoji, no clickbait, follows the `Show HN:` convention.

---

## Submission body (the opening paragraph posted in the URL field's text box)

> A few weeks into using Claude Code I noticed my sessions were billing
> a lot more than the work justified. I started reading the JSONL
> transcripts Claude Code already writes to `~/.claude/projects/` and
> found the usual cloud-billing pathology, in miniature: oversized
> reads, repeated reads, unused MCP tool schemas loaded every turn, a
> `CLAUDE.md` that had quietly grown to 10k tokens. Same bug pattern as
> overprovisioned cloud VMs, just at the context-window scale.
>
> So I wrote a CLI that runs six heuristic auditors over those
> transcripts and prints a cost-explorer-style report — what was loaded,
> what was actually used, where the waste is, with concrete patches.
> No proxy, no API key, no model calls. Pure local file analysis.
>
> The companion `contextops fix` command is intentionally conservative:
> it only proposes disabling an MCP server when it's been *exposed*
> across ≥5 sessions for the same project **and** *unused* in ≥80% of
> them. Below those thresholds it stays silent, so a one-day refactor
> doesn't get you a recommendation to disable the GitHub MCP server you
> use every other Tuesday. The patch is a unified diff against
> `.claude/settings.local.json`; `--apply` writes it.
>
> Screenshot of the report on my own sessions: [docs/screenshot.png URL]
>
> Repo: https://github.com/desmartinguillaume-a11y/contextops
>
> Curious for feedback from anyone whose `~/.claude/projects/` has more
> than a handful of sessions in it.

---

## First comment to your own thread (post ~30 min after submission)

> Two methodology notes I want to call out before anyone asks:
>
> **The numbers undercount on purpose.** Token estimation is `len(text)
> // 4` by default; the heuristics that can't be confident stay silent
> rather than inflate the bill. If the per-finding total ever exceeds
> the actual billed total, the report clamps waste to total — better
> silent under-reporting than embarrassing inflation. Every finding
> includes a one-line "how detected" methodology so you can argue with
> it.
>
> **The auto-fix safety floor is hard-coded for v0.** The 5-session,
> 80%-unused thresholds are tuned to my own usage; they're tunable via
> `--min-sessions` and `--threshold` if you have more or fewer sessions
> per project. I'd love feedback from people whose marketplace folder
> looks different from mine — particularly anyone whose project
> structure breaks the per-project aggregation.
>
> If you find a session that produces a report you can't explain, please
> open an issue with the (redacted) JSONL —
> https://github.com/desmartinguillaume-a11y/contextops/issues. The
> failure modes I haven't seen yet are the most interesting ones.

---

## Repo "About" panel — what to put in the GitHub UI before posting

The "About" panel is edited via the ⚙️ icon next to "About" on the repo
homepage. None of this can be set via PR; you do it in the web UI.

**Description** (one sentence, ~150 chars):

```
FinOps for Claude Code — audit your context window, find waste, get safe fix patches. Local, no proxy, no API key.
```

**Topics** (paste into the topics field, space-separated):

```
claude-code finops cli python observability cost-optimization developer-tools llm tokens
```

**Homepage URL:** point at the repo itself, or at the README's "How
accurate are the numbers?" anchor for a serious-readers landing.

---

## Pre-flight checklist

- [ ] PR #3 (`contextops fix`) merged into `main`.
- [ ] PR #4 (MIT license) merged into `main`.
- [ ] `v0.1.0` tag pushed to `main`.
- [ ] `docs/screenshot.png` is a real Rich screenshot from your own
      sessions, not the ASCII mock.
- [ ] README's hero block shows numbers consistent with the screenshot.
- [ ] Repo description, topics, and homepage set in the GitHub About
      panel.
- [ ] `pip install git+https://github.com/desmartinguillaume-a11y/contextops`
      works in a fresh venv on your Mac.
- [ ] (Optional, if you want PyPI day-one) `twine upload dist/*` and
      switch the README's quickstart to `pip install contextops`.

---

## Title alternatives (in case the main one feels off)

For reference only; don't switch unless you have a strong reason. HN
rewards understated, technical titles.

1. `Show HN: ContextOps – FinOps for your Claude Code context window`
   *(recommended)*
2. `Show HN: ContextOps – audit Claude Code sessions and find wasted tokens`
3. `Show HN: I built a FinOps auditor for my Claude Code sessions`

Avoid:
- Anything with `🚀`, `Built with ❤️`, or "AI-powered."
- "X% savings" framing in the title — the body can say it; the title
  shouldn't.
- "ccusage clone" or "alternative to X" framing — position by what it
  does, not by who it competes with.
