# Tuno

A terminal-first UNO game.

![screenshot](./docs/assets/screenshot.png)

## Client 

### macOS / Linux

#### Install

```bash
curl -fsSL https://raw.githubusercontent.com/Renovamen/tuno/HEAD/scripts/install.sh | sh
```

The install script puts Tuno in `~/.local/bin` and adds it to your `PATH`.

#### Update

Tuno can update itself if a new version is available:

```bash
tuno update
```

#### Uninstall

```bash
tuno uninstall
```

This removes `~/.local/share/tuno` and `~/.local/bin/tuno`, and can optionally remove `~/.config/tuno`.

&nbsp;
## Server

Here is a hosted server you can try:

```bash
wss://tuno.renovamenzxh.workers.dev
```

If you want to deploy your own server, check the following.

### Deploy on Cloudflare Workers

**Option 1:** Install [uv](https://docs.astral.sh/uv/#installation), then deploy from a local checkout:

```bash
git clone https://github.com/Renovamen/tuno.git
cd tuno
uvx --from workers-py pywrangler deploy
```

**Option 2:** Fork this repo and import the fork into your
[Cloudflare dashboard](https://developers.cloudflare.com/workers/get-started/dashboard/). In "Build configuration", leave "Build command" empty and set "Deploy command" to `uv run pywrangler deploy`.

&nbsp;
## How to play

Start the Tuno client app:

```bash
tuno
```

### Commands

**Note:** You can always press `Tab` to autocomplete the current command.

**Lobby:**
- `/server <server>`: Connect to the specified server.
- `/server`: Show and select saved servers.
- `/create <room>`: Create and select a room.
- `/connect <room>`: Select an existing room.
- `/join <player_name>`: Join the selected room as a player.
- `/start`: The host starts the round.
- `/exit`: Quit Tuno.

**Gameplay:**
- `/play <n>`: Play the numbered card shown in your hand.
- `/play <n> [color]`: Play a wild card and choose its color.
- `/draw`: Draw one card.
- `/pass`: Pass after drawing, when allowed.
- `/uno`: Arm UNO for your next play.

### Notable rules

- The first player is the host.
- The host can start once at least 2 players have joined.
- Arm UNO with `/uno` **before** playing a card from a two-card hand. Missing UNO triggers an immediate 2-card penalty.
- A drawn card is immediately playable if it is valid.
- `Wild +4` is rejected if the player still has a non-wild card matching the current color.

&nbsp;
## Todo

- [x] Multiple game rooms
- [ ] House rules
- [ ] More players
- [ ] Chat

&nbsp;
## Development

Check [DEVELOP.md](docs/DEVELOP.md) for development instructions.
