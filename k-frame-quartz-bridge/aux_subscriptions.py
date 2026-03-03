from __future__ import annotations

"""Utility helpers for building AUX subscription packets.

These functions recreate the working methodology from grass valley/aux_monitor_control.py
so the Quartz bridge can subscribe to AUX buses without depending on the captured dataset.

Special thanks to Brad Shaffer, @orthicon
"""

import struct
from typing import Iterable, List

_PKT_HEADER = 0x0004
_CMD_SUBSCRIBE = 0x0002
_PARAM_SUBSCRIBE = 0x0008
_PAYLOAD_WORDS = (0x00000024, 0x0000002E)
_DEFAULT_SEQUENCE = 0x0300
_DEFAULT_SUB_ID = 0x0400
_DEFAULT_LAYER_ADDR = 0x0000
_PID_AUX_SOURCE = 0x104A
_SIGNATURE = 0x0003


def build_aux_subscription_packet(
    sequence: int,
    subscription_id: int,
    bus_index: int,
    layer_address: int = _DEFAULT_LAYER_ADDR,
) -> bytes:
    """Return a single AUX source subscription packet (same as aux_monitor_control)."""

    bus = max(0, min(95, int(bus_index)))
    pkt = bytearray(52)

    struct.pack_into('>H', pkt, 0, _PKT_HEADER)
    struct.pack_into('>H', pkt, 2, sequence & 0xFFFF)
    struct.pack_into('>H', pkt, 4, _CMD_SUBSCRIBE)
    struct.pack_into('>H', pkt, 6, _PARAM_SUBSCRIBE)
    struct.pack_into('>I', pkt, 8, _PAYLOAD_WORDS[0])
    struct.pack_into('>I', pkt, 12, _PAYLOAD_WORDS[1])
    struct.pack_into('>H', pkt, 32, subscription_id & 0xFFFF)
    struct.pack_into('>H', pkt, 34, 0x0001)
    struct.pack_into('>H', pkt, 36, _SIGNATURE)
    struct.pack_into('>H', pkt, 38, _SIGNATURE)
    struct.pack_into('>I', pkt, 40, 0x00000000)
    struct.pack_into('>H', pkt, 44, _PID_AUX_SOURCE)
    struct.pack_into('>H', pkt, 46, 0x0000)
    pkt[48] = 0x19
    pkt[49] = (layer_address >> 8) & 0xFF
    pkt[50] = layer_address & 0xFF
    pkt[51] = bus

    return bytes(pkt)


def build_aux_subscription_sequence(
    aux_indices: Iterable[int],
    starting_sequence: int = _DEFAULT_SEQUENCE,
    starting_subscription_id: int = _DEFAULT_SUB_ID,
    layer_address: int = _DEFAULT_LAYER_ADDR,
) -> List[bytes]:
    """Generate packets for each AUX in aux_indices using the monitor methodology."""

    packets: List[bytes] = []
    seen: set[int] = set()
    sequence = starting_sequence
    sub_id = starting_subscription_id

    for aux in aux_indices:
        bus = max(0, min(95, int(aux)))
        if bus in seen:
            continue
        seen.add(bus)
        packets.append(
            build_aux_subscription_packet(
                sequence,
                sub_id,
                bus,
                layer_address=layer_address,
            )
        )
        sequence = (sequence + 1) & 0xFFFF
        sub_id = (sub_id + 1) & 0xFFFF

    return packets
