#!/usr/bin/env sh
set -eu

TARGET="${1:-patch}"

TAG="$(uv run python scripts/bump_version.py "${TARGET}" --print-tag)"

if [ -z "${TAG}" ]; then
  echo "error: bump script did not return a release tag" >&2
  exit 1
fi

git add package.json uv.lock src/tuno/__init__.py
git commit -m "chore: ${TAG}"

git tag "${TAG}"
git push
git push origin "${TAG}"
