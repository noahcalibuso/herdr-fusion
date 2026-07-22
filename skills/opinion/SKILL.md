---
name: opinion
description: Fan one prompt out to multiple CLI agents (Claude Code, PI, Cursor) in side-by-side herdr panes for a comparison with no merge. Use /opinion when the user wants a multi-model comparison, second opinions, or a benchmark of models against each other.
---

# opinion

Drive the `herdr-fusion opinion` CLI, then bring the result back into this conversation.

## Steps

1. **Preflight.** `command -v herdr-fusion` — if missing, tell the user to run
   `uv tool install git+https://github.com/noahcalibuso/herdr-fusion` and stop.
   The run needs a live herdr session; if `herdr status --json` shows no running server, say so
   and stop rather than guessing.

2. **Compose the prompt.** Workers get NO conversation context — write a fully self-contained
   request: the question, relevant paths in this repo, constraints, and what evidence to cite.
   Do not paste secrets into it.

3. **Launch in the background** (a run takes 5–20+ minutes; never block on it in the foreground):

   ```bash
   herdr-fusion opinion "<composed prompt>" [--workers a,b,c]
   ```

   Run this with the Bash tool's `run_in_background` option. `--session` defaults to
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
- For a merged/converged answer, use the `/fusion` skill instead.
