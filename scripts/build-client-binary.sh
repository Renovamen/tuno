#!/usr/bin/env sh
set -eu

# Resolve paths relative to the repository root so the script can be launched
# from any working directory. The output paths can be overridden by environment
# variables when CI or local smoke tests need isolated build directories.
ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
DIST_PATH="${TUNO_DIST_PATH:-dist}"
WORK_PATH="${TUNO_BUILD_PATH:-build}"
SPEC_PATH="${TUNO_SPEC_PATH:-build}"
RELEASE_PATH="${TUNO_RELEASE_PATH:-release}"
ENTRYPOINT_PATH="${ROOT_DIR}/scripts/entrypoints/tuno_binary.py"
TUI_CSS_PATH="${ROOT_DIR}/src/tuno/client/tui/app.tcss"

# Fail early with a clear message when an external command is unavailable.
require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "error: required command not found: $1" >&2
    exit 1
  fi
}

# Fail early when a source/data file expected by the build has moved or is
# missing. This catches stale PyInstaller data paths before the expensive build.
require_file() {
  if [ ! -f "$1" ]; then
    echo "error: required file not found: $1" >&2
    exit 1
  fi
}

# Map the current OS and CPU architecture to the release artifact name used by
# install scripts and GitHub release assets.
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

# Write a checksum file next to the archive. macOS has shasum by default; Linux
# systems commonly provide sha256sum instead, so support both.
write_checksum() {
  archive="$1"
  checksum="$2"

  if command -v shasum >/dev/null 2>&1; then
    (cd "${RELEASE_PATH}" && shasum -a 256 "${archive}" > "${checksum}")
    return
  fi

  if command -v sha256sum >/dev/null 2>&1; then
    (cd "${RELEASE_PATH}" && sha256sum "${archive}" > "${checksum}")
    return
  fi

  echo "error: required command not found: shasum or sha256sum" >&2
  exit 1
}

# Move to the repo root and validate the local build prerequisites before
# asking PyInstaller to analyze the application.
cd "${ROOT_DIR}"
require_command python
require_command tar
require_file "${ENTRYPOINT_PATH}"
require_file "${TUI_CSS_PATH}"

# PyInstaller needs the certifi CA bundle bundled explicitly so HTTPS requests
# made by the frozen client can locate trusted roots consistently.
mkdir -p "${SPEC_PATH}"
CERTIFI_CACERT="$(python - <<'PY'
import certifi
print(certifi.where())
PY
)"
require_file "${CERTIFI_CACERT}"

# Build the standalone app directory. The Textual CSS file lives inside the
# tuno.client.tui package, so bundle it at the same package-relative path.
python -m PyInstaller \
  --clean \
  --name tuno \
  --distpath "${DIST_PATH}" \
  --workpath "${WORK_PATH}" \
  --specpath "${SPEC_PATH}" \
  --add-data "${TUI_CSS_PATH}:tuno/client/tui" \
  --add-data "${CERTIFI_CACERT}:certifi" \
  "${ENTRYPOINT_PATH}"

# Derive the platform-specific archive/checksum names after the build so the
# release asset matches what installers expect on this platform.
ARTIFACT="$(detect_artifact)"
ARCHIVE="${ARTIFACT}.tar.gz"
CHECKSUM="${ARTIFACT}.sha256"

# Package the PyInstaller app directory and write the matching checksum file
# into the local release directory.
mkdir -p "${RELEASE_PATH}"
tar -czf "${RELEASE_PATH}/${ARCHIVE}" -C "${DIST_PATH}" tuno
write_checksum "${ARCHIVE}" "${CHECKSUM}"

# Print the concrete paths a developer usually needs for local verification or
# upload to a release.
echo
echo "Built ${DIST_PATH}/tuno"
echo "Packaged ${RELEASE_PATH}/${ARCHIVE}"
echo "Wrote ${RELEASE_PATH}/${CHECKSUM}"
