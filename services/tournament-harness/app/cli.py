"""Operator CLI surface for tournament harness (CD-05, CD-07).

Subcommands:
  run <yaml_path> [--allow-dirty]
      Launch a tournament via the orchestrator. Refuses to run on a dirty git
      tree unless --allow-dirty is set.

  leaderboard list [--tournament-id ID] [--top N] [--by COL] [--where 'col=val AND col=val']
      Query the leaderboard. The --where clause goes through a safe parser
      (queries.parse_where) before binding to parameterised SQL.

  export-snapshot <tournament_id> [--output PATH]
      Write the JSON snapshot artifact (D-18) downstream phases consume.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from app.config.settings import get_settings


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def cmd_run(args: argparse.Namespace) -> int:
    from app.orchestrator.launcher import run_tournament

    summary = run_tournament(args.yaml_path, allow_dirty=args.allow_dirty)
    print(json.dumps(summary, indent=2, default=str))
    return 0


def cmd_leaderboard_list(args: argparse.Namespace) -> int:
    from app.leaderboard.queries import run_query

    settings = get_settings()
    rows = run_query(
        db_path=settings.leaderboard_db_path,
        tournament_id=args.tournament_id,
        top=args.top,
        by=args.by,
        where=args.where or "",
    )
    print(json.dumps(rows, indent=2, default=str))
    return 0


def cmd_open_pr(args: argparse.Namespace) -> int:
    # Lazy import: open_pr pulls numpy / TF (via predict_fn → ml-retraining).
    from app.pr.open_pr import run_open_pr

    return run_open_pr(
        args.tournament_id,
        allow_dirty=args.allow_dirty,
        dry_run=args.dry_run,
    )


def cmd_reproduce(args: argparse.Namespace) -> int:
    # Lazy import — pulls run_open_pr → numpy/TF chain.
    from app.pr.reproduce import run_reproduce

    return run_reproduce(
        args.tournament_id,
        git_sha_expected=args.git_sha,
        force=args.force,
    )


def cmd_export_snapshot(args: argparse.Namespace) -> int:
    from app.leaderboard.snapshot import export_snapshot

    settings = get_settings()
    out = (
        Path(args.output)
        if args.output
        else (Path(settings.snapshots_dir) / f"{args.tournament_id}.json")
    )
    snap = export_snapshot(settings.leaderboard_db_path, args.tournament_id, out)
    print(
        json.dumps(
            {
                "snapshot_path": str(out),
                "n_rows": snap["summary"]["n_rows"],
                "n_success": snap["summary"]["n_success"],
                "n_failed": snap["summary"]["n_failed"],
            },
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Launch a tournament from YAML config")
    p_run.add_argument("yaml_path", help="Path to tournament.yaml")
    p_run.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow running on a dirty git tree (development override)",
    )
    p_run.set_defaults(func=cmd_run)

    p_lb = sub.add_parser("leaderboard", help="Leaderboard utilities")
    sub_lb = p_lb.add_subparsers(dest="lb_cmd", required=True)
    p_lb_list = sub_lb.add_parser("list", help="List leaderboard rows")
    p_lb_list.add_argument("--tournament-id")
    p_lb_list.add_argument("--top", type=int, default=10)
    p_lb_list.add_argument(
        "--by",
        default="dsr",
        help=(
            "Order column (allowlisted: r2_returns, dir_acc_corrected, "
            "oos_sharpe, psr, dsr, cpcv_dsr, train_seconds, created_at)"
        ),
    )
    p_lb_list.add_argument(
        "--where",
        default="",
        help="Safe DSL: 'symbol=SOL AND architecture=gru'",
    )
    p_lb_list.set_defaults(func=cmd_leaderboard_list)

    p_snap = sub.add_parser("export-snapshot", help="Write tournament snapshot JSON")
    p_snap.add_argument("tournament_id")
    p_snap.add_argument("--output", help="Override default snapshot path")
    p_snap.set_defaults(func=cmd_export_snapshot)

    p_pr = sub.add_parser(
        "open-pr",
        help="Build ensemble + significance + draft PR for a tournament",
    )
    p_pr.add_argument("tournament_id")
    p_pr.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow dirty tree (mirrors `tournament run`)",
    )
    p_pr.add_argument(
        "--dry-run",
        action="store_true",
        help="Write artifacts but do NOT invoke gh pr create",
    )
    p_pr.set_defaults(func=cmd_open_pr)

    p_repro = sub.add_parser(
        "reproduce",
        help="Re-derive significance from snapshot at the same git_sha (D-12)",
    )
    p_repro.add_argument("tournament_id")
    p_repro.add_argument(
        "--git-sha",
        required=True,
        help="Expected HEAD; refuses with exit 3 if HEAD does not match",
    )
    p_repro.add_argument(
        "--force",
        action="store_true",
        help="Drop existing temp DB before re-running (CD-06 forensic)",
    )
    p_repro.set_defaults(func=cmd_reproduce)

    return parser


def main(argv=None) -> int:
    _setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
