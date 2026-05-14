# Design

## Architecture

### Cloudflare Worker

The Worker deployment mirrors the standalone room server, but adapts it to Cloudflare's request-driven runtime. Instead of keeping one long-lived `RoomServer` object in a Python process, the Worker routes every websocket upgrade into one Cloudflare Durable Object so room state has a stable owner even when the Worker instance wakes, sleeps, or moves.

**Core files:**

- [`src/tuno/server/worker.py`](../src/tuno/server/worker.py): Worker entrypoint and `TunoLobby` Durable Object.
- [`wrangler.jsonc`](../wrangler.jsonc): binds `TUNO_LOBBY` to `TunoLobby` and declares the Durable Object migration.
- [`src/tuno/server/standalone.py`](../src/tuno/server/standalone.py): local websocket server using the same protocol and game-action layer.
- [`src/tuno/server/actions.py`](../src/tuno/server/actions.py): shared action application for both server modes.

**High-level flow:**

```text
Client websocket
  |
  v
Default.fetch()
  |
  v
env.TUNO_LOBBY.getByName("default-lobby")
  |
  v
TunoLobby.fetch() validates websocket upgrade and sends room_list
  |
  +-- no room selected --> TunoLobby._handle_room_selection()
  |                         /create creates GameState
  |                         /connect selects existing room
  |
  +-- room selected -----> TunoLobby._handle_room_action()
                            apply_action(GameState, player_id, payload)
                            broadcast state to sockets in that room
```

**Design notes:**

- `Default.fetch()` is intentionally thin: every request routes to the single lobby object named by `DEFAULT_LOBBY_ID`.
- `TunoLobby` owns `rooms: dict[str, GameState]`; each room name maps to one independent UNO game.
- `TunoLobby.fetch()` handles Cloudflare's websocket upgrade path with `WebSocketPair`. The standalone server receives an already-upgraded websocket from `websockets.serve()`, so it can enter `handler()` directly.
- WebSocket attachments store only routing metadata: `room` and `player_id`. This replaces standalone's in-process connection bookkeeping for Worker hibernation; the authoritative game state still lives in `TunoLobby.rooms`.
- `_handle_room_selection()` accepts only `create_room` and `join_room` before a room is selected.
- `_handle_room_action()` delegates UNO rules to `apply_action()`, so Worker and standalone behavior stay aligned.
- `_ensure_loaded()` and `_save_rooms()` serialize the room map through Durable Object storage. This is Worker-specific: `GameState`, `Card`, RNG state, and players are Python objects, while Durable Object storage needs JSON-safe values that can be restored after a wake-up.
- `_serialize_game()` and `_deserialize_game()` are the adapter layer between the in-memory game engine and Durable Object storage; they should preserve engine fields without changing game rules.
- `webSocketClose()` removes the closing player and deletes a room once no open socket remains attached to it.
- `_room_list()` exposes only public room metadata: name, status, player count, and max players.
