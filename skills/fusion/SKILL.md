---
name: fusion
description: Fan one prompt out to multiple CLI agents (Claude Code, cursor-agent GPT/Grok) in side-by-side herdr panes, then converge them into one fused answer. Use for /fusion, when the user wants a multi-model comparison, a second opinion from other models, or a fused/converged answer.
---

# fusion

Drive the `herdr-fusion` CLI, then bring the result back into this conversation.

## Steps

1. **Preflight.** `command -v herdr-fusion` — if missing, tell the user to run
   `uv tool install git+https://github.com/noahcalibuso/herdr-fusion` and stop.
   The run needs a live herdr session; if `herdr status --json` shows no running server, say so
   and stop rather than guessing.

2. **Pick the mode.** `fuse` by default. Use `opinion` when the user only wants a comparison /
   opinions / a benchmark of models against each other, with no merged result.

3. **Compose the prompt.** Workers get NO conversation context — write a fully self-contained
   request: the task, relevant paths in this repo, constraints, and the expected deliverable.
   Do not paste secrets into it.

4. **Launch in the background** (a run takes 5–20+ minutes; never block on it in the foreground):

   ```bash
   herdr-fusion fuse "<composed prompt>" [--instruction "<merge instruction>"] [--workers a,b,c]
   ```

   Run this with the Bash tool's `run_in_background` option. `--session` defaults to
   `$HERDR_SESSION` automatically when inside herdr. Tell the user the run has started and that
   the side-by-side panes are visible in a new tab of their herdr session.

5. **On completion**, the final stdout line is `RESULT <run-dir>`. Read from that directory:
   - `fused.md` (fuse) or `comparison.md` (opinion) — the deliverable
   - `manifest.json` — per-worker status/timing; report any worker that failed or timed out
   Exit code 2 means partial: a worker died but a result was still produced.

6. **Report back**: summarize the fused answer (or the comparison), including the
   consensus/divergence section, and give the run-dir path for the full artifacts.

## Notes

- Config lives in `./fusion.toml` or `~/.config/herdr-fusion/config.toml` (workers = slot name +
  CLI command; model/effort are that CLI's own flags).
- Do not close the panes or the tab the run created — the user reads them; they clean up.
- If the run hard-fails (exit 1), read `manifest.json` and each worker's pane `tail` recorded
  there before diagnosing further.
