"""Uninstall command implementation for the tuno client CLI."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

import typer


def _remove_path(path: Path) -> bool:
    """Remove a file, symlink, or directory if it exists."""
    if path.is_symlink() or path.is_file():
        path.unlink()
        return True

    if path.is_dir():
        shutil.rmtree(path)
        return True

    return False


def _display_path(path: Path, home: Path) -> str:
    try:
        return f"~/{path.relative_to(home)}"
    except ValueError:
        return str(path)


def _confirm_delete(prompt: str) -> bool:
    return typer.confirm(prompt, default=False)


def cli_uninstall(
    *,
    home: Path | None = None,
    confirm: Callable[[str], bool] | None = None,
    echo: Callable[[str], None] = typer.echo,
) -> bool:
    """Remove files installed by the README uninstall command."""
    home = home or Path.home()
    install_paths = [
        home / ".local" / "share" / "tuno",
        home / ".local" / "bin" / "tuno",
    ]
    config_path = home / ".config" / "tuno"
    if confirm is None:
        confirm = _confirm_delete

    removed_any = False

    for path in install_paths:
        if _remove_path(path):
            removed_any = True
            echo(f"Removed {_display_path(path, home)}")

    if confirm(f"Delete configuration at {_display_path(config_path, home)}?"):
        if _remove_path(config_path):
            removed_any = True
            echo(f"Removed {_display_path(config_path, home)}")
        else:
            echo(f"No configuration found at {_display_path(config_path, home)}")
    else:
        echo(f"Kept configuration at {_display_path(config_path, home)}")

    if not removed_any:
        echo("No tuno installation files were found.")

    return removed_any
