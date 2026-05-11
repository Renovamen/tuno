from __future__ import annotations

import unittest

from tuno.client.runtime import ClientRuntime


class RuntimeCallbacks:
    def __init__(self) -> None:
        self.feedback: list[str] = []
        self.render_count = 0
        self.clear_count = 0
        self.exit_count = 0

    def set_feedback(self, message: str) -> None:
        self.feedback.append(message)

    def clear_pending(self) -> None:
        self.clear_count += 1

    def render_state(self) -> None:
        self.render_count += 1

    def exit_app(self) -> None:
        self.exit_count += 1


class FakeApi:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def send(self, kind: str, **payload) -> None:
        self.sent = (kind, payload)


class ClientRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Cover non-widget client runtime behavior extracted from the Textual app."""

    def build_runtime(self, callbacks: RuntimeCallbacks) -> ClientRuntime:
        return ClientRuntime(
            set_feedback=callbacks.set_feedback,
            clear_pending_server_response=callbacks.clear_pending,
            render_state=callbacks.render_state,
            exit_app=callbacks.exit_app,
        )

    async def test_invalid_server_url_surfaces_feedback(self) -> None:
        callbacks = RuntimeCallbacks()
        runtime = self.build_runtime(callbacks)

        await runtime.connect_server("http://example.test")

        self.assertEqual(
            callbacks.feedback,
            ["Command error: /server requires a ws:// or wss:// URL."],
        )

    async def test_send_without_connection_surfaces_feedback(self) -> None:
        callbacks = RuntimeCallbacks()
        runtime = self.build_runtime(callbacks)

        await runtime.send("start")

        self.assertEqual(callbacks.feedback, ["Command error: Connect first."])

    async def test_handle_messages_updates_state_and_feedback(self) -> None:
        callbacks = RuntimeCallbacks()
        runtime = self.build_runtime(callbacks)
        runtime.state = {"current_color": "red", "top_card": {"short": "R:5"}}

        await runtime.handle_message({"type": "welcome", "player_id": "p1"})
        await runtime.handle_message({"type": "state", "state": {"started": True}})
        await runtime.handle_message(
            {
                "type": "error",
                "code": "illegal_play",
                "message": "That card cannot be played.",
            }
        )

        self.assertEqual(runtime.player_id, "p1")
        self.assertEqual(runtime.state, {"started": True})
        self.assertEqual(callbacks.clear_count, 2)
        self.assertEqual(callbacks.render_count, 2)
        self.assertIn("Illegal play:", callbacks.feedback[-1])

    async def test_close_current_server_resets_runtime_state(self) -> None:
        callbacks = RuntimeCallbacks()
        runtime = self.build_runtime(callbacks)
        api = FakeApi()
        runtime.api = api  # type: ignore[assignment]
        runtime.player_id = "p1"
        runtime.state = {"started": True}
        runtime.say_uno_next = True

        await runtime.close_current_server()

        self.assertIsNone(runtime.api)
        self.assertIsNone(runtime.player_id)
        self.assertEqual(runtime.state, {})
        self.assertFalse(runtime.say_uno_next)
        self.assertTrue(api.closed)
