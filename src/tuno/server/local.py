from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Optional

from websockets.exceptions import ConnectionClosed

from tuno.protocol.messages import ProtocolError, decode_client_message, encode_message
from tuno.server.session import GameSession

LOGGER = logging.getLogger(__name__)


async def handler(websocket, session: GameSession) -> None:
    accepted = await session.attach(websocket)
    if not accepted:
        return

    try:
        async for raw in websocket:
            try:
                payload = decode_client_message(raw)
            except ProtocolError as exc:
                await websocket.send(encode_message("error", message=str(exc)))
                continue
            await session.handle(websocket, payload)
    except ConnectionClosed:
        LOGGER.info("client disconnected")
    finally:
        await session.detach(websocket)


async def run_server(host: str, port: int, session: Optional[GameSession] = None) -> None:
    from websockets.asyncio.server import serve

    active_session = session or GameSession()
    async with serve(lambda websocket: handler(websocket, active_session), host, port):
        LOGGER.info("tuno local server listening on ws://%s:%s", host, port)
        await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the tuno local WebSocket server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    asyncio.run(run_server(args.host, args.port))


if __name__ == "__main__":
    main()
