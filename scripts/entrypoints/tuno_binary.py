"""PyInstaller entrypoint for the standalone Tuno client binary."""

from __future__ import annotations

from tuno.client.app import main

if __name__ == "__main__":
    main()
