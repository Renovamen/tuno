# tUNO

A terminal-first UNO game.

## Install

The installer downloads the **client only** and exposes it as `tuno`.

```bash
curl -fsSL https://raw.githubusercontent.com/Renovamen/tuno/main/scripts/install.sh | sh
```

If `~/.local/bin` is not on your `PATH`, add it before running `tuno`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

macOS may quarantine unsigned downloaded binaries. If needed:

```bash
xattr -dr com.apple.quarantine ~/.local/share/tuno ~/.local/bin/tuno
```

## Server

Server binaries are not shipped. Run the server from source on a machine with Python 3.11+:

```bash
git clone https://github.com/Renovamen/tuno.git
cd tuno
python -m pip install .
python -m tuno.server.local --host 0.0.0.0 --port 8765
```

## How to play

Connect to a running server:

```bash
tuno ws://server-host:8765
```

### Commands

- `/connect <name>`: Join the server.
- `/start`: Host starts the round.
- `/play <n>`: Play the numbered card shown in your hand.
- `/play <n> [color]`: Play a wild card and choose its color.
- `/draw`: Draw one card.
- `/pass`: Pass after drawing, when allowed.
- `/uno`: Arm UNO for your next play.
- `/exit`: Quit.

Type `Tab` to autocomplete the current command.

### Notable rules

- The first player is the host.
- The host can start once at least 2 players have joined.
- Arm UNO with `/uno` **before** playing a card from a two-card hand. Missing UNO triggers an immediate 2-card penalty.
- A drawn card is immediately playable if it is valid.
- `Wild +4` is rejected if the player still has a non-wild card matching the current color.

## Development

### Environment setup

```bash
conda create -n tuno python=3.12
conda activate tuno

python -m pip install -e ".[dev]"

export PYTHONPATH=src
```

### Run locally

```bash
python -m tuno.server.local --host 127.0.0.1 --port 8765
python -m tuno.client.app ws://127.0.0.1:8765
```

### Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m ruff check .
PYTHONPATH=src python -m ruff format --check .
```

## Todo

- [ ] Multiple game rooms
- [ ] House UNO rules
- [ ] More players
