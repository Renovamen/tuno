"""PyInstaller entrypoint for the standalone Tuno client binary."""

from __future__ import annotations

from tuno.client.__main__ import app

if __name__ == "__main__":
    app()
