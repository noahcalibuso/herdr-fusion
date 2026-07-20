"""herdr-fusion: opinion (side-by-side) and fuse (converge) commands."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import harness


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("prompt", help="the request to fan out")
    common.add_argument("--workers", help="comma-separated worker slots (default: all configured)")
    common.add_argument("--config", help="path to fusion.toml")
    common.add_argument("--session", default=os.environ.get("HERDR_SESSION") or "default",
                        help="herdr session name (default: $HERDR_SESSION or 'default')")
    common.add_argument("--cwd", type=Path, help="working directory for the agents (default: current)")
    common.add_argument("--timeout", type=float, default=1200, help="per-worker seconds (default 1200)")
    common.add_argument("--launch-timeout", type=float, default=120,
                        help="seconds for an agent TUI to reach idle (default 120)")
    common.add_argument("--no-notify", action="store_true", help="skip herdr notifications")

    ap = argparse.ArgumentParser(prog="herdr-fusion",
                                 description="fusion-harness on herdr panes: side-by-side fan-out, then convergence.")
    sub = ap.add_subparsers(dest="mode", required=True)
    sub.add_parser("opinion", parents=[common],
                   help="fan out read-only, collect a side-by-side comparison.md")
    fuse = sub.add_parser("fuse", parents=[common],
                          help="fan out with full tools, then converge into fused.md")
    fuse.add_argument("--instruction", help="override the default fusion/merge instruction")
    fuse.add_argument("--fusion", help="worker slot whose CLI runs the merge (default: [fusion].runner)")
    fuse.add_argument("--fusion-timeout", type=float, default=1800,
                      help="seconds for the merge step (default 1800)")

    args = ap.parse_args(argv)
    cfg = harness.load_config(args.config)
    try:
        return harness.run(
            mode=args.mode,
            prompt=args.prompt,
            cfg=cfg,
            worker_names=args.workers.split(",") if args.workers else None,
            fusion_runner=getattr(args, "fusion", None),
            session=args.session,
            cwd=args.cwd,
            instruction=getattr(args, "instruction", None),
            worker_timeout=args.timeout,
            launch_timeout=args.launch_timeout,
            fusion_timeout=getattr(args, "fusion_timeout", 1800),
            notify=not args.no_notify,
        )
    except harness.HerdrError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
