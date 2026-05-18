# Tuno Development

## Environment

```bash
git clone https://github.com/Renovamen/tuno.git
cd tuno

uv sync --extra dev
```

For Cloudflare Worker development, install the worker extra as well:

```bash
uv sync --extra dev,worker
```

For client binary builds, install the build extra:

```bash
uv sync --extra dev,build
```

If you change the local package version in `src/tuno/__init__.py`, refresh the editable package metadata so `importlib.metadata.version("tuno")` returns the new version:

```bash
uv sync --reinstall-package tuno
```

&nbsp;
## Run Locally

Start the server:

```bash
uv run python -m tuno.server --host 127.0.0.1 --port 8765
```

Start the client:

```bash
uv run python -m tuno.client
uv run python -m tuno.client --server ws://127.0.0.1:8765 # Start with a preconfigured server, so you do not need to enter it in the TUI
```

&nbsp;
## Cloudflare Workers

Local development:

```bash
uv run pywrangler dev
```

Deploy on cloudflare workers:

```bash
uv run pywrangler deploy
```

The Worker uses the default room lobby endpoint. After connecting, clients create or select rooms with `/create <room>` or `/connect <room>`.

If you change the Durable Object class name or add more Durable Objects later, update the `durable_objects.bindings` and `migrations` sections in [`wrangler.jsonc`](wrangler.jsonc) before deploying.

&nbsp;
## Tests

```bash
uv run python -m unittest discover -s tests -v
```

&nbsp;
## Lint & Formatting

```bash
uv run python -m ruff check . # Run lint checks
uv run python -m ruff format --check . # Check formatting
uv run python -m ruff format .
```

&nbsp;
## Build Client Binary

```bash
./scripts/build-client-binary.sh
```

The build script runs PyInstaller through the locked uv project environment with the `build` extra enabled.

The default output is `dist/tuno/`. The script also writes a local release archive and checksum to `release/`.

Verify the generated command:

```bash
./dist/tuno/tuno --help
```

&nbsp;
## Install a Local Release Asset

This script picks the default package for your current arch:

```bash
./scripts/install-local.sh
```

You can also provide a specific release path:

```bash
./scripts/install-local.sh release/tuno-macos-arm64.tar.gz
```

Verify the installed wrapper:

```bash
tuno --help
```

&nbsp;
## Release Workflow

The GitHub Actions workflow in `.github/workflows/release-client.yml` builds client-only release assets for:

- macOS arm64
- macOS x86_64
- Linux x86_64

The release archive contains the PyInstaller app directory `tuno/`. The installer copies it to `~/.local/share/tuno` and writes a `tuno` wrapper into `~/.local/bin`.
