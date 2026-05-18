"""Self-update command implementation for the tuno client CLI."""

from __future__ import annotations

import contextlib
import os
import subprocess
import tempfile
from urllib.request import Request, urlopen

from tuno.client.tls import build_client_ssl_context
from tuno.client.updates import fetch_latest_release_version, is_newer_version, normalize_version

INSTALL_SCRIPT_URL = "https://raw.githubusercontent.com/Renovamen/tuno/HEAD/scripts/install.sh"


def fetch_install_script(timeout: float = 10.0) -> str:
    """Download the installer script used by `tuno update`."""
    request = Request(INSTALL_SCRIPT_URL, headers={"User-Agent": "tuno-client"})
    with urlopen(request, timeout=timeout, context=build_client_ssl_context()) as response:
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


def cli_self_update(
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
