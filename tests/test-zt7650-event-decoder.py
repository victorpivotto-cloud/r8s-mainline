#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic protocol tests; never access the phone."""
import importlib.util
from pathlib import Path
import sys
import unittest

path = Path(__file__).resolve().parents[1] / 'experiments/zt7650_event_decoder.py'
spec = importlib.util.spec_from_file_location('zt7650_event_decoder', path)
decoder = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = decoder
spec.loader.exec_module(decoder)


class DecoderTests(unittest.TestCase):
    def decode(self, data, **kwargs):
        return decoder.decode_batch(data, slots=kwargs.get('slots', 10),
                                    max_x=kwargs.get('max_x', 4095),
                                    max_y=kwargs.get('max_y', 4095))

    def test_independent_layout_vector(self):
        # Hand-derived: PRESS=01, tid=1001 => 0x64; ABC/DEF => AB DE CF.
        # Pressure=100101, type high=10/low=01 => A5/40 (touch_type9).
        packet = bytes([0x64, 0xab, 0xde, 0xcf, 7, 3, 0xa5, 0x40] + [0] * 8)
        event, = self.decode(packet)
        self.assertEqual(event, decoder.Coordinate(9, 1, 0xabc, 0xdef, 37, 9, 7, 3))

    def test_zero_slot_and_all_active_statuses(self):
        for status in (1, 2, 3):
            event, = self.decode(bytes([status << 6] + [0] * 15))
            self.assertEqual((event.slot, event.status, event.x, event.y), (0, status, 0, 0))
        self.assertEqual(self.decode(bytes(16)), ())

    def test_maximum_batch(self):
        packets = [bytes([(1 << 6) | (slot << 2), 0, 0, 0, 0, 0, 0,
                          9 if slot == 0 else 0] + [0] * 8) for slot in range(10)]
        self.assertEqual([event.slot for event in self.decode(b''.join(packets))], list(range(10)))

    def test_truncation_and_count(self):
        for data in (b'', bytes(15), bytes(17), bytes(32), bytes([0] * 7 + [10] + [0] * 8),
                     bytes([0] * 7 + [1] + [0] * 8)):
            with self.subTest(size=len(data)):
                with self.assertRaises(decoder.ProtocolError):
                    self.decode(data)

    def test_bad_type_id_and_range(self):
        for data in (bytes([0x41] + [0] * 15), bytes([0x7c] + [0] * 15),
                     bytes([0x40, 0xff, 0, 0xf0] + [0] * 12)):
            with self.assertRaises(decoder.ProtocolError):
                self.decode(data, max_x=1079, max_y=2399)

    def test_batch_failure_is_atomic(self):
        first = bytes([0x40] + [0] * 6 + [1] + [0] * 8)
        invalid_tail = bytes([0x7c] + [0] * 15)
        with self.assertRaises(decoder.ProtocolError):
            self.decode(first + invalid_tail)

    def test_inclusive_axis_boundary(self):
        packet = bytes([0x40, 0x43, 0x95, 0x7f] + [0] * 12)
        event, = self.decode(packet, max_x=1079, max_y=2399)
        self.assertEqual((event.x, event.y), (1079, 2399))
        with self.assertRaises(decoder.ProtocolError):
            self.decode(packet, max_x=1078, max_y=2399)

    def test_configuration_and_reduced_slot_bounds(self):
        for settings in ({'slots': 0}, {'slots': 11}, {'max_x': 4096}, {'max_y': -1}):
            with self.assertRaises(ValueError):
                self.decode(bytes(16), **settings)
        with self.assertRaises(decoder.ProtocolError):
            self.decode(bytes([0x48] + [0] * 15), slots=2)
        with self.assertRaises(decoder.ProtocolError):
            self.decode(bytes([0] * 7 + [2] + [0] * 8) * 3, slots=2)

    def test_tail_event_type_and_strict_release(self):
        first = bytes([0x40] + [0] * 6 + [1] + [0] * 8)
        with self.assertRaises(decoder.ProtocolError):
            self.decode(first + bytes([0x41] + [0] * 15))
        with self.assertRaises(decoder.ProtocolError):
            self.decode(bytes([0xc0, 0xff, 0, 0xf0] + [0] * 12), max_x=1079)

    def test_preserved_duplicates_and_ignored_tail_metadata(self):
        first = bytes([0x40] + [0] * 6 + [1] + [0] * 8)
        tail = bytes([0x80] + [0] * 6 + [7] + [0] * 8)
        self.assertEqual([(event.slot, event.status) for event in self.decode(first + tail)],
                         [(0, 1), (0, 2)])
        none_tail = bytes([0x3c, 0xff, 0xff, 0xff] + [0] * 12)
        self.assertEqual(len(self.decode(first + none_tail, max_x=1079, max_y=2399)), 1)


if __name__ == '__main__':
    unittest.main()
