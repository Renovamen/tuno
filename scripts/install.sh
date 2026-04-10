#!/usr/bin/env sh
set -eu

# This script downloads the matching macOS/Linux release asset into
# ~/.local/share/tuno and writes a tuno command wrapper into ~/.local/bin
# by default. Override those paths with TUNO_APP_DIR and TUNO_INSTALL_DIR.

REPO="${TUNO_REPO:-Renovamen/tuno}"
VERSION="${TUNO_VERSION:-latest}"
INSTALL_DIR="${TUNO_INSTALL_DIR:-${HOME}/.local/bin}"
APP_DIR="${TUNO_APP_DIR:-${HOME}/.local/share/tuno}"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT HUP INT TERM

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "error: required command not found: $1" >&2
    exit 1
  fi
}

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
      echo "error: unsupported platform: ${os} ${arch}" >&2
      exit 1
      ;;
  esac
}

download_url() {
  artifact="$1"
  if [ "${VERSION}" = "latest" ]; then
    echo "https://github.com/${REPO}/releases/latest/download/${artifact}.tar.gz"
  else
    echo "https://github.com/${REPO}/releases/download/${VERSION}/${artifact}.tar.gz"
  fi
}

checksum_url() {
  artifact="$1"
  if [ "${VERSION}" = "latest" ]; then
    echo "https://github.com/${REPO}/releases/latest/download/${artifact}.sha256"
  else
    echo "https://github.com/${REPO}/releases/download/${VERSION}/${artifact}.sha256"
  fi
}

verify_checksum() {
  artifact="$1"
  checksum_file="$2"
  archive_file="$3"

  if command -v shasum >/dev/null 2>&1; then
    (cd "${TMP_DIR}" && shasum -a 256 -c "${checksum_file}")
    return
  fi

  if command -v sha256sum >/dev/null 2>&1; then
    (cd "${TMP_DIR}" && sha256sum -c "${checksum_file}")
    return
  fi

  echo "warning: neither shasum nor sha256sum is available; skipping checksum verification" >&2
  echo "downloaded archive: ${archive_file}" >&2
  echo "expected checksum file: ${artifact}.sha256" >&2
}

require_command curl
require_command tar

ARTIFACT="$(detect_artifact)"
ARCHIVE="${ARTIFACT}.tar.gz"
CHECKSUM="${ARTIFACT}.sha256"

echo "Installing tUNO client binary (${ARTIFACT}) from ${REPO} ${VERSION}."
echo "Warning: install only from trusted release assets."

curl -fsSL "$(download_url "${ARTIFACT}")" -o "${TMP_DIR}/${ARCHIVE}"
curl -fsSL "$(checksum_url "${ARTIFACT}")" -o "${TMP_DIR}/${CHECKSUM}"
verify_checksum "${ARTIFACT}" "${CHECKSUM}" "${ARCHIVE}"

tar -xzf "${TMP_DIR}/${ARCHIVE}" -C "${TMP_DIR}"

if [ ! -x "${TMP_DIR}/tuno/tuno" ]; then
  echo "error: release archive did not contain a tuno app directory" >&2
  exit 1
fi

mkdir -p "${INSTALL_DIR}"
rm -rf "${APP_DIR}"
mkdir -p "$(dirname "${APP_DIR}")"
cp -R "${TMP_DIR}/tuno" "${APP_DIR}"
cat > "${INSTALL_DIR}/tuno" <<EOF
#!/usr/bin/env sh
exec "${APP_DIR}/tuno" "\$@"
EOF
chmod 0755 "${INSTALL_DIR}/tuno"

echo
echo "Installed tuno app to ${APP_DIR}"
echo "Installed tuno command to ${INSTALL_DIR}/tuno"
echo "Run: tuno ws://server-host:8765"
case ":${PATH}:" in
  *":${INSTALL_DIR}:"*) ;;
  *) echo "If '${INSTALL_DIR}' is not on your PATH, add it before running tuno." ;;
esac
