# Tuno Development

## Environment

```bash
conda create -n tuno python=3.12
conda activate tuno

python -m pip install -e ".[dev]"
export PYTHONPATH=src
```

For client binary builds, install the build extra:

```bash
python -m pip install -e ".[build]"
```

## Run Locally

Start the server:

```bash
python -m tuno.server.local --host 127.0.0.1 --port 8765
```

Start the client:

```bash
python -m tuno.client.app ws://127.0.0.1:8765
```

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m ruff check .
PYTHONPATH=src python -m ruff format --check .
```

## Lint

```bash
python -m ruff format .
```

## Build Client Binary

```bash
./scripts/build-client-binary.sh
```

The default output is `dist/tuno/`. The script also writes a local release archive and checksum to `release/`.

Verify the generated command:

```bash
./dist/tuno/tuno --help
```

## Install a Local Release Asset

```bash
./scripts/install-local.sh release/tuno-macos-arm64.tar.gz
```

If no path is provided, the script picks the default package for the current macOS arch:

```bash
./scripts/install-local.sh
```

Verify the installed wrapper:

```bash
tuno --help
```

To avoid touching your normal install paths during testing:

```bash
TUNO_INSTALL_DIR=/tmp/tuno-install-bin \
TUNO_APP_DIR=/tmp/tuno-install-app \
./scripts/install-local.sh release/tuno-macos-arm64.tar.gz

/tmp/tuno-install-bin/tuno --help
```

## Release Workflow

The GitHub Actions workflow in `.github/workflows/release-client.yml` builds client-only release assets for:

- macOS arm64
- macOS x86_64
- Linux x86_64

The release archive contains the PyInstaller app directory `tuno/`. The installer copies it to `~/.local/share/tuno` and writes a `tuno` wrapper into `~/.local/bin`.
