import unittest

from tuno.protocol.messages import (
    ProtocolError,
    decode_client_message,
    decode_json_message,
    encode_message,
)


class ProtocolTests(unittest.TestCase):
    """Cover protocol encoding and decoding contracts."""

    def test_round_trip_json_message(self) -> None:
        """Round-trip a valid client message through the JSON protocol helpers."""
        raw = encode_message("join", name="Alice")
        self.assertEqual(decode_client_message(raw), {"type": "join", "name": "Alice"})

    def test_rejects_unknown_type(self) -> None:
        """Reject protocol messages that declare an unsupported type."""
        with self.assertRaises(ProtocolError):
            decode_client_message('{"type": "hack"}')

    def test_decode_json_message_accepts_server_payload_shape(self) -> None:
        """Accept the server-side envelope shape when decoding raw JSON."""
        raw = encode_message("state", state={"started": False})
        self.assertEqual(decode_json_message(raw), {"type": "state", "state": {"started": False}})
