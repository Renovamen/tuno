#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_VERSION_FILE = REPO_ROOT / "src" / "tuno" / "__init__.py"
PACKAGE_JSON_FILE = REPO_ROOT / "package.json"
VERSION_RE = re.compile(r'^__version__ = "(?P<version>[^"]+)"$', re.MULTILINE)
SIMPLE_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def read_current_version() -> str:
    match = VERSION_RE.search(PYTHON_VERSION_FILE.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit(f"Could not find __version__ in {PYTHON_VERSION_FILE}")
    return match.group("version")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bump tuno version and keep package metadata in sync."
    )
    parser.add_argument(
        "target",
        help="One of: major, minor, patch, or an explicit version like 0.1.2",
    )
    parser.add_argument(
        "--no-lock",
        action="store_true",
        help="Skip `uv lock` after updating the version files.",
    )
    return parser.parse_args()


def resolve_next_version(current: str, target: str) -> str:
    if SIMPLE_VERSION_RE.fullmatch(target):
        return target

    try:
        major, minor, patch = (int(part) for part in current.split("."))
    except ValueError as exc:
        raise SystemExit(
            f"Current version `{current}` is not in `major.minor.patch` form."
        ) from exc

    if target == "major":
        return f"{major + 1}.0.0"
    if target == "minor":
        return f"{major}.{minor + 1}.0"
    if target == "patch":
        return f"{major}.{minor}.{patch + 1}"

    raise SystemExit(
        "Target must be `major`, `minor`, `patch`, or an explicit version like `0.1.2`."
    )


def write_python_version(version: str) -> None:
    updated, replacements = VERSION_RE.subn(
        f'__version__ = "{version}"',
        PYTHON_VERSION_FILE.read_text(encoding="utf-8"),
    )

    if replacements != 1:
        raise SystemExit(f"Expected one __version__ assignment in {PYTHON_VERSION_FILE}")

    PYTHON_VERSION_FILE.write_text(updated, encoding="utf-8")


def write_package_json(version: str) -> None:
    package_json = json.loads(PACKAGE_JSON_FILE.read_text(encoding="utf-8"))
    package_json["version"] = version
    PACKAGE_JSON_FILE.write_text(f"{json.dumps(package_json, indent=4)}\n", encoding="utf-8")


def refresh_lockfile() -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("`uv` is required to refresh uv.lock. Re-run with `--no-lock` if needed.")

    subprocess.run([uv, "lock"], cwd=REPO_ROOT, check=True)


def main() -> None:
    args = parse_args()
    current = read_current_version()
    next_version = resolve_next_version(current, args.target)

    write_python_version(next_version)
    write_package_json(next_version)

    if not args.no_lock:
        refresh_lockfile()

    print(f"{current} -> {next_version}")


if __name__ == "__main__":
    main()
