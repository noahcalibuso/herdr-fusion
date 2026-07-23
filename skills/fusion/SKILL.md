---
name: fusion
description: Fan one prompt out to multiple CLI agents in side-by-side herdr panes, then converge them into one fused answer. Use when the user wants a fused/converged multi-model answer, or asks for fusion / fuse.
---

# fusion

Drive the `herdr-fusion fuse` CLI from this agent session, then bring the result back here.

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
   request: the task, relevant paths in this repo, constraints, and the expected deliverable.
   Do not paste secrets into it.

3. **Launch in the background** (a run takes 5–20+ minutes; never block the foreground on it):

   ```bash
   herdr-fusion fuse "<composed prompt>" [--instruction "<merge instruction>"] [--workers a,b,c]
   ```

   Use whatever background/async shell mechanism this harness provides. `--session` defaults to
   `$HERDR_SESSION` automatically when inside herdr. Tell the user the run has started and that
   the side-by-side panes are visible in a new tab of their herdr session.

4. **On completion**, the final stdout line is `RESULT <run-dir>`. Read from that directory:
   - `fused.md` — the deliverable
   - `manifest.json` — per-worker status/timing; report any worker that failed or timed out
   Exit code 2 means partial: a worker died but a result was still produced.

5. **Report back**: summarize the fused answer, including the consensus/divergence section, and
   give the run-dir path for the full artifacts.

## Notes

- Config lives in `./fusion.toml` or `~/.config/herdr-fusion/config.toml` (workers = slot name +
  CLI command; model/effort are that CLI's own flags).
- Do not close the panes or the tab the run created — the user reads them; they clean up.
- If the run hard-fails (exit 1), read `manifest.json` and each worker's pane `tail` recorded
  there before diagnosing further.
- For a side-by-side comparison with no merge, use the `opinion` skill instead.
