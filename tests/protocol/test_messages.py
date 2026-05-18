import unittest

from tuno.protocol.messages import (
    ClientMsg,
    ProtocolError,
    ServerMsg,
    decode_client_message,
    decode_json_message,
    decode_server_message,
    encode_message,
)


class ProtocolTests(unittest.TestCase):
    """Cover protocol encoding and decoding contracts."""

    def test_round_trip_json_message(self) -> None:
        """Round-trip a valid client message through the JSON protocol helpers."""
        raw = encode_message(ClientMsg.JOIN, name="Alice")
        decoded = decode_client_message(raw)
        self.assertEqual(decoded, {"type": "join", "name": "Alice"})
        self.assertIs(type(decoded["type"]), str)

    def test_accepts_room_protocol_messages(self) -> None:
        """Accept room-selection client and server message envelopes."""
        self.assertEqual(
            decode_client_message(encode_message(ClientMsg.CREATE_ROOM, name="Table 1")),
            {"type": "create_room", "name": "Table 1"},
        )
        self.assertEqual(
            decode_client_message(encode_message(ClientMsg.EXIT_ROOM)),
            {"type": "exit_room"},
        )
        self.assertEqual(
            decode_server_message(encode_message(ServerMsg.ROOM_CLOSED, message="Room closed.")),
            {"type": "room_closed", "message": "Room closed."},
        )
        self.assertEqual(
            decode_server_message(encode_message(ServerMsg.ROOM_LEFT, message="Left room.")),
            {"type": "room_left", "message": "Left room."},
        )

    def test_enum_values_match_wire_strings(self) -> None:
        """StrEnum members serialize to the exact protocol strings on the wire."""
        self.assertEqual(str(ClientMsg.PLAY_CARD), "play_card")
        self.assertEqual(str(ServerMsg.WELCOME), "welcome")

    def test_rejects_unknown_type(self) -> None:
        """Reject protocol messages that declare an unsupported type."""
        with self.assertRaises(ProtocolError):
            decode_client_message('{"type": "hack"}')
        with self.assertRaises(ProtocolError):
            decode_server_message('{"type": "hack"}')

    def test_decode_json_message_accepts_server_payload_shape(self) -> None:
        """Accept the server-side envelope shape when decoding raw JSON."""
        raw = encode_message(ServerMsg.STATE, state={"started": False})
        self.assertEqual(decode_json_message(raw), {"type": "state", "state": {"started": False}})
