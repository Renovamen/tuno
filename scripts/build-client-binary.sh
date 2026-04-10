#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
DIST_PATH="${TUNO_DIST_PATH:-dist}"
WORK_PATH="${TUNO_BUILD_PATH:-build}"
SPEC_PATH="${TUNO_SPEC_PATH:-build}"

cd "${ROOT_DIR}"
mkdir -p "${SPEC_PATH}"

python -m PyInstaller \
  --clean \
  --name tuno \
  --distpath "${DIST_PATH}" \
  --workpath "${WORK_PATH}" \
  --specpath "${SPEC_PATH}" \
  --add-data "${ROOT_DIR}/src/tuno/client/app.tcss:tuno/client" \
  scripts/entrypoints/tuno_binary.py
