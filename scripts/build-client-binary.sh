#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
DIST_PATH="${TUNO_DIST_PATH:-dist}"
WORK_PATH="${TUNO_BUILD_PATH:-build}"
SPEC_PATH="${TUNO_SPEC_PATH:-build}"
RELEASE_PATH="${TUNO_RELEASE_PATH:-release}"

detect_artifact() {
  os="$(uname -s)"
  arch="$(uname -m)"

  case "${os}:${arch}" in
    Darwin:arm64)
      echo "tuno-macos-arm64"
      ;;
    Darwin:x86_64)
      echo "tuno-macos-x86_64"
      ;;
    Linux:x86_64)
      echo "tuno-linux-x86_64"
      ;;
    *)
      echo "error: unsupported build platform: ${os} ${arch}" >&2
      exit 1
      ;;
  esac
}

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

ARTIFACT="$(detect_artifact)"
ARCHIVE="${ARTIFACT}.tar.gz"
CHECKSUM="${ARTIFACT}.sha256"

mkdir -p "${RELEASE_PATH}"
tar -czf "${RELEASE_PATH}/${ARCHIVE}" -C "${DIST_PATH}" tuno
(cd "${RELEASE_PATH}" && shasum -a 256 "${ARCHIVE}" > "${CHECKSUM}")

echo
echo "Built ${DIST_PATH}/tuno"
echo "Packaged ${RELEASE_PATH}/${ARCHIVE}"
echo "Wrote ${RELEASE_PATH}/${CHECKSUM}"
