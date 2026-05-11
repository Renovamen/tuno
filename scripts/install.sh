#!/usr/bin/env sh
set -eu

# This script downloads the matching macOS/Linux release asset into
# ~/.local/share/tuno and writes a tuno command wrapper into ~/.local/bin
# by default.

REPO="${TUNO_REPO:-Renovamen/tuno}"
VERSION="${TUNO_VERSION:-latest}"
INSTALL_DIR="${HOME}/.local/bin"
APP_DIR="${HOME}/.local/share/tuno"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT HUP INT TERM

# Exit early when a required external tool is missing.
require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "error: required command not found: $1" >&2
    exit 1
  fi
}

# Return the home directory that owns a shell startup file.
# zsh startup files may live under ZDOTDIR instead of HOME.
print_home_for_script() {
  case "$1" in
    .zsh*)
      if [ -n "${ZDOTDIR:-}" ]; then
        echo "${ZDOTDIR}"
      else
        echo "${HOME}"
      fi
      ;;
    *)
      echo "${HOME}"
      ;;
  esac
}

# Add the managed PATH block to a startup file if it is not already present.
# Echo the file path only when this function writes a new block.
append_tuno_path_block() {
  target="$1"

  if grep -F 'export PATH="$HOME/.local/bin:$PATH"' "${target}" >/dev/null 2>&1; then
    return 0
  fi

  if grep -F '# tuno' "${target}" >/dev/null 2>&1 && \
     grep -F '# tuno end' "${target}" >/dev/null 2>&1; then
    return 0
  fi

  mkdir -p "$(dirname "${target}")"
  if [ ! -f "${target}" ]; then
    : > "${target}"
  fi

  printf '\n# tuno\nexport PATH="$HOME/.local/bin:$PATH"\n# tuno end\n' >> "${target}"
  echo "${target}"
}

# Choose the best startup file from an ordered list.
# Prefer an existing file; otherwise return the first candidate path.
choose_rcfile_target() {
  rcfiles="$1"

  for rcfile_relative in ${rcfiles}; do
    home_dir="$(print_home_for_script "${rcfile_relative}")"
    rcfile="${home_dir}/${rcfile_relative}"

    if [ -f "${rcfile}" ]; then
      echo "${rcfile}"
      return 0
    fi
  done

  set -- ${rcfiles}
  home_dir="$(print_home_for_script "$1")"
  echo "${home_dir}/$1"
}

# Add the managed PATH block to one selected startup file from a candidate list.
# If none of the candidates exist, create the first candidate and write it there.
add_tuno_path_to_rcfiles() {
  append_tuno_path_block "$(choose_rcfile_target "$1")"
}

# Add the managed PATH block to every existing startup file in a candidate list.
# Unlike add_tuno_path_to_rcfiles, this never creates missing candidates.
# This avoids creating extra bash files while still updating files users already use.
add_tuno_path_to_existing_rcfiles() {
  rcfiles="$1"

  for rcfile_relative in ${rcfiles}; do
    home_dir="$(print_home_for_script "${rcfile_relative}")"
    rcfile="${home_dir}/${rcfile_relative}"

    if [ -f "${rcfile}" ]; then
      append_tuno_path_block "${rcfile}"
    fi
  done
}

# Remove empty lines and duplicate paths from a newline-separated list.
dedupe_lines() {
  printf '%s\n' "$1" | sed '/^$/d' | awk '!seen[$0]++'
}

