from pathlib import Path

import pytest

from herdr_fusion import harness
from herdr_fusion.harness import (
    Worker, deep_get, fill, listen_prompt, load_config, merge_prompt, tab_slug, worker_prompt,
)

WORKERS = [
    Worker("claude", "claude --model opus"),
    Worker("gpt", "cursor-agent --model gpt-5.2"),
]


def test_fill_interpolates_and_blanks_unknown(tmp_path, monkeypatch):
    tpl = tmp_path / "t.md"
    tpl.write_text("hi {{NAME}} / {{MISSING}}!")
    monkeypatch.setattr(harness, "PROMPTS", tmp_path)
    assert fill("t.md", {"NAME": "noah"}) == "hi noah / !"


def test_deep_get_nested():
    obj = {"result": {"pane": {"pane_id": "w1:p3"}}, "ok": True}
    assert deep_get(obj, "pane_id") == "w1:p3"
    assert deep_get(obj, "nope") is None


def test_load_config_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    cfg = load_config()
    assert cfg["fusion"]["runner"] == "claude"
    assert set(cfg["workers"]) == {"claude", "gpt", "grok"}


def test_load_config_workers_replace_defaults(tmp_path):
    p = tmp_path / "fusion.toml"
    p.write_text('[workers.a]\ncommand = "x"\n')
    cfg = load_config(str(p))
    assert list(cfg["workers"]) == ["a"]          # file set replaces defaults
    assert cfg["fusion"]["runner"] == "claude"    # fusion table still merges


def test_worker_prompt_has_collision_rules_and_answer_path(tmp_path):
    out = worker_prompt("fuse", WORKERS[0], WORKERS, tmp_path / "claude.md", "do the thing")
    assert "CLAUDE" in out
    assert "GPT (cursor-agent --model gpt-5.2)" in out   # peers listed
    assert str(tmp_path / "claude.md") in out
    assert "NEVER write to a bare path" in out
    assert "do the thing" in out


def test_opinion_prompt_is_read_only(tmp_path):
    out = worker_prompt("opinion", WORKERS[1], WORKERS, tmp_path / "gpt.md", "q?")
    assert "READ-ONLY" in out
    assert str(tmp_path / "gpt.md") in out


def test_merge_prompt_inlines_and_truncates(tmp_path):
    (tmp_path / "claude.md").write_text("A" * (harness.HANDOFF_MAX + 100))
    (tmp_path / "gpt.md").write_text("short answer")
    out = merge_prompt(WORKERS, tmp_path, tmp_path / "fused.md", "orig request", None)
    assert "truncated at 60000 chars" in out
    assert "short answer" in out
    assert "[CLAUDE]" in out and "[GPT]" in out
    assert str(tmp_path / "fused.md") in out
    assert "do not simply concatenate" in out  # default instruction applied


def test_listen_prompt_polls_paths_without_inlining(tmp_path):
    # Listener is spawned BEFORE workers finish: it must name the paths to poll,
    # carry a wait budget, and NOT inline answer text (there is none yet).
    out = listen_prompt(WORKERS, tmp_path, tmp_path / "fused.md", "orig request", None, 900)
    assert str(tmp_path / "claude.md") in out and str(tmp_path / "gpt.md") in out
    assert "900" in out                      # wait budget interpolated
    assert "orig request" in out
    assert str(tmp_path / "fused.md") in out
    assert "{{" not in out                   # every placeholder filled


def test_tab_slug_prefixes_mode_and_truncates():
    assert tab_slug("fuse", "rate limiter design") == "fuse: rate limiter design"
    long = tab_slug("opinion", "should we migrate from npm to pnpm and why exactly", limit=20)
    assert long.startswith("opinion: ") and long.endswith("…") and len(long) < 40
    assert tab_slug("fuse", "") == "fuse"       # empty prompt → bare mode, no trailing ': '


def test_merge_prompt_custom_instruction(tmp_path):
    (tmp_path / "claude.md").write_text("x")
    (tmp_path / "gpt.md").write_text("y")
    out = merge_prompt(WORKERS, tmp_path, tmp_path / "fused.md", "req", "pick the funnier one")
    assert "pick the funnier one" in out
    assert "do not simply concatenate" not in out
