# AGENTS.md

## Cursor Cloud specific instructions

`herdr-fusion` is a pure-Python CLI (Python ≥ 3.12) managed with `uv`. There are no
runtime dependencies; the only dev dependency is `pytest`. The startup update script
already runs `uv sync`, so the `.venv` is ready when a session begins.

Standard commands (see `README.md` "Development"):
- Tests: `uv run pytest -q`
- Run the CLI: `uv run herdr-fusion opinion "..."` or `uv run herdr-fusion fuse "..."`

There is no linter configured in this repo (no ruff/flake8/black config); "lint" is
not part of the workflow here.

Non-obvious runtime caveat: a real `opinion`/`fuse` run drives the external `herdr`
CLI plus subscription agent CLIs (`claude`, `cursor-agent`) inside a live herdr
session. None of those are installed in the cloud VM and they require interactive
logins/subscriptions, so a full real run cannot complete here. Without `herdr` on
PATH the CLI fails fast at preflight with `herdr is not reachable` (exit 1) — this is
expected, not an environment bug. To exercise the fan-out orchestration end-to-end
without the real tools, put a mock `herdr` executable on PATH that answers the JSON
protocol used in `src/herdr_fusion/harness.py` (`status`, `tab create`, `pane
split/rename/run/read/zoom`, `agent get`, `notification show`) and, on the submit
`pane run` ("Read the file <prompt> ..."), writes a stub answer to the HANDOFF path
embedded in the worker prompt. Run artifacts land in
`/tmp/herdr-fusion/<project>/<run-id>/` (`comparison.md` / `fused.md`, per-worker
`*.md`, `manifest.json`); the last stdout line is always `RESULT <run-dir>`.
