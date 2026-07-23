# herdr-fusion

![Python](https://img.shields.io/badge/python-3.12+-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Dependencies](https://img.shields.io/badge/runtime%20deps-0-brightgreen) ![Built on](https://img.shields.io/badge/built%20on-herdr-8a2be2)

**Fan one prompt out to several subscription coding-agent CLIs running side by side, then have a
fresh agent critically merge their answers into one.** No API keys, no per-token billing — it drives
the interactive agent TUIs you already pay for.

```
┌────────────┬────────────┐
│  CLAUDE    │    GPT     │   ← same prompt, independent answers
│  claude    │  pi-agent  │
├────────────┴────────────┤
│         FUSION          │   ← merges all answers → fused.md
└─────────────────────────┘
```

<!-- DEMO: replace with a recorded gif of a live run (see "Demo" below) -->
> **Demo:** _recording coming — a real fan-out-then-converge run in herdr panes._

A reimagining of [fusion-harness](https://github.com/disler/fusion-harness) rebuilt on
[herdr](https://herdr.dev) panes and **CLI agents**, so that you can make use subscription
rather than API usage. 

Use the **/fusion** skill, One prompt fans out to N coding agents in parallel panes.
Then a fresh **fusion agent** merges the answers into one definitive result with inline
attribution and a consensus/divergence report.

### What this project demonstrates

- **Orchestrating *interactive* agent TUIs unattended** — launch detection, prompt submission, and
  completion gating for tools built for a human at a keyboard, with no exit code or "done" event to
  rely on.
- **Zero runtime dependencies** — the whole harness is ~400 lines of standard-library Python behind
  a single integration surface (the `herdr` CLI; IDs parsed from responses, never constructed).
- **Graceful degradation** — completion detection combines agent-status polling with file-stability
  and falls back cleanly when a CLI has no status integration.
- **Fail-fast ergonomics** — a worker stuck on a first-run trust/login dialog raises immediately with
  the pane's on-screen contents, instead of hanging until timeout.

📐 **[Read the design notes / case study →](DESIGN.md)** for the architecture, the three decisions
that mattered, and what I'd build next.

## Requirements

- **herdr ≥ 0.7.4** with a running session, and the agent-state integration installed for each
  CLI you fan out to (`herdr integration install claude`, `... cursor`, etc.). Without the
  integration a worker still runs, but completion falls back to file-stability detection.
- The agent CLIs themselves on `PATH` and logged in (`claude`, `cursor-agent`, ...).
- Python ≥ 3.12 (`uv` recommended).

## Install

### CLI

Try it with no install (uv's npx equivalent):

```bash
uvx --from git+https://github.com/noahcalibuso/herdr-fusion herdr-fusion fuse "..."
```

Or install the `herdr-fusion` command permanently:

```bash
uv tool install git+https://github.com/noahcalibuso/herdr-fusion
```

### Skills (any agent harness)

The `fusion` and `opinion` skills are [Agent Skills](https://agentskills.io)-compatible — install
them into Claude Code, Cursor, Codex, OpenCode, PI, and other supported harnesses with one
command:

```bash
npx skills add noahcalibuso/herdr-fusion
```

Useful variants:

```bash
# list skills in this repo
npx skills add noahcalibuso/herdr-fusion --list

# global install / specific agents
npx skills add noahcalibuso/herdr-fusion -g -a cursor -a claude-code -a codex
```

Claude Code users can instead install via the plugin marketplace (same skills, Claude-only path):

```
/plugin marketplace add noahcalibuso/herdr-fusion
/plugin install herdr-fusion@herdr-fusion
```


## Configuration

`./fusion.toml`, else `~/.config/herdr-fusion/config.toml`, else built-in defaults.
See [fusion.example.toml](fusion.example.toml):

```toml
[fusion]
runner = "claude"                # worker slot whose CLI runs the merge (fresh pane)

[workers.claude]
command = "claude --permission-mode bypassPermissions --model opus"

[workers.gpt]
command = "pi --provider openai-codex --model gpt-5.6-sol --thinking high --approve"
```

> **Workers run unattended.** A permission prompt nobody answers stalls the run, so the default
> commands use each CLI's autonomous mode (`--permission-mode bypassPermissions` / `--approve` / `--force`) —
> the same posture as fusion-harness's full-tool children. Drop those flags if you'd rather
> approve tool calls in the panes yourself (you're watching them anyway); the run then waits on
> you. First-time setup dialogs (folder trust, logins) must be answered once manually — the
> harness fails fast with the pane contents if a worker blocks at launch.

A worker is just a slot name plus the exact command line to launch its interactive TUI — herdr
has no model concept, so **model and effort are whatever flags that CLI accepts**:

- `pi` selects backends with `--provider`/`--model` (`pi --list-models`); `cursor-agent` parameterized
  models take bracket overrides: `cursor-agent --model 'claude-opus-4-8[effort=high]'`.
- Claude Code takes `--model`; thinking budget via env: `command = "env MAX_THINKING_TOKENS=32000 claude"`.
- Any agent CLI with a herdr integration works: `codex`, `pi`, `opencode`, ...

Defining `[workers.*]` in a config file replaces the default set (your set is your set);
`[fusion]` keys merge over defaults.


## Usage

### Agent Skills (recommended)

After installing the skills, ask your Agent Skills-compatible coding agent in natural language:

> /fusion design a rate limiter for our API gateway, then return one fused implementation plan.

For a comparison without a merge, ask:

> /opinion should we migrate this repo from npm to pnpm. Cite and summarize evidence.

You can include supported run preferences in the request. For example:

> Use the fusion skill with the `claude` and `gpt` workers. Merge their answers into one
> implementation plan, preferring the simpler design when they conflict.


### Direct CLI (manual/advanced)

To invoke the harness yourself, run from any shell pane **inside a herdr session** (the run lands
in a new tab of that session):

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


## Development

```bash
uv sync
uv run pytest -q
```

Prompts are plain `.md` files with `{{VAR}}` interpolation — edit them to change behavior.

## License

MIT
