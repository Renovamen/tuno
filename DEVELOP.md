# Tuno Development

## Environment

```bash
git clone https://github.com/Renovamen/tuno.git
cd tuno

conda create -n tuno python=3.12
conda activate tuno

python -m pip install -e ".[dev]"
export PYTHONPATH=src
```

For Cloudflare Worker development, install the worker extra as well:

```bash
python -m pip install -e ".[dev,worker]"
```

For client binary builds, install the build extra:

```bash
python -m pip install -e ".[build]"
```

&nbsp;
## Run Locally

Start the server:

```bash
python -m tuno.server.local --host 127.0.0.1 --port 8765
```

Start the client:

```bash
python -m tuno.client.app
```

Then connect from inside the TUI:

```text
/server ws://127.0.0.1:8765
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

The Worker supports an optional `?game=<name>` query parameter. If omitted, it uses the default single shared game. 

If you change the Durable Object class name or add more Durable Objects later, update the `durable_objects.bindings` and `migrations` sections in [`wrangler.jsonc`](wrangler.jsonc) before deploying.

&nbsp;
## Tests

```bash
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
```

&nbsp;
## Lint

```bash
python -m ruff format .
```

&nbsp;
## Build Client Binary

```bash
./scripts/build-client-binary.sh
```

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
