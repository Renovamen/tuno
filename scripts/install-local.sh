#!/usr/bin/env sh
set -eu

# Simulate scripts/install.sh against a local macOS/Linux release tarball.
# Usage:
#   ./scripts/install-local.sh [path/to/tuno-*.tar.gz]
#
# Defaults:
#   ./release/tuno-macos-arm64.tar.gz on Apple Silicon
#   ./release/tuno-macos-x86_64.tar.gz on Intel macOS
#   ./release/tuno-linux-x86_64.tar.gz on Linux x86_64

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT HUP INT TERM

detect_local_artifact() {
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

ARTIFACT="$(detect_local_artifact)"
ARCHIVE_PATH="${1:-${ROOT_DIR}/release/${ARTIFACT}.tar.gz}"
CHECKSUM_PATH="${ARCHIVE_PATH%.tar.gz}.sha256"

if [ ! -f "${ARCHIVE_PATH}" ]; then
  echo "error: local release archive not found: ${ARCHIVE_PATH}" >&2
  echo "build one first:" >&2
  echo "  ./scripts/build-client-binary.sh" >&2
  echo "expected output:" >&2
  echo "  release/${ARTIFACT}.tar.gz" >&2
  echo "  release/${ARTIFACT}.sha256" >&2
  exit 1
fi

if [ ! -f "${CHECKSUM_PATH}" ]; then
  echo "error: checksum file not found: ${CHECKSUM_PATH}" >&2
  echo "re-run ./scripts/build-client-binary.sh to generate the archive and checksum together." >&2
  exit 1
fi

mkdir -p "${TMP_DIR}/bin"
# Replace curl with a local-file shim so install.sh can exercise the real install flow.
cat > "${TMP_DIR}/bin/curl" <<EOF
#!/usr/bin/env sh
set -eu

out=""
url=""
while [ "\$#" -gt 0 ]; do
  case "\$1" in
    -o)
      shift
      out="\$1"
      ;;
    -*)
      ;;
    *)
      url="\$1"
      ;;
  esac
  shift
done

case "\${url}" in
  *.tar.gz)
    cp "${ARCHIVE_PATH}" "\${out}"
    ;;
  *.sha256)
    cp "${CHECKSUM_PATH}" "\${out}"
    ;;
  *)
    echo "unexpected URL requested by install.sh: \${url}" >&2
    exit 1
    ;;
esac
EOF
chmod +x "${TMP_DIR}/bin/curl"

PATH="${TMP_DIR}/bin:${PATH}" \
TUNO_REPO="${TUNO_REPO:-local/tuno}" \
TUNO_VERSION="${TUNO_VERSION:-local}" \
"${ROOT_DIR}/scripts/install.sh"
