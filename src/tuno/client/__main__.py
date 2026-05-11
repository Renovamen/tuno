"""`python -m tuno.client` to launch the terminal client."""

from __future__ import annotations

from tuno.client.tui.app import main as run_tui_client


def main() -> None:
    run_tui_client()


if __name__ == "__main__":
    main()
