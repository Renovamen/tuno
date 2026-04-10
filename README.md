# Tuno

A terminal-first UNO game.

## Client 

### macOS / Linux

#### Install

```bash
curl -fsSL https://raw.githubusercontent.com/Renovamen/tuno/main/scripts/install.sh | sh
```

The install script puts `tuno` in `~/.local/bin`. If it's not on your `PATH`, add it:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

#### Uninstall:

```bash
rm -rf ~/.local/share/tuno
rm -f ~/.local/bin/tuno
```

## Server

Run the server from source on a machine with Python 3.11+:

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

## Todo

- [ ] Multiple game rooms
- [ ] House UNO rules
- [ ] More players
