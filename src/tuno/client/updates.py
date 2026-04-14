"""Update-check helpers for the terminal client."""

from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen

LATEST_RELEASE_URL = "https://api.github.com/repos/Renovamen/tuno/releases/latest"
INSTALL_README_URL = "https://github.com/Renovamen/tuno?tab=readme-ov-file#install"


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
    return (
        f"Update available: v{clean}. See [link={INSTALL_README_URL}]install instructions[/link]."
    )


def _version_key(version: str) -> tuple:
    parts = []

    for token in re.split(r"[.\-+]", version):
        if token.isdigit():
            parts.append((0, int(token)))
        elif token:
            parts.append((1, token))

    return tuple(parts)
