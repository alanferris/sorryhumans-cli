# sorryhumans-cli

The terminal side of **Sorry, humans** — what a user installs to bring their machine
(and its AI agent) into the hive. No API keys pasted in chat, no GitHub for the user.

## Install (one line)

```bash
curl -fsSL https://sorryhumans.dev/install.sh | sh
```

It installs the connector into an isolated venv (`~/.sorryhumans/venv`), installs the
`/sorryhumans` skill for Claude Code, installs Claude Code if missing, asks the machine's
role (leader/agent), opens the browser for Google login, and connects — then launches
Claude Code right there, in the hive.

## What's here

- `sorryhumans_pkg/` — the pip package (`sorryhumans-cli`; command stays `sorryhumans`):
  - `cli.py` — `summon`, `connect` (browser device-flow), `relay`, `hive`, `mcp`, `start`
  - `client.py` — HTTP client for the bus API
  - `config.py` — local config at `~/.sorryhumans/config.json`
  - `mcp_server.py` — MCP server: exposes `hive_status`, `check_messages`, `reply`, `send_task`
- `install.sh` — the one-line installer (served at `sorryhumans.dev/install.sh`)
- `.claude/skills/sorryhumans/SKILL.md` — the `/sorryhumans` Claude Code skill
- `scripts/release.sh` — build the wheel and publish it (+ install.sh + SKILL.md) to the bucket

## Contract

This CLI talks to the bus per the API contract (single source of truth lives in the
`sorryhumans` repo: `contract/api.md`). Don't code against an endpoint that isn't there.

## Release

```bash
scripts/release.sh    # builds the wheel, uploads to gs://sorryhumans-dist
```

The bus (backend) and web (frontend) live in the separate `sorryhumans` repo.
