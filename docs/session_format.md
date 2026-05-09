# Claude Code session-log format

This document records the on-disk format used by Claude Code for its session
transcripts, as observed on Linux with Claude Code `2.1.138` (May 2026).
ContextOps depends on this format; if it changes, the loader in
`contextops/session.py` will need to track the change here.

## Location

Session logs live under the user's `~/.claude` directory:

```
~/.claude/projects/<project-id>/<session-uuid>.jsonl
```

- `<project-id>` is the slugified absolute path of the project directory.
  Example: a project at `/home/user/contextops` becomes the directory
  `~/.claude/projects/-home-user-contextops/`.
- Each `.jsonl` file is one Claude Code session, named by its UUID.

Other directories observed under `~/.claude/`:

| Path                  | Purpose                                              |
| --------------------- | ---------------------------------------------------- |
| `projects/`           | Per-project session JSONL files (what we read).      |
| `sessions/`           | Lightweight session metadata (id, last activity).    |
| `shell-snapshots/`    | Shell environment snapshots, unrelated to auditing.  |
| `session-env/`        | Per-session env vars, unrelated to auditing.         |
| `backups/`            | File backups taken before edits.                     |
| `settings.json`       | User-level Claude Code settings.                     |

ContextOps's auto-discovery walks `~/.claude/projects/` and picks the most
recently modified `.jsonl` file (or filters by `--project`).

## File format

Each line of the `.jsonl` file is one independent JSON event. Lines are
appended as the session progresses; the file is **not** valid JSON as a whole.

### Top-level event types

| `type`             | Origin                | Notes                                         |
| ------------------ | --------------------- | --------------------------------------------- |
| `user`             | User turn             | The actual prompt or tool result the model sees. |
| `assistant`        | Assistant turn        | One model response. Contains `usage`.         |
| `attachment`       | Side-channel attachment | E.g. `deferred_tools_delta`, file uploads.    |
| `queue-operation`  | Internal queueing     | `enqueue`/`dequeue`. Not billed.              |
| `last-prompt`      | UI bookmark           | Most recent user prompt for resume.           |
| `ai-title`         | UI metadata           | Auto-generated session title.                 |

ContextOps treats only `user` and `assistant` events as billable turns. The
others are skipped.

### Common fields

Every billable event carries:

- `parentUuid` — UUID of the parent event (for threading sidechain agents).
- `isSidechain` — `true` for sub-agent (Task/Agent) turns. ContextOps
  attributes their tokens to the parent session but tags them as sidechain.
- `uuid` — this event's UUID.
- `timestamp` — ISO-8601 with millis, UTC.
- `sessionId` — UUID matching the filename.

Assistant events additionally carry:

- `cwd` — working directory at the time of the turn.
- `gitBranch` — current branch at the time of the turn.
- `version` — Claude Code version.
- `entrypoint` — `local`, `remote`, etc.

### Assistant event shape

```jsonc
{
  "type": "assistant",
  "uuid": "...",
  "parentUuid": "...",
  "timestamp": "2026-05-09T19:24:28.755Z",
  "sessionId": "...",
  "cwd": "/home/user/contextops",
  "gitBranch": "main",
  "version": "2.1.138",
  "message": {
    "model": "claude-opus-4-7",
    "id": "msg_...",
    "role": "assistant",
    "type": "message",
    "content": [
      { "type": "thinking", "thinking": "...", "signature": "..." },
      { "type": "text", "text": "..." },
      { "type": "tool_use", "id": "toolu_...", "name": "Read",
        "input": { "file_path": "/abs/path", "offset": 1, "limit": 200 } }
    ],
    "stop_reason": "tool_use",
    "usage": {
      "input_tokens": 6,
      "output_tokens": 381,
      "cache_creation_input_tokens": 26805,
      "cache_read_input_tokens": 0,
      "cache_creation": {
        "ephemeral_5m_input_tokens": 0,
        "ephemeral_1h_input_tokens": 26805
      }
    }
  }
}
```

The `message` object is exactly the Anthropic Messages-API response object,
embedded verbatim. That includes the `usage` block, which is the source of
truth for token billing.

### User event shape

User events always have a `message.role == "user"`. The `content` is either:

- A string (a typed user prompt), or
- A list of content blocks. The most common block is `tool_result`:

```jsonc
{
  "type": "user",
  "uuid": "...",
  "parentUuid": "<the assistant tool_use uuid>",
  "message": {
    "role": "user",
    "content": [
      {
        "type": "tool_result",
        "tool_use_id": "toolu_...",
        "is_error": false,
        "content": "<file contents or stdout>"
      }
    ]
  }
}
```

`tool_result.content` may itself be a string or a list of blocks (e.g. for
multi-modal results). ContextOps coerces it to a string by concatenating any
`text` blocks.

### Tool-use input shapes (Claude Code built-ins)

| Tool name      | Key input fields                              |
| -------------- | --------------------------------------------- |
| `Read`         | `file_path`, optional `offset`, `limit`       |
| `Edit`         | `file_path`, `old_string`, `new_string`       |
| `Write`        | `file_path`, `content`                        |
| `Bash`         | `command`, optional `description`, `timeout`  |
| `Glob`         | `pattern`, optional `path`                    |
| `Grep`         | `pattern`, optional `path`, `glob`            |
| `LS`           | `path`                                        |
| `WebFetch`     | `url`, `prompt`                               |
| `Task`/`Agent` | `subagent_type`, `prompt`, `description`     |

MCP tools follow the convention `mcp__<server>__<tool>`.

## Pricing inputs

ContextOps reads token counts from `message.usage`:

- Billable input  = `input_tokens`
- Cache write     = `cache_creation_input_tokens` (priced higher than input)
- Cache hit       = `cache_read_input_tokens` (priced ~10% of input)
- Output          = `output_tokens`

The model name from `message.model` selects the per-million-token pricing
constants in `contextops/pricing.py`.
