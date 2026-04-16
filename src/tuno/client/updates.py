"""Update-check helpers for the terminal client."""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import tempfile
from urllib.request import Request, urlopen

LATEST_RELEASE_URL = "https://api.github.com/repos/Renovamen/tuno/releases/latest"
INSTALL_README_URL = "https://github.com/Renovamen/tuno?tab=readme-ov-file#install"
INSTALL_SCRIPT_URL = "https://raw.githubusercontent.com/Renovamen/tuno/HEAD/scripts/install.sh"


def fetch_latest_release_version(timeout: float = 5.0) -> str | None:
    """Fetch the latest GitHub release tag and normalize it to a version string."""
    request = Request(
        LATEST_RELEASE_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "tuno-client",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)

    tag = payload.get("tag_name")
    if not tag:
        return None

    return normalize_version(tag)


def normalize_version(version: str) -> str:
    """Strip a leading v/V prefix from a semantic version string."""
    return version.lstrip("vV")


def is_newer_version(latest: str, current: str) -> bool:
    """Return whether the fetched release version is newer than the local one."""
    return _version_key(normalize_version(latest)) > _version_key(normalize_version(current))


def build_update_notice(latest: str) -> str:
    """Build the Rich markup text shown when a newer version is available."""
    clean = normalize_version(latest)
    return f"Update available: v{clean}. Run: [bold]tuno update[/]"


def fetch_install_script(timeout: float = 10.0) -> str:
    """Download the installer script used by `tuno update`."""
    request = Request(INSTALL_SCRIPT_URL, headers={"User-Agent": "tuno-client"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def run_install_script(script: str) -> None:
    """Execute the fetched installer script in a temporary shell file."""
    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        handle.write(script)
        script_path = handle.name

    try:
        subprocess.run(["/bin/sh", script_path], check=True, env=os.environ.copy())
    finally:
        with contextlib.suppress(OSError):
            os.unlink(script_path)


def perform_self_update(
    current_version: str,
    *,
    fetch_latest_version=fetch_latest_release_version,
    fetch_install_script_fn=fetch_install_script,
    run_install_script_fn=run_install_script,
    echo=print,
) -> bool:
    """Check for a newer release and run the installer when one exists."""
    current = normalize_version(current_version)

    try:
        latest = fetch_latest_version()
    except Exception as exc:
        echo(f"Failed to check for updates: {exc}")
        return False

    if not latest or not is_newer_version(latest, current):
        echo(f"tuno v{current} is already up to date.")
        return False

    echo(f"Updating tuno from v{current} to v{latest}...")

    try:
        script = fetch_install_script_fn()
        run_install_script_fn(script)
    except Exception as exc:
        echo(f"Update failed: {exc}")
        return False

    echo("Update installed. Restart tuno to use the new version.")
    return True


def _version_key(version: str) -> tuple:
    parts = []

    for token in re.split(r"[.\-+]", version):
        if token.isdigit():
            parts.append((0, int(token)))
        elif token:
            parts.append((1, token))

    return tuple(parts)
