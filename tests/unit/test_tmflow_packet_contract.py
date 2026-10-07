"""Offline packet checks against the supplied 1002 field record."""
import unittest

from scripts.tmflow_connection_check import build_packet, parse_packet


class TMflowPacketContractTest(unittest.TestCase):
    def test_recorded_robot_ack(self):
        packet = parse_packet(b"$TMSCT,8,move1,OK,*41\r\n")
        self.assertEqual(packet.header, "TMSCT")
        self.assertEqual(packet.data, "move1,OK")

    def test_scalar_motion_packet_roundtrip(self):
        script = 'Move_Line("CPP",50,0,0,0,0,0,25,200,0,false)'
        data = "move1," + script
        packet = parse_packet(build_packet("TMSCT", data))
        self.assertEqual(packet.data, data)
        self.assertNotIn("{", packet.data)

    def test_corrupt_checksum_rejected(self):
        with self.assertRaises(ValueError):
            parse_packet(b"$TMSCT,8,move1,OK,*00\r\n")

    def test_length_counts_utf8_bytes(self):
        data = "test,中文"
        self.assertEqual(parse_packet(build_packet("TMSCT", data)).data, data)


if __name__ == "__main__":
    unittest.main()
