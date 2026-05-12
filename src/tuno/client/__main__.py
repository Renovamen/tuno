"""Command-line entrypoint for the terminal client."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from tuno import __version__
from tuno.client.cli.update import cli_self_update
from tuno.client.tui.app import run_client


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the tuno terminal client.")
    parser.add_argument(
        "-s",
        "--server",
        dest="server_url",
        default=None,
        help="Optional ws:// or wss:// server URL to connect on startup.",
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("update", description="Update the installed tuno client.")

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.command == "update":
        cli_self_update(__version__)
        return

    run_client(server_url=args.server_url or "")


if __name__ == "__main__":
    main()
