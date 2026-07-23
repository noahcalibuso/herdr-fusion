"""Drive a fusion-harness run through herdr-managed panes.

All herdr interaction goes through the `herdr` CLI (one subprocess per call);
IDs are always parsed from responses, never constructed.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

PROMPTS = Path(__file__).parent / "prompts"
HANDOFF_MAX = 60_000
POLL_SECONDS = 3.0

# Workers run unattended in background panes: a permission prompt they can't
# answer stalls the whole run, so defaults bypass prompting (upstream's children
# likewise ran with full tools pre-authorized). Tighten via your own config.
DEFAULT_CONFIG: dict = {
    "fusion": {"runner": "claude"},
    "workers": {
        "claude": {"command": "claude --permission-mode bypassPermissions"},
        "gpt": {"command": "pi --provider openai-codex --model gpt-5.6-sol --thinking high --approve"},
    },
}


class HerdrError(RuntimeError):
    pass


def herdr(session: str, *args: str, timeout: float = 60.0):
    cmd = ["herdr", "--session", session, *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        # herdr writes error JSON to stderr on failure
        detail = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        raise HerdrError(f"{' '.join(cmd)}: {detail}")
    out = proc.stdout.strip()
    if not out:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"raw": out}


def deep_get(obj, key: str):
    """First value for `key` anywhere in a nested JSON structure."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = deep_get(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = deep_get(v, key)
            if found is not None:
                return found
    return None


def fill(template: str, vars: dict) -> str:
    text = (PROMPTS / template).read_text()
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(vars.get(m.group(1), "")), text)


def load_config(explicit: str | None = None) -> dict:
    """./fusion.toml, else ~/.config/herdr-fusion/config.toml, else defaults.

    A config file's [workers] table REPLACES the default workers (defining your
    own set means you want exactly that set); [fusion] keys merge over defaults.
    """
    if explicit:
        candidates = [Path(explicit)]
    else:
        candidates = [
            Path("fusion.toml"),
            Path.home() / ".config" / "herdr-fusion" / "config.toml",
        ]
    cfg = {
        "fusion": dict(DEFAULT_CONFIG["fusion"]),
        "workers": {k: dict(v) for k, v in DEFAULT_CONFIG["workers"].items()},
    }
    for path in candidates:
        if path.is_file():
            data = tomllib.loads(path.read_text())
            cfg["fusion"].update(data.get("fusion", {}))
            if "workers" in data:
                cfg["workers"] = {k: dict(v) for k, v in data["workers"].items()}
            break
    return cfg


@dataclass
class Worker:
    name: str
    command: str
    pane_id: str = ""
    status: str = "pending"  # pending | running | done | timeout | failed
    seconds: float = 0.0
    tail: str = ""

    @property
    def role(self) -> str:
        return self.name.upper()


def peers_line(worker: Worker, workers: list[Worker]) -> str:
    others = [w for w in workers if w.name != worker.name]
    return ", ".join(f"{w.role} ({w.command})" for w in others) or "none"


def tab_slug(mode: str, prompt: str, limit: int = 48) -> str:
    """Short one-line tab label from the request, e.g. 'fuse: rate limiter design'."""
    text = " ".join(prompt.split())
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return f"{mode}: {text}" if text else mode


def worker_prompt(mode: str, worker: Worker, workers: list[Worker],
                  answer_path: Path, prompt: str) -> str:
    template = "opinion.md" if mode == "opinion" else "worker.md"
    return fill(template, {
        "ROLE": worker.role,
        "MODEL": worker.command,
        "TAG": worker.name,
        "PEERS": peers_line(worker, workers),
        "ANSWER_PATH": answer_path,
        "PROMPT": prompt,
    })


def merge_prompt(workers: list[Worker], run_dir: Path, fused_path: Path,
                 prompt: str, instruction: str | None) -> str:
    instruction = instruction or (PROMPTS / "default_instruction.md").read_text().strip()
    path_lines, sections = [], []
    for w in workers:
        p = run_dir / f"{w.name}.md"
        path_lines.append(f"- [{w.role}]'s full raw answer: {p}")
        text = p.read_text() if p.is_file() else "(no answer produced — this worker failed or timed out)"
        if len(text) > HANDOFF_MAX:
            text = text[:HANDOFF_MAX] + f"\n\n[... truncated at {HANDOFF_MAX} chars — full answer at {p}]"
        sections.append(f"# ANSWER FROM [{w.role}] — {w.command}\n{text}")
    return fill("merge.md", {
        "N": len(workers),
        "FUSION_INSTRUCTION": instruction,
        "RUN_TAG": "-".join(w.name for w in workers),
        "RUN_DIR": run_dir,
        "ANSWER_PATH_LINES": "\n".join(path_lines),
        "HANDOFF_MAX": HANDOFF_MAX,
        "PROMPT": prompt,
        "ANSWER_SECTIONS": "\n\n".join(sections),
        "ROLE_EXAMPLES": " or ".join(f"[{w.role}]" for w in workers[:2]),
        "FUSED_PATH": fused_path,
    })


