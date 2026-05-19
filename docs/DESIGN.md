# Design

## Frameworks

- **TUI**: [Textual](https://textual.textualize.io/)
- **Client CLI**: [Typer](https://typer.tiangolo.com/)
- **Standalone server**: [websockets](https://websockets.readthedocs.io/)
- **Cloudflare server**: [Cloudflare Workers (Python)](https://developers.cloudflare.com/workers/languages/python/) + [Durable Objects](https://developers.cloudflare.com/durable-objects/)

## Architecture

### Cloudflare Worker

The Worker deployment mirrors the standalone room server but adapts it to Cloudflare's request-driven runtime. Instead of one long-lived `RoomServer` object in a Python process, the Worker routes every websocket upgrade into a single Cloudflare Durable Object so room state has a stable owner even when the Worker instance wakes, sleeps, or moves.

#### Why a Durable Object

Workers are stateless and short-lived, but UNO needs a single authoritative game per room — turn order, draw pile, and broadcasts must stay consistent across all players. The `TunoLobby` Durable Object acts as a singleton actor that:

- persists rooms and game state to its SQLite-backed storage, so the lobby survives evictions and redeploys;
- accepts hibernatable WebSockets and stashes each socket's `room` and `player_id` in its attachment, so reconnecting or waking clients resume without relying on process memory;
- serializes all room mutations through one event loop, removing the need for cross-instance locking.

#### Core files

- [`src/tuno/server/worker.py`](../src/tuno/server/worker.py): Worker entrypoint and `TunoLobby` Durable Object.
- [`wrangler.jsonc`](../wrangler.jsonc): binds `TUNO_LOBBY` to `TunoLobby` and declares the Durable Object migration.
- [`src/tuno/server/actions.py`](../src/tuno/server/actions.py): applies a client action to a room's `GameState`, shared by the Worker and the standalone server.

#### Configuration

[`wrangler.jsonc`](../wrangler.jsonc) wires the runtime to the Durable Object:

- `durable_objects.bindings` exposes the `TUNO_LOBBY` binding that `Default.fetch()` looks up.
- `migrations` declares `TunoLobby` as a SQLite-backed Durable Object class. Cloudflare uses these migration entries to create or evolve Durable Object classes in production.

If you rename `TunoLobby` or introduce additional Durable Objects, update both sections (and add a new migration tag) before deploying.

#### Routing and rooms

- `Default.fetch()` is intentionally thin: every request routes to the single lobby object named by `DEFAULT_LOBBY_ID`.
- `TunoLobby` owns `rooms: dict[str, GameState]`; each room name maps to one independent UNO game.
- `_room_list()` exposes only public room metadata: name, status, player count, and max players.

#### WebSocket lifecycle

- `TunoLobby.fetch()` handles Cloudflare's websocket upgrade path with `WebSocketPair`. The standalone server receives an already-upgraded websocket from `websockets.serve()`, so it can enter `handler()` directly.
- WebSocket attachments store only routing metadata: `room` and `player_id`. This replaces standalone's in-process connection bookkeeping for Worker hibernation; the authoritative game state still lives in `TunoLobby.rooms`.
- `_handle_room_selection()` accepts only `create_room` and `join_room` before a room is selected.
- `_handle_room_action()` delegates UNO rules to `apply_action()`, so Worker and standalone behavior stay aligned.
- `webSocketClose()` removes the closing player and deletes a room once no open socket remains attached to it.

#### State persistence

- `_ensure_loaded()` and `_save_rooms()` serialize the room map through Durable Object storage. This is Worker-specific: `GameState`, `Card`, RNG state, and players are Python objects, while Durable Object storage needs JSON-safe values that can be restored after a wake-up.
- `_serialize_game()` and `_deserialize_game()` are the adapter layer between the in-memory game engine and Durable Object storage; they should preserve engine fields without changing game rules.
