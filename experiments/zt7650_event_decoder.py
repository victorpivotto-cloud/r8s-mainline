# SPDX-License-Identifier: GPL-2.0-only
"""Host-only coordinate packet model, not a touchscreen driver.

Layout reference: ExtremeXT/android_kernel_samsung_exynos990 at
69515fbb7a4395898c05a8624f76a12afbac11c5, zinitix/zt7650/zinitix_ts.h.
No I2C, GPIO, IRQ, input events, calibration or firmware access.
"""
from dataclasses import dataclass

PACKET_SIZE = 16
MAX_EVENTS = 10


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class Coordinate:
    slot: int
    status: int
    x: int
    y: int
    pressure: int
    touch_type: int
    major: int
    minor: int


def decode_batch(data: bytes, *, slots: int, max_x: int, max_y: int) -> tuple:
    """Decode a fully read coordinate batch atomically.

    Strict experimental policy: first left_event fixes batch size, IDs are
    zero-based, and active coordinate events (including release) must be within
    inclusive axis limits. Release/error/input-slot policy needs real captures.
    Unlike vendor's count clamp, malformed batches are rejected. NONE packets
    count toward batch size but do not validate ID/coordinates or emit output.
    Tail left_event fields are not assumed to be a countdown.
    """
    if not 1 <= slots <= MAX_EVENTS or not 0 <= max_x <= 4095 or not 0 <= max_y <= 4095:
        raise ValueError('invalid decoder configuration')
    if len(data) < PACKET_SIZE or len(data) % PACKET_SIZE:
        raise ProtocolError('truncated packet')
    if data[0] & 3:
        raise ProtocolError('first packet is not a coordinate event')
    remaining = data[7] & 15
    if remaining >= slots or len(data) != (remaining + 1) * PACKET_SIZE:
        raise ProtocolError('invalid batch event count')
    result = []
    for offset in range(0, len(data), PACKET_SIZE):
        packet = data[offset:offset + PACKET_SIZE]
        if packet[0] & 3:
            raise ProtocolError('non-coordinate event in coordinate batch')
        status = packet[0] >> 6
        if status == 0:
            continue
        slot = (packet[0] >> 2) & 15
        if slot >= slots:  # Bound vendor's direct cur_coord[tid] indexing.
            raise ProtocolError('invalid slot')
        x = (packet[1] << 4) | (packet[3] >> 4)
        y = (packet[2] << 4) | (packet[3] & 15)
        if x > max_x or y > max_y:
            raise ProtocolError('coordinate outside axis limits')
        result.append(Coordinate(slot, status, x, y, packet[6] & 63,
                                 ((packet[6] >> 6) << 2) | (packet[7] >> 6),
                                 packet[4], packet[5]))
    return tuple(result)