def listen_prompt(workers: list[Worker], run_dir: Path, fused_path: Path,
                  prompt: str, instruction: str | None, wait_budget: float) -> str:
    """Merge prompt for a fusion agent spawned BEFORE the workers finish: it is
    told to poll for the answer files, not handed their (not-yet-written) text."""
    instruction = instruction or (PROMPTS / "default_instruction.md").read_text().strip()
    path_lines = [f"- [{w.role}] ({w.command}): {run_dir / f'{w.name}.md'}" for w in workers]
    return fill("listen.md", {
        "N": len(workers),
        "FUSION_INSTRUCTION": instruction,
        "RUN_TAG": "-".join(w.name for w in workers),
        "ANSWER_PATH_LINES": "\n".join(path_lines),
        "PROMPT": prompt,
        "ROLE_EXAMPLES": " or ".join(f"[{w.role}]" for w in workers[:2]),
        "FUSED_PATH": fused_path,
        "WAIT_BUDGET": int(wait_budget),
    })


class Harness:
    def __init__(self, session: str, cwd: Path, run_dir: Path, echo=print, notify=True):
        self.session = session
        self.cwd = cwd
        self.run_dir = run_dir
        self.echo = echo
        self.notify_enabled = notify
        self.manifest: dict = {}

    def h(self, *args: str, timeout: float = 60.0):
        return herdr(self.session, *args, timeout=timeout)

    def save_manifest(self):
        (self.run_dir / "manifest.json").write_text(json.dumps(self.manifest, indent=2, default=str))

    def preflight(self):
        try:
            status = self.h("status", "--json")
        except (HerdrError, FileNotFoundError) as e:
            raise HerdrError(f"herdr is not reachable: {e}") from e
        server = status.get("server", status) if isinstance(status, dict) else {}
        if not deep_get(server, "running"):
            raise HerdrError(
                f"No herdr server running for session '{self.session}'. "
                "Start herdr (or pass --session) first."
            )

    def rename_origin_tab(self, label: str):
        """Relabel the tab this run was launched from (herdr sets HERDR_TAB_ID in
        the launching pane) so it reads as the control tab for the fusion tab we
        just opened. Best-effort — a failed rename never fails the run."""
        origin = os.environ.get("HERDR_TAB_ID")
        if not origin or origin == self.manifest.get("tab_id"):
            return
        try:
            self.h("tab", "rename", origin, label)
        except HerdrError:
            pass

    def make_layout(self, label: str, n: int) -> list[str]:
        resp = self.h("tab", "create", "--label", label, "--cwd", str(self.cwd), "--no-focus")
        self.manifest["tab_id"] = deep_get(resp, "tab_id")
        first = deep_get(resp, "pane_id")
        if not first:
            raise HerdrError(f"tab create returned no pane_id: {resp}")
        panes = [str(first)]
        for _ in range(n - 1):
            resp = self.h("pane", "split", panes[-1], "--direction", "right",
                          "--no-focus", "--cwd", str(self.cwd))
            pane = deep_get(resp, "pane_id")
            if not pane:
                raise HerdrError(f"pane split returned no pane_id: {resp}")
            panes.append(str(pane))
        # ponytail: shells need a beat before pane run's keystrokes land; a
        # process-info readiness poll is the upgrade path.
        time.sleep(1.5)
        return panes

    def make_fuse_layout(self, label: str, n_workers: int) -> tuple[list[str], str]:
        """N worker panes across the top, one wide fusion-listener pane below them.
        Split the footer off FIRST so it spans the full width before the top row
        is divided into columns. Returns (worker_panes, footer_pane)."""
        resp = self.h("tab", "create", "--label", label, "--cwd", str(self.cwd), "--no-focus")
        self.manifest["tab_id"] = deep_get(resp, "tab_id")
        top = deep_get(resp, "pane_id")
        if not top:
            raise HerdrError(f"tab create returned no pane_id: {resp}")
        resp = self.h("pane", "split", str(top), "--direction", "down",
                      "--ratio", "0.4", "--no-focus", "--cwd", str(self.cwd))
        footer = deep_get(resp, "pane_id")
        if not footer:
            raise HerdrError(f"footer split returned no pane_id: {resp}")
        panes = [str(top)]
        for _ in range(n_workers - 1):
            resp = self.h("pane", "split", panes[-1], "--direction", "right",
                          "--no-focus", "--cwd", str(self.cwd))
            pane = deep_get(resp, "pane_id")
            if not pane:
                raise HerdrError(f"pane split returned no pane_id: {resp}")
            panes.append(str(pane))
        time.sleep(1.5)
        return panes, str(footer)

    def agent_status(self, pane_id: str) -> str:
        try:
            return str(deep_get(self.h("agent", "get", pane_id), "agent_status") or "unknown")
        except HerdrError:
            return "unknown"  # agent_not_found: plain shell, no agent yet

    def pane_tail(self, pane_id: str, lines: int = 60) -> str:
        # --lines below the viewport height returns empty; always over-fetch.
        try:
            resp = self.h("pane", "read", pane_id, "--source", "recent-unwrapped", "--lines", "300")
        except HerdrError:
            return ""
        text = resp.get("raw") or deep_get(resp, "text") or ""
        return "\n".join(str(text).splitlines()[-lines:])

    def launch(self, worker: Worker, launch_timeout: float):
        self.h("pane", "rename", worker.pane_id, worker.name)
        self.h("pane", "run", worker.pane_id, worker.command)
        deadline = time.monotonic() + launch_timeout
        blocked_polls = 0
        while time.monotonic() < deadline:
            status = self.agent_status(worker.pane_id)
            if status in ("idle", "done"):
                return
            # blocked at launch = a startup dialog (folder trust, login, theme)
            # nobody is there to answer — fail fast with the screen contents.
            blocked_polls = blocked_polls + 1 if status == "blocked" else 0
            if blocked_polls >= 3:
                worker.tail = self.pane_tail(worker.pane_id)
                raise HerdrError(
                    f"{worker.name}: agent is blocked on a startup dialog after "
                    f"`{worker.command}` — answer it once manually (e.g. folder "
                    f"trust) or adjust the command's flags. Pane tail:\n{worker.tail}"
                )
            time.sleep(2.0)
        worker.tail = self.pane_tail(worker.pane_id)
        raise HerdrError(
            f"{worker.name}: agent never reached idle after `{worker.command}` "
            f"(is its herdr integration installed?). Pane tail:\n{worker.tail}"
        )

    def submit(self, pane_id: str, prompt_path: Path):
        # `pane run` only starts shell commands; it can't type into an
        # already-running agent TUI. Deliver the prompt as keystrokes instead.
        # One-line pointer sidesteps multi-line paste behavior in agent TUIs.
        self.h("pane", "send-text", pane_id,
               f"Read the file {prompt_path} and follow the instructions in it exactly.")
        self.h("pane", "send-keys", pane_id, "Enter")

    def await_answer(self, worker: Worker, answer_path: Path, timeout: float) -> bool:
        """Answer file exists, stopped growing, and the agent is no longer working.

        Completed agents report `done` when backgrounded but `idle` when focused,
        so accept either; `unknown` (no integration) falls back to file stability.
        """
        started = time.monotonic()
        deadline = started + timeout
        last_size, stable = -1, 0
        while time.monotonic() < deadline:
            if answer_path.is_file():
                size = answer_path.stat().st_size
                stable = stable + 1 if size == last_size and size > 0 else 0
                last_size = size
                status = self.agent_status(worker.pane_id)
                if stable >= 1 and status in ("idle", "done"):
                    break
                if stable >= 3 and status == "unknown":
                    break
            time.sleep(POLL_SECONDS)
        else:
            worker.status = "timeout"
            worker.seconds = round(time.monotonic() - started, 1)
            worker.tail = self.pane_tail(worker.pane_id)
            return False
        worker.status = "done"
        worker.seconds = round(time.monotonic() - started, 1)
        return True

    def notify(self, title: str, body: str):
        if not self.notify_enabled:
            return
        try:
            self.h("notification", "show", title, "--body", body, "--sound", "done")
        except HerdrError:
            pass  # a failed toast never fails the run


