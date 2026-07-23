---
name: opinion
description: Fan one prompt out to multiple CLI agents in side-by-side herdr panes for a comparison with no merge. Use when the user wants a multi-model comparison, second opinions, or a benchmark of models against each other.
---

# opinion

Drive the `herdr-fusion opinion` CLI from this agent session, then bring the result back here.

Works from any coding-agent harness that can run shell commands and read files (Claude Code,
Cursor, Codex, PI, OpenCode, …). The harness is only the launcher — workers run in herdr panes.

## Steps

1. **Preflight.**
   - `command -v herdr-fusion` — if missing, tell the user to install with
     `uv tool install git+https://github.com/noahcalibuso/herdr-fusion`
     (or run once via `uvx --from git+https://github.com/noahcalibuso/herdr-fusion herdr-fusion …`)
     and stop.
   - Needs a live herdr session; if `herdr status --json` shows no running server, say so and stop.

2. **Compose the prompt.** Workers get NO conversation context — write a fully self-contained
   request: the question, relevant paths in this repo, constraints, and what evidence to cite.
   Do not paste secrets into it.

3. **Launch in the background** (a run takes 5–20+ minutes; never block the foreground on it):

   ```bash
   herdr-fusion opinion "<composed prompt>" [--workers a,b,c]
   ```

   Use whatever background/async shell mechanism this harness provides. `--session` defaults to
   `$HERDR_SESSION` automatically when inside herdr. Tell the user the run has started and that
   the side-by-side panes are visible in a new tab of their herdr session.

4. **On completion**, the final stdout line is `RESULT <run-dir>`. Read from that directory:
   - `comparison.md` — the deliverable
   - `manifest.json` — per-worker status/timing; report any worker that failed or timed out
   Exit code 2 means partial: a worker died but a result was still produced.

5. **Report back**: summarize the comparison, including consensus and divergence across models,
   and give the run-dir path for the full artifacts.

## Notes

- Config lives in `./fusion.toml` or `~/.config/herdr-fusion/config.toml` (workers = slot name +
  CLI command; model/effort are that CLI's own flags).
- Do not close the panes or the tab the run created — the user reads them; they clean up.
- If the run hard-fails (exit 1), read `manifest.json` and each worker's pane `tail` recorded
  there before diagnosing further.
- For a merged/converged answer, use the `fusion` skill instead.
