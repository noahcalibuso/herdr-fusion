# herdr-fusion

[fusion-harness](https://github.com/disler/fusion-harness), rebuilt on [herdr](https://herdr.dev)
panes and **subscription CLI agents** — no API keys, no per-token billing.

One prompt fans out to N coding agents running side by side in herdr panes (Claude Code on your
Claude subscription; GPT and Grok through `cursor-agent` on your Cursor subscription). You watch
them work in parallel. Then a fresh **fusion agent** critically merges the answers into one
definitive result, with inline attribution and a consensus/divergence report.

```
┌────────────┬────────────┬────────────┐
│  CLAUDE    │    GPT     │    GROK    │   ← same prompt, independent answers
│  claude    │ cursor-agent│ cursor-agent│
├────────────┴────────────┴────────────┤
│               FUSION                 │   ← merges all answers → fused.md
└──────────────────────────────────────┘
```

## Requirements

- **herdr ≥ 0.7.4** with a running session, and the agent-state integration installed for each
  CLI you fan out to (`herdr integration install claude`, `... cursor`, etc.). Without the
  integration a worker still runs, but completion falls back to file-stability detection.
- The agent CLIs themselves on `PATH` and logged in (`claude`, `cursor-agent`, ...).
- Python ≥ 3.12 (`uv` recommended).

## Install

```bash
uv tool install git+https://github.com/noahcalibuso/herdr-fusion
```

As a **Claude Code plugin** (adds the `/fusion` skill so a Claude session can launch a run and
pull the fused answer back into its own context):

```
/plugin install noahcalibuso/herdr-fusion
```

## Usage

Run from any shell pane **inside a herdr session** (the run lands in a new tab of that session):

```bash
# side-by-side comparison only (read-only workers)
herdr-fusion opinion "Should we migrate this repo from npm to pnpm? Cite evidence."

# full fan-out, then convergence into one answer
herdr-fusion fuse "Design a rate limiter for our API gateway."

# pick workers / merge instruction / fusion model per run
herdr-fusion fuse "..." --workers claude,gpt --fusion claude \
  --instruction "Produce a single implementation plan; prefer the simpler design on conflicts."
```

Every run gets a directory `/tmp/herdr-fusion/<project>/<run-id>/` with each worker's
`<name>.prompt.md` and `<name>.md` answer, `comparison.md` (opinion) or `fused.md` (fuse), and a
`manifest.json` of statuses and timings. The last stdout line is always `RESULT <run-dir>`.
Exit codes: `0` all workers answered, `2` partial (some worker failed/timed out but a result was
produced), `1` hard failure. Panes stay open afterwards — the side-by-side *is* the UI; close the
tab when you're done reading.

## Configuration

`./fusion.toml`, else `~/.config/herdr-fusion/config.toml`, else built-in defaults.
See [fusion.example.toml](fusion.example.toml):

```toml
[fusion]
runner = "claude"                # worker slot whose CLI runs the merge (fresh pane)

[workers.claude]
command = "claude --permission-mode bypassPermissions --model opus"

[workers.gpt]
command = "cursor-agent --force --model gpt-5.2"

[workers.grok]
command = "cursor-agent --force --model grok-4"
```

> **Workers run unattended.** A permission prompt nobody answers stalls the run, so the default
> commands use each CLI's autonomous mode (`--permission-mode bypassPermissions` / `--force`) —
> the same posture as fusion-harness's full-tool children. Drop those flags if you'd rather
> approve tool calls in the panes yourself (you're watching them anyway); the run then waits on
> you. First-time setup dialogs (folder trust, logins) must be answered once manually — the
> harness fails fast with the pane contents if a worker blocks at launch.

A worker is just a slot name plus the exact command line to launch its interactive TUI — herdr
has no model concept, so **model and effort are whatever flags that CLI accepts**:

- `cursor-agent` parameterized models take bracket overrides: `cursor-agent --model 'claude-opus-4-8[effort=high]'`.
  Verify names with `cursor-agent --list-models`.
- Claude Code takes `--model`; thinking budget via env: `command = "env MAX_THINKING_TOKENS=32000 claude"`.
- Any agent CLI with a herdr integration works: `codex`, `pi`, `opencode`, ...

Defining `[workers.*]` in a config file replaces the default set (your set is your set);
`[fusion]` keys merge over defaults.

## How it maps to fusion-harness

| fusion-harness | herdr-fusion |
|---|---|
| `/opinion` (2 models, read-only, side-by-side columns) | `opinion` (N workers, read-only prompt, real panes + `comparison.md`) |
| `/fusion` (2 workers + fresh fusion agent on the architect model) | `fuse` (N workers + fresh pane on `[fusion].runner`) |
| Spawns `pi --mode json -p` subprocesses on API billing | Drives interactive subscription CLIs in herdr panes |
| Worker/merge/opinion prompt templates | Same templates, generalized 2-way → N-way, in [src/herdr_fusion/prompts/](src/herdr_fusion/prompts/) |
| Shared cwd, collisions avoided by prompt discipline | Same convention |
| `/auto-validate` gate loop | Not ported (out of scope) |

Handoff is file-based: each worker is told to write its complete answer to
`<run-dir>/<name>.md`; the merge prompt inlines every answer (truncated at 60k chars) plus the
authoritative file paths. Completion gating: answer file exists + stopped growing + agent status
`idle`/`done` (herdr reports `done` when the pane is backgrounded, `idle` when focused — both
mean finished).

## Development

```bash
uv sync
uv run pytest -q
```

Prompts are plain `.md` files with `{{VAR}}` interpolation — edit them to change behavior.

## License

MIT