def run(mode: str, prompt: str, cfg: dict, worker_names: list[str] | None = None,
        fusion_runner: str | None = None, session: str = "default",
        cwd: Path | None = None, instruction: str | None = None,
        worker_timeout: float = 1200, launch_timeout: float = 120,
        fusion_timeout: float = 1800, notify: bool = True, echo=print) -> int:
    cwd = (cwd or Path.cwd()).resolve()
    available = cfg["workers"]
    names = worker_names or list(available)
    unknown = [n for n in names if n not in available]
    if unknown:
        raise SystemExit(f"unknown worker(s) {unknown}; configured: {list(available)}")
    workers = [Worker(n, available[n]["command"]) for n in names]

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = Path("/tmp/herdr-fusion") / cwd.name / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    hz = Harness(session, cwd, run_dir, echo=echo, notify=notify)
    hz.manifest = {
        "mode": mode, "prompt": prompt, "session": session, "cwd": str(cwd),
        "created": datetime.now(timezone.utc).isoformat(),
        "workers": {}, "fusion": None,
    }
    hz.preflight()

    echo(f"run dir: {run_dir}")
    fused_path = run_dir / "fused.md"
    fusion = None
    if mode == "fuse":
        # Wide fusion-listener pane below the worker row, launched UP FRONT so it
        # watches the answers land live instead of being spawned after the fact.
        runner_name = fusion_runner or cfg["fusion"]["runner"]
        if runner_name not in available:
            raise SystemExit(f"fusion runner '{runner_name}' is not a configured worker")
        panes, fusion_pane = hz.make_fuse_layout(f"fusion {run_id}", len(workers))
        fusion = Worker("fusion", available[runner_name]["command"])
        fusion.pane_id = fusion_pane
    else:
        panes = hz.make_layout(f"fusion {run_id}", len(workers))
    hz.rename_origin_tab(tab_slug(mode, prompt))
    for worker, pane in zip(workers, panes):
        worker.pane_id = pane

    if fusion is not None:
        echo(f"launching fusion listener ({fusion.command})")
        hz.launch(fusion, launch_timeout)
        prompt_path = run_dir / "fusion.prompt.md"
        prompt_path.write_text(
            listen_prompt(workers, run_dir, fused_path, prompt, instruction, fusion_timeout))
        hz.submit(fusion.pane_id, prompt_path)
        fusion.status = "running"
        hz.manifest["fusion"] = vars(fusion)
        hz.save_manifest()

    for worker in workers:
        echo(f"launching {worker.name}: {worker.command}")
        hz.launch(worker, launch_timeout)
        answer_path = run_dir / f"{worker.name}.md"
        prompt_path = run_dir / f"{worker.name}.prompt.md"
        prompt_path.write_text(worker_prompt(mode, worker, workers, answer_path, prompt))
        hz.submit(worker.pane_id, prompt_path)
        worker.status = "running"
    hz.manifest["workers"] = {w.name: vars(w) for w in workers}
    hz.save_manifest()

    echo(f"waiting for {len(workers)} workers (timeout {worker_timeout:.0f}s each)...")
    for worker in workers:
        ok = hz.await_answer(worker, run_dir / f"{worker.name}.md", worker_timeout)
        echo(f"  {worker.name}: {worker.status} ({worker.seconds:.0f}s)")
        if not ok:
            echo(f"    tail:\n{worker.tail}")
    hz.manifest["workers"] = {w.name: vars(w) for w in workers}
    hz.save_manifest()

    survivors = [w for w in workers if w.status == "done"]
    if not survivors:
        hz.notify("herdr-fusion: run failed", "no worker produced an answer")
        echo(f"RESULT {run_dir}")
        return 1

    if mode == "opinion":
        parts = [f"# Opinion run — {run_id}\n\n**Prompt:** {prompt}\n"]
        for w in workers:
            answer = (run_dir / f"{w.name}.md")
            text = answer.read_text() if answer.is_file() else f"_({w.status})_"
            parts.append(f"\n---\n\n## [{w.role}] — {w.command} ({w.seconds:.0f}s)\n\n{text}")
        (run_dir / "comparison.md").write_text("\n".join(parts))
        hz.notify("herdr-fusion: opinion ready", str(run_dir / "comparison.md"))
        echo(f"RESULT {run_dir}")
        return 0 if len(survivors) == len(workers) else 2

    # fuse: the listener pane has been polling for the answers since launch and
    # merges them the moment both land — just wait for its fused.md.
    echo(f"waiting for fusion (timeout {fusion_timeout:.0f}s)...")
    ok = hz.await_answer(fusion, fused_path, fusion_timeout)
    hz.manifest["fusion"] = vars(fusion)
    hz.save_manifest()
    if not ok:
        hz.notify("herdr-fusion: fusion failed", f"worker answers intact in {run_dir}")
        echo(f"fusion: {fusion.status}\n    tail:\n{fusion.tail}")
        echo(f"RESULT {run_dir}")
        return 1
    echo(f"fusion: done ({fusion.seconds:.0f}s)")
    hz.notify("herdr-fusion: fusion ready", str(fused_path))
    echo(f"RESULT {run_dir}")
    return 0 if len(survivors) == len(workers) else 2