# Quote a path so it can be embedded safely in the generated sh wrapper.
quote_sh() {
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

# Map the current OS and CPU architecture to the release asset name.
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

# Build the tarball URL for either the latest release or a pinned TUNO_VERSION.
download_url() {
  artifact="$1"
  if [ "${VERSION}" = "latest" ]; then
    echo "https://github.com/${REPO}/releases/latest/download/${artifact}.tar.gz"
  else
    echo "https://github.com/${REPO}/releases/download/${VERSION}/${artifact}.tar.gz"
  fi
}

# Build the checksum URL that matches the selected release tarball.
checksum_url() {
  artifact="$1"
  if [ "${VERSION}" = "latest" ]; then
    echo "https://github.com/${REPO}/releases/latest/download/${artifact}.sha256"
  else
    echo "https://github.com/${REPO}/releases/download/${VERSION}/${artifact}.sha256"
  fi
}

# Verify the downloaded archive against the release-provided checksum file.
# Prefer shasum for macOS, fall back to sha256sum for common Linux installs.
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

  # Keep the installer usable on minimal systems, but make the skipped check explicit.
  echo "warning: neither shasum nor sha256sum is available; skipping checksum verification" >&2
  echo "downloaded archive: ${archive_file}" >&2
  echo "expected checksum file: ${artifact}.sha256" >&2
}

# Check for the external tools needed by the main install flow before doing any
# network or filesystem work.
require_command curl
require_command tar

# Resolve the platform-specific release asset names used for the archive and
# checksum downloads.
ARTIFACT="$(detect_artifact)"
ARCHIVE="${ARTIFACT}.tar.gz"
CHECKSUM="${ARTIFACT}.sha256"

echo "Installing Tuno client binary (${ARTIFACT}) from ${REPO} ${VERSION}."
echo "Warning: install only from trusted release assets."

# Download the release archive and its checksum into the temporary directory,
# then verify the archive before extracting it.
curl -fsSL "$(download_url "${ARTIFACT}")" -o "${TMP_DIR}/${ARCHIVE}"
curl -fsSL "$(checksum_url "${ARTIFACT}")" -o "${TMP_DIR}/${CHECKSUM}"
verify_checksum "${ARTIFACT}" "${CHECKSUM}" "${ARCHIVE}"

# Extract the release bundle and make sure it contains the expected executable.
tar -xzf "${TMP_DIR}/${ARCHIVE}" -C "${TMP_DIR}"

if [ ! -x "${TMP_DIR}/tuno/tuno" ]; then
  echo "error: release archive did not contain a tuno app directory" >&2
  exit 1
fi

# Replace the managed app directory with the extracted app, then install a small
# command wrapper into INSTALL_DIR so users can run `tuno` from PATH.
mkdir -p "${INSTALL_DIR}"
rm -rf "${APP_DIR:?}"
mkdir -p "$(dirname "${APP_DIR}")"
cp -R "${TMP_DIR}/tuno" "${APP_DIR}"
TUNO_BIN="$(quote_sh "${APP_DIR}/tuno")"
cat > "${INSTALL_DIR}/tuno" <<EOF
#!/usr/bin/env sh
exec ${TUNO_BIN} "\$@"
EOF
chmod 0755 "${INSTALL_DIR}/tuno"

# Print the installed paths and the first command users should run after install.
echo
echo "Installed tuno app to ${APP_DIR}"
echo "Installed tuno command to ${INSTALL_DIR}/tuno"
echo
echo "Run: tuno"
echo "Then connect inside the TUI:"
echo "  /server ws://<server-host>:<port>"
echo "  /server wss://<your-worker>.<subdomain>.workers.dev"

# If ~/.local/bin is not already on PATH, add it to common shell startup files.
case ":${PATH}:" in
  *":${INSTALL_DIR}:"*) ;;
  *)
    written_rcfiles="$(
      add_tuno_path_to_rcfiles ".profile"
      add_tuno_path_to_existing_rcfiles ".bashrc .bash_profile .bash_login"
      add_tuno_path_to_rcfiles ".zshrc .zshenv"
    )"
    written_rcfiles="$(dedupe_lines "${written_rcfiles}")"

    if [ -n "${written_rcfiles}" ]; then
      echo
      echo "Added ~/.local/bin PATH setup to:"
      printf '%s\n' "${written_rcfiles}" | sed 's/^/  /'
      echo "Restart your shell to use tuno."
    else
      echo
      echo "~/.local/bin is not on PATH for this shell. Restart your shell if you already have the tuno PATH block in your rc files."
    fi
    ;;
esac
