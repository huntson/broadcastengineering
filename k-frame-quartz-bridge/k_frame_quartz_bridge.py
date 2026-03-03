#!/usr/bin/env python3
"""
K-Frame Quartz Bridge.

Bridges Grass Valley K-Frame AUX buses to Evertz/Quartz router control
clients. Listens for Quartz ASCII router commands and translates them into
K-Frame AUX bus routing calls using the persistent GV plugin connection.

Special thanks to Brad Shaffer, @orthicon
"""

from __future__ import annotations

import asyncio
import configparser
import contextlib
import html
import json
import struct
import random
import time
import logging
import os
import re
import signal
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from gv_plugin_persistent import GVPluginPersistent
from aux_subscriptions import build_aux_subscription_sequence

logger = logging.getLogger("k_frame_quartz_bridge")


@dataclass
class GVConfig:
    host: str
    suite: str
    bind_host: str = "0.0.0.0"
    protocol: str = "auto"


@dataclass
class RouterConfig:
    listen_host: str = "127.0.0.1"
    listen_port: int = 4000
    levels: list[str] = field(default_factory=lambda: ["V"])
    sources: int = 0
    destinations: int = 0


@dataclass
class BridgeMappings:
    dest_to_aux: Dict[int, int] = field(default_factory=dict)
    source_to_input: Dict[int, int] = field(default_factory=dict)


@dataclass
class RouterNames:
    sources: Dict[int, str] = field(default_factory=dict)
    destinations: Dict[int, str] = field(default_factory=dict)


@dataclass
class HTTPConfig:
    listen_host: str = "127.0.0.1"
    listen_port: int = 4001


@dataclass
class CommandRecord:
    timestamp: datetime
    level: str
    dest: int
    source: int
    aux: int
    gv_source: int
    status: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "destination": self.dest,
            "source": self.source,
            "aux": self.aux,
            "gv_source": self.gv_source,
            "status": self.status,
        }


@dataclass
class BridgeState:
    gv_host: str
    gv_suite: str
    dest_to_aux: Dict[int, int]
    source_to_input: Dict[int, int]
    names: RouterNames
    routes: Dict[str, Dict[int, int]] = field(default_factory=dict)
    clients: Dict[str, datetime] = field(default_factory=dict)
    gv_connected: bool = False
    gv_working_port: int = 0
    last_error: Optional[str] = None
    command_log: List[CommandRecord] = field(default_factory=list)
    max_log: int = 50
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def set_gv_connected(self, connected: bool, working_port: Optional[int] = None) -> None:
        self.gv_connected = connected
        if working_port is not None:
            self.gv_working_port = working_port
        if connected:
            self.last_error = None

    def set_gv_error(self, message: str) -> None:
        self.last_error = message
        self.gv_connected = False

    def add_client(self, peer: str) -> None:
        self.clients[peer] = datetime.now(timezone.utc)

    def remove_client(self, peer: str) -> None:
        self.clients.pop(peer, None)

    def record_route(
        self,
        level: str,
        dest: int,
        source: int,
        aux: int,
        gv_source: int,
        status: str,
    ) -> None:
        record = CommandRecord(
            timestamp=datetime.now(timezone.utc),
            level=level,
            dest=dest,
            source=source,
            aux=aux,
            gv_source=gv_source,
            status=status,
        )
        self.command_log.append(record)
        if len(self.command_log) > self.max_log:
            self.command_log = self.command_log[-self.max_log :]

        if status == "ok":
            self.routes.setdefault(level, {})[dest] = source

@dataclass
class BridgeConfig:
    gv: GVConfig
    router: RouterConfig
    mappings: BridgeMappings
    names: RouterNames
    http: HTTPConfig

    @staticmethod
    def _parse_json_dict(raw: str) -> Dict[int, int]:
        result: Dict[int, int] = {}
        if raw:
            for k, v in json.loads(raw).items():
                result[int(k)] = int(v)
        return result

    @staticmethod
    def _parse_json_str_dict(raw: str) -> Dict[int, str]:
        result: Dict[int, str] = {}
        if raw:
            for k, v in json.loads(raw).items():
                result[int(k)] = str(v)
        return result

    @staticmethod
    def from_env() -> "BridgeConfig":
        gv_cfg = GVConfig(
            host=os.environ.get("GV_HOST", "127.0.0.1"),
            suite=os.environ.get("GV_SUITE", "suite1a"),
            bind_host=os.environ.get("GV_BIND_HOST", "0.0.0.0"),
            protocol=os.environ.get("GV_PROTOCOL", "auto"),
        )

        destinations = int(os.environ.get("ROUTER_DESTINATIONS", "96"))
        sources = int(os.environ.get("ROUTER_SOURCES", "809"))
        router_cfg = RouterConfig(
            listen_host=os.environ.get("QUARTZ_LISTEN_HOST", "127.0.0.1"),
            listen_port=int(os.environ.get("QUARTZ_LISTEN_PORT", "4000")),
            sources=sources,
            destinations=destinations,
        )

        dest_map = BridgeConfig._parse_json_dict(os.environ.get("DEST_MAPPINGS", ""))
        source_map = BridgeConfig._parse_json_dict(os.environ.get("SRC_MAPPINGS", ""))

        dest_names = BridgeConfig._parse_json_str_dict(os.environ.get("DEST_NAMES", ""))
        if not dest_names:
            for i in range(1, destinations + 1):
                dest_names[i] = f"AUX{i}"

        src_names = BridgeConfig._parse_json_str_dict(os.environ.get("SRC_NAMES", ""))

        names = RouterNames(sources=src_names, destinations=dest_names)

        http_cfg = HTTPConfig(
            listen_host=os.environ.get("HTTP_LISTEN_HOST", "127.0.0.1"),
            listen_port=int(os.environ.get("HTTP_LISTEN_PORT", "4001")),
        )

        return BridgeConfig(
            gv=gv_cfg,
            router=router_cfg,
            mappings=BridgeMappings(dest_to_aux=dest_map, source_to_input=source_map),
            names=names,
            http=http_cfg,
        )

    @staticmethod
    def from_ini(config_path: Path) -> "BridgeConfig":
        config = configparser.ConfigParser()
        config.read(config_path)

        gv_cfg = GVConfig(
            host=config.get("gv", "host", fallback="127.0.0.1"),
            suite=config.get("gv", "suite", fallback="suite1a"),
            bind_host=config.get("gv", "bind_host", fallback="0.0.0.0"),
            protocol=config.get("gv", "protocol", fallback="auto"),
        )

        destinations = config.getint("router", "destinations", fallback=96)
        sources = config.getint("router", "sources", fallback=809)
        router_cfg = RouterConfig(
            listen_host=config.get("quartz", "listen_host", fallback="127.0.0.1"),
            listen_port=config.getint("quartz", "listen_port", fallback=4000),
            sources=sources,
            destinations=destinations,
        )

        dest_map = BridgeConfig._parse_json_dict(
            config.get("mappings", "dest_mappings", fallback="")
        )
        source_map = BridgeConfig._parse_json_dict(
            config.get("mappings", "src_mappings", fallback="")
        )

        dest_names = BridgeConfig._parse_json_str_dict(
            config.get("names", "dest_names", fallback="")
        )
        if not dest_names:
            for i in range(1, destinations + 1):
                dest_names[i] = f"AUX{i}"

        src_names = BridgeConfig._parse_json_str_dict(
            config.get("names", "src_names", fallback="")
        )

        names = RouterNames(sources=src_names, destinations=dest_names)

        http_cfg = HTTPConfig(
            listen_host=config.get("http", "listen_host", fallback="127.0.0.1"),
            listen_port=config.getint("http", "listen_port", fallback=4001),
        )

        return BridgeConfig(
            gv=gv_cfg,
            router=router_cfg,
            mappings=BridgeMappings(dest_to_aux=dest_map, source_to_input=source_map),
            names=names,
            http=http_cfg,
        )


class GVSwitchController:
    """Thin wrapper around the persistent GV plugin."""

    def __init__(self, cfg: GVConfig, router_cfg: Optional[RouterConfig], state: BridgeState):
        self.cfg = cfg
        self.router_cfg = router_cfg or RouterConfig()
        self.state = state
        self.loop = None
        self.plugin = GVPluginPersistent(
            cfg.host,
            cfg.suite,
            bind_host=cfg.bind_host,
            message_callback=self._handle_plugin_message,
            protocol=cfg.protocol,
        )
        self._lock = asyncio.Lock()
        self._connected = False
        self._subscribed = False
        aux_base_count = self.router_cfg.destinations or len(state.dest_to_aux) or 96
        dest_aux_values = self._compute_dest_aux_values(aux_base_count)

        self.subscription_payloads = build_aux_subscription_sequence(dest_aux_values)
        if self.subscription_payloads:
            logger.info(
                'Prepared %s AUX subscription packets using aux_monitor_control methodology',
                len(self.subscription_payloads),
            )
        else:
            logger.error('Failed to build AUX subscription packets; updates disabled')

    async def ensure_connection(self) -> None:
        if self._connected:
            return
        async with self._lock:
            if self._connected:
                return
            self._subscribed = False
            logger.info("Connecting to GV switcher %s (%s)", self.cfg.host, self.cfg.suite)
            success = await asyncio.to_thread(self.plugin.connect)
            if not success:
                self.state.set_gv_error("Failed to perform GV handshake")
                raise ConnectionError("Failed to connect to GV switcher")
            self._connected = True
            self.loop = asyncio.get_running_loop()
            self.state.set_gv_connected(True, self.plugin.working_port)
            logger.info("Connection to GV switcher established (port %s)", self.plugin.working_port)
            if not self._subscribed:
                await asyncio.to_thread(self._replay_subscription_sequence)

    async def send_aux(self, aux_number: int, source_number: int) -> bool:
        if self._connected and not self.plugin.connected:
            logger.warning("Plugin reports disconnected; marking controller disconnected")
            self._connected = False
            self.state.set_gv_connected(False, 0)
        try:
            await self.ensure_connection()
        except Exception as exc:
            logger.error("GV connection failed before routing AUX %s -> %s: %s", aux_number, source_number, exc)
            self.state.set_gv_error(str(exc))
            return False
        logger.info("Routing AUX %s -> source %s", aux_number, source_number)
        try:
            result = await asyncio.to_thread(self.plugin.send_aux_command, aux_number, source_number)
        except Exception as exc:
            logger.error("GV send exception for AUX %s -> %s: %s", aux_number, source_number, exc)
            self._connected = False
            self.state.set_gv_error(str(exc))
            return False
        if result:
            logger.info("GV command succeeded AUX %s -> source %s", aux_number, source_number)
            self.state.set_gv_connected(True, self.plugin.working_port)
        else:
            logger.error("GV command FAILED AUX %s -> source %s", aux_number, source_number)
            self._connected = False
            self.state.set_gv_error(f"AUX {aux_number} -> {source_number} command failed")
        return result

    def _compute_dest_aux_values(self, aux_base_count: int) -> List[int]:
        count = max(aux_base_count, len(self.state.dest_to_aux) or 1)
        dest_aux_values: List[int] = []
        for index in range(count):
            quartz_dest = index + 1
            aux_number = self.state.dest_to_aux.get(quartz_dest, quartz_dest)
            dest_aux_values.append(max(0, int(aux_number) - 1))
        return dest_aux_values

    def _replay_subscription_sequence(self) -> None:
        if not self.subscription_payloads:
            logger.warning('No subscription payloads available; AUX updates will not be received')
            return
        sent = 0
        for idx, payload in enumerate(self.subscription_payloads):
            label = f'SUB_PKT[{idx}]'
            if self.plugin.send_raw_packet(payload, label=label):
                sent += 1
                time.sleep(0.005)
            else:
                logger.warning('Failed to send subscription payload %s', idx)
        self._subscribed = sent > 0
        if self._subscribed:
            logger.info('Replayed %s subscription payloads for AUX subscription', sent)
        else:
            logger.warning('No subscription payloads sent successfully')

    def _handle_plugin_message(self, payload: bytes) -> None:
        if self.loop:
            self.loop.call_soon_threadsafe(self._process_plugin_message, payload)

    def _process_plugin_message(self, payload: bytes) -> None:
        """Parse one or more subscription response blocks from a GV message.

        Uses the multi-response block parsing from aux_monitor_control.py.
        A single UDP packet can contain multiple response blocks.
        """
        if len(payload) < 8:
            logger.debug("GV message too short (%d bytes)", len(payload))
            return

        offset = 4  # Skip the 4-byte header (0x0004 + seq)

        while offset + 12 <= len(payload):
            resp_type = struct.unpack_from('>H', payload, offset + 2)[0]
            pay_len = struct.unpack_from('>I', payload, offset + 4)[0]

            resp_size = 12 + pay_len
            if offset + resp_size > len(payload):
                break

            if resp_type == 0x0010 and pay_len >= 16:
                self._parse_single_aux_response(payload, offset, pay_len)

            offset += resp_size

    def _parse_single_aux_response(self, msg: bytes, offset: int, pay_len: int) -> None:
        """Parse a single AUX subscription response block.

        Layout at payload base (offset + 12):
          +0..+1:   sub_id
          +8..+9:   signature (must be 0x104a)
          +12:      marker (must be 0x19)
          +13..+14: addr
          +15:      bus (0-based AUX index)
          +20..+21: source value
        """
        pb = offset + 12

        if pb + 16 > len(msg):
            return

        signature = struct.unpack_from('>H', msg, pb + 8)[0]
        marker = msg[pb + 12]

        if signature != 0x104a or marker != 0x19:
            return

        bus = msg[pb + 15]
        aux_number = bus + 1

        data_base = pb + 16
        data_len = pay_len - 16

        if data_len < 6 or data_base + 6 > len(msg):
            return

        gv_source = struct.unpack_from('>H', msg, data_base + 4)[0]
        quartz_dest = self._unmap_dest(aux_number)
        quartz_source = self._unmap_source(gv_source)

        logger.info(
            "AUX update: AUX %d -> GV source %d (quartz dest=%d src=%d)",
            aux_number, gv_source, quartz_dest, quartz_source,
        )
        self.state.record_route('V', quartz_dest, quartz_source, aux_number, gv_source, 'ok')

    def _unmap_source(self, gv_source: int) -> int:
        for quartz_source, mapped in self.state.source_to_input.items():
            if mapped == gv_source:
                return quartz_source
        return gv_source

    def _unmap_dest(self, aux: int) -> int:
        for quartz_dest, mapped_aux in self.state.dest_to_aux.items():
            if mapped_aux == aux:
                return quartz_dest
        return aux

    async def close(self) -> None:
        if not self._connected:
            return
        async with self._lock:
            if not self._connected:
                return
            await asyncio.to_thread(self.plugin.disconnect)
            self._connected = False
            self.state.set_gv_connected(False, 0)
            logger.info("Disconnected from GV switcher")

    async def _reconnect(self) -> bool:
        """Force a full disconnect/reconnect cycle. Returns True on success."""
        async with self._lock:
            self._connected = False
            self._subscribed = False
            self.state.set_gv_connected(False, 0)
            logger.info("Disconnecting from GV switcher for reconnection")
            try:
                await asyncio.to_thread(self.plugin.disconnect)
            except Exception as exc:
                logger.warning("Error during disconnect: %s", exc)
        await self.ensure_connection()
        return self._connected

    async def reconnection_loop(self, stop_event: asyncio.Event) -> None:
        """Background task that monitors connection health and reconnects.

        Exponential backoff: 5s -> 10s -> 20s -> 40s -> 60s cap.
        Resets to 5s after a successful reconnection.
        """
        INITIAL_DELAY = 5.0
        MAX_DELAY = 60.0
        CHECK_INTERVAL = 2.0

        delay = INITIAL_DELAY

        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=CHECK_INTERVAL)
                break
            except asyncio.TimeoutError:
                pass

            if self._connected and self.plugin.connected:
                delay = INITIAL_DELAY
                continue

            logger.info(
                "GV connection lost (controller=%s, plugin=%s); reconnecting in %.0fs",
                self._connected, self.plugin.connected, delay,
            )
            self.state.set_gv_error("Connection lost, reconnecting...")

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=delay)
                break
            except asyncio.TimeoutError:
                pass

            try:
                await self._reconnect()
                logger.info("GV reconnection successful (port %s)", self.plugin.working_port)
                delay = INITIAL_DELAY
            except Exception as exc:
                logger.warning("GV reconnection failed: %s", exc)
                self.state.set_gv_error(f"Reconnection failed: {exc}")
                delay = min(delay * 2, MAX_DELAY)

        logger.info("Reconnection loop stopped")


class QuartzRouterServer:
    """Implements a minimal Quartz ASCII router server."""

    EXTENSION_RESPONSES = {
        'QCX': '.&QCX,NO',
        'QCP': '.&QCP,NO',
        'ILK': '.&ILK,NO',
        'ELK': '.&ELK,NO',
        'DLK': '.&DLK,NO',
        'EPT': '.&EPT,NO',
        'DPT': '.&DPT,NO',
        'SET': '.&SET,NO',
    }

    LEVEL_RESPONSES = {
        10: ['.ALV10,V,A33-A64', '.A'],
        18: ['.ALV18,V,A65-A96', '.A'],
    }

    ROUTE_CMD = re.compile(r"^\.SW([A-Z])(\d{1,3}),(\d{1,3})$")
    SET_VECTOR_CMD = re.compile(r"^\.S([A-Z])0*(\d+),0*(\d+)$")
    INQUIRE_CMD = re.compile(r"^\.I([A-Z])(\d{1,3})$")
    SOURCE_NAME_CMD = re.compile(r"^\.RS(\d{1,3})$")
    DEST_NAME_CMD = re.compile(r"^\.RD(\d{1,3})$")
    LEVEL_INFO_CMD = re.compile(r"^\.LV(\d+),([-A-Z0-9]*)$")
    LIST_CMD = re.compile(r"^\.L([A-Z])(\d{1,3}),(.*)$")
    LOCK_INQUIRE_CMD = re.compile(r"^\.BI(\d{1,3})$")

    def __init__(self, cfg: BridgeConfig, gv_controller: GVSwitchController, state: BridgeState):
        self.cfg = cfg
        self.gv = gv_controller
        self.state = state
        for level in cfg.router.levels:
            self.state.routes.setdefault(level, {})
        self.routes = self.state.routes
        self.server: Optional[asyncio.base_events.Server] = None

    def _map_source(self, source: int) -> int:
        mapped = self.cfg.mappings.source_to_input.get(source)
        if mapped is not None:
            return mapped
        return source

    def _respond(self, responses: List[str]) -> List[str]:
        logger.debug("Responding with: %s", responses)
        return responses

    async def start(self) -> None:
        self.server = await asyncio.start_server(
            self.handle_client,
            host=self.cfg.router.listen_host,
            port=self.cfg.router.listen_port,
        )
        addr = ", ".join(str(sock.getsockname()) for sock in self.server.sockets or [])
        logger.info("Quartz bridge listening on %s", addr)

    async def serve_forever(self) -> None:
        if not self.server:
            await self.start()
        assert self.server is not None
        async with self.server:
            await self.server.serve_forever()

    async def shutdown(self) -> None:
        logger.info("Shutting down Quartz bridge")
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        await self.gv.close()

    _MAX_CLIENT_BUFFER = 65536

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        peer_label = self._format_peer(peer)
        logger.info("Client connected: %s", peer_label)
        self.state.add_client(peer_label)
        buffer = ""
        try:
            while not reader.at_eof():
                data = await reader.read(1024)
                if not data:
                    break
                try:
                    buffer += data.decode("ascii")
                except UnicodeDecodeError:
                    logger.warning("Non-ASCII data from %s; ignoring", peer)
                    continue

                if len(buffer) > self._MAX_CLIENT_BUFFER:
                    logger.warning("Client %s exceeded buffer limit; disconnecting", peer_label)
                    break

                while "\r" in buffer:
                    line, buffer = buffer.split("\r", 1)
                    line = line.strip()
                    if not line:
                        continue
                    responses = await self.process_command(line)
                    if not responses:
                        continue
                    for response in responses:
                        writer.write((response + "\r").encode("ascii"))
                        await writer.drain()
        except ConnectionResetError:
            logger.info("Client reset connection: %s", peer_label)
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            self.state.remove_client(peer_label)
            logger.info("Client disconnected: %s", peer_label)

    async def process_command(self, command: str) -> Optional[List[str]]:
        logger.debug("Received command: %s", command)

        if command.startswith('.X,'):
            tokens = [token.strip().upper() for token in command[3:].split(',') if token.strip()]
            if not tokens:
                return self._respond(['.XA,QCX,NONE,NO'])

            primary = tokens[0]
            if primary == 'QCX':
                pairs: List[str] = []
                for feature in tokens[1:]:
                    pairs.extend([feature, 'NO'])
                if not pairs:
                    pairs.extend(['NONE', 'NO'])
                response = ['.XA', 'QCX', *pairs]
                return self._respond([','.join(response)])

            if primary == 'QCP':
                sources = self.cfg.router.sources or len(self.cfg.mappings.source_to_input) or 0
                destinations = self.cfg.router.destinations or len(self.cfg.mappings.dest_to_aux) or 0
                return self._respond([f".XA,QCP,{sources},{destinations}"])

            responses = []
            for feature in tokens[1:]:
                responses.append(f".XA,{feature},NO")
            if primary not in {'QCX', 'QCP'}:
                responses.insert(0, f".XA,{primary},NO")
            return self._respond(responses)

        if command == '.$IC':
            logger.info("Identification capability request received")
            return self._respond(['.$IC1'])

        match = self.SET_VECTOR_CMD.match(command)
        if match:
            level_char, dest_str, source_str = match.groups()
            dest = int(dest_str)
            source = int(source_str)
            logger.info("Status vector update: level=%s dest=%s source=%s", level_char, dest, source)

            max_dest = self.cfg.router.destinations or 96
            if dest < 1 or dest > max_dest:
                logger.warning("Vector update rejected: dest %d out of range (1-%d)", dest, max_dest)
                return self._respond([".NA"])

            max_src = self.cfg.router.sources or 0
            if max_src and (source < 1 or source > max_src):
                logger.warning("Vector update rejected: source %d out of range (1-%d)", source, max_src)
                return self._respond([".NA"])

            aux = self.cfg.mappings.dest_to_aux.get(dest, dest)
            gv_source = self._map_source(source)

            if level_char.upper() == 'V':
                try:
                    success = await self.gv.send_aux(aux, gv_source)
                except Exception as exc:
                    logger.error("GV routing failed for vector AUX %s -> %s: %s", aux, gv_source, exc)
                    self.state.set_gv_error(str(exc))
                    self.state.record_route(level_char, dest, source, aux, gv_source, 'error')
                    return self._respond([".NA"])

                if not success:
                    logger.error("GV command FAILED for vector AUX %s -> %s", aux, gv_source)
                    self.state.record_route(level_char, dest, source, aux, gv_source, 'error')
                    return self._respond([".NA"])

                self.state.record_route(level_char, dest, source, aux, gv_source, 'ok')
            else:
                self.state.record_route(level_char, dest, source, aux, gv_source, 'vector')

            return self._respond([f".UV{level_char}{dest:03d},{source:03d}"])

        match = self.ROUTE_CMD.match(command)
        if match:
            level, dest_str, source_str = match.groups()
            dest = int(dest_str)
            source = int(source_str)
            logger.info("Route request: level=%s dest=%s source=%s", level, dest, source)

            max_dest = self.cfg.router.destinations or 96
            if dest < 1 or dest > max_dest:
                logger.warning("Route rejected: dest %d out of range (1-%d)", dest, max_dest)
                return self._respond([".NA"])

            max_src = self.cfg.router.sources or 0
            if max_src and (source < 1 or source > max_src):
                logger.warning("Route rejected: source %d out of range (1-%d)", source, max_src)
                return self._respond([".NA"])

            aux = self.cfg.mappings.dest_to_aux.get(dest, dest)
            gv_source = self._map_source(source)
            status = "ok"
            try:
                success = await self.gv.send_aux(aux, gv_source)
            except Exception as exc:
                logger.error("GV routing failed for AUX %s -> %s: %s", aux, gv_source, exc)
                status = "error"
                self.state.set_gv_error(str(exc))
                self.state.record_route(level, dest, source, aux, gv_source, status)
                return self._respond([".NA"])

            if success:
                self.state.record_route(level, dest, source, aux, gv_source, status)
                return self._respond([".A"])

            status = "error"
            logger.error("GV plugin returned failure for AUX %s -> %s", aux, gv_source)
            self.state.record_route(level, dest, source, aux, gv_source, status)
            return self._respond([".NA"])


        match = self.LEVEL_INFO_CMD.match(command)
        if match:
            level_index = int(match.group(1))
            logger.info("Level info request: level_index=%s", level_index)
            if level_index == 2:
                return self._respond([
                    '.ALV2,V,A1-A32',
                    '.ALV10,V,A33-A64',
                    '.ALV18,V,A65-A96',
                    '.A'
                ])
            response = self.LEVEL_RESPONSES.get(level_index)
            if response:
                return self._respond(response)
            return self._respond([".A"])

        match = self.LIST_CMD.match(command)
        if match:
            level = match.group(1)
            start_dest = int(match.group(2))
            criteria = match.group(3).strip()
            logger.info("List request: level=%s start_dest=%s criteria=%s", level, start_dest, criteria)
            results: List[str] = []
            max_dest = self.cfg.router.destinations or max(self.state.dest_to_aux.keys() or [start_dest])
            if criteria in ('', '-'):
                dest = start_dest
                while len(results) < 8 and dest <= max_dest:
                    current = self.routes.get(level, {}).get(dest, 0)
                    results.append(f"{level}{dest:03d},{current:03d}")
                    dest += 1
            else:
                try:
                    target_source = int(criteria)
                except ValueError:
                    target_source = -1
                dest = start_dest
                while len(results) < 8 and dest <= max_dest:
                    current = self.routes.get(level, {}).get(dest, 0)
                    if current == target_source:
                        results.append(f"{level}{dest:03d},{current:03d}")
                    dest += 1
            if results:
                return self._respond([".A" + "".join(results)])
            return self._respond([".A"])


        match = self.INQUIRE_CMD.match(command)
        if match:
            level, dest_str = match.groups()
            dest = int(dest_str)
            logger.info("Route inquire: level=%s dest=%s", level, dest)
            source = self.routes.get(level, {}).get(dest, 0)
            return self._respond([f".A{level}{dest:03d},{source:03d}"])


        match = self.SOURCE_NAME_CMD.match(command)
        if match:
            src = int(match.group(1))
            logger.info("Source name request: %s", src)
            name = self.cfg.names.sources.get(src, f"SRC{src:03d}")
            # Quartz expects up to 8 chars on line 1; we leave trimming to client
            return self._respond([f".RAS{src:03d}{name}"])


        match = self.DEST_NAME_CMD.match(command)
        if match:
            dest = int(match.group(1))
            logger.info("Destination name request: %s", dest)
            name = self.cfg.names.destinations.get(dest, f"DEST{dest:03d}")
            return self._respond([f".RAD{dest:03d}{name}"])


        if command == ".QH":  # Simple heartbeat request
            logger.info("Heartbeat query received")
            return self._respond([".A"])


        match = self.LOCK_INQUIRE_CMD.match(command)
        if match:
            dest = int(match.group(1))
            logger.info("Destination lock status requested: dest=%s", dest)
            return self._respond([f".BA{dest:03d},0"])


        # Status dump request: .#01 = dump all routes for level 1 (V)
        if command.startswith('.#'):
            logger.info("Status dump request: %s", command)
            responses: List[str] = []
            max_dest = self.cfg.router.destinations or 96
            for level in self.cfg.router.levels:
                level_routes = self.routes.get(level, {})
                for dest in range(1, max_dest + 1):
                    source = level_routes.get(dest, 0)
                    if source > 0:
                        responses.append(f".UV{level}{dest:03d},{source:03d}")
            responses.append(".A")
            logger.info("Status dump: sending %d route updates", len(responses) - 1)
            return self._respond(responses)

        # Default to positive acknowledgement to keep router clients happy
        logger.info("Unhandled command %s -> default ACK", command)
        return self._respond([".A"])


    @staticmethod
    def _format_peer(peer: object) -> str:
        if not peer:
            return "unknown"
        if isinstance(peer, tuple) and len(peer) >= 2:
            return f"{peer[0]}:{peer[1]}"
        return str(peer)


class StatusHTTPServer:
    """Very small HTTP server for status/monitoring."""

    def __init__(self, cfg: HTTPConfig, state: BridgeState):
        self.cfg = cfg
        self.state = state
        self.server: Optional[asyncio.AbstractServer] = None

    async def start(self) -> None:
        if self.server:
            return
        self.server = await asyncio.start_server(
            self.handle_http,
            host=self.cfg.listen_host,
            port=self.cfg.listen_port,
        )
        addr = ", ".join(str(sock.getsockname()) for sock in self.server.sockets or [])
        logger.info("Status UI listening on %s", addr)

    async def shutdown(self) -> None:
        if not self.server:
            return
        self.server.close()
        await self.server.wait_closed()
        self.server = None
        logger.info("Status UI stopped")

    async def handle_http(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await reader.readline()
            if not request_line:
                return
            try:
                method, path, _ = request_line.decode("ascii").strip().split()
            except ValueError:
                await self._write_response(writer, "400 Bad Request", "text/plain", "Bad Request\n")
                return

            # Drain headers until blank line
            while True:
                line = await reader.readline()
                if not line or line in (b"\r\n", b"\n"):
                    break

            if method != "GET":
                await self._write_response(writer, "405 Method Not Allowed", "text/plain", "Method Not Allowed\n")
                return

            if path.startswith("/health"):
                body = json.dumps(self._build_health_snapshot(), indent=2)
                await self._write_response(writer, "200 OK", "application/json", body)
                return

            body = self._render_status_page()
            await self._write_response(writer, "200 OK", "text/html; charset=utf-8", body)

        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _write_response(self, writer: asyncio.StreamWriter, status: str, content_type: str, body: str) -> None:
        body_bytes = body.encode("utf-8")
        headers = (
            f"HTTP/1.1 {status}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body_bytes)}\r\n"
            "Cache-Control: no-cache\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii")
        writer.write(headers + body_bytes)
        await writer.drain()

    def _build_health_snapshot(self) -> Dict[str, object]:
        clients = [
            {
                "peer": peer,
                "connected_since": connected.isoformat(),
            }
            for peer, connected in sorted(self.state.clients.items())
        ]

        routes = {
            level: {
                str(dest): {
                    "source": source,
                    "aux": self.state.dest_to_aux.get(dest, dest),
                    "gv_source": self.state.source_to_input.get(source, source),
                }
                for dest, source in sorted(dest_map.items())
            }
            for level, dest_map in sorted(self.state.routes.items())
        }

        return {
            "gv": {
                "host": self.state.gv_host,
                "suite": self.state.gv_suite,
                "connected": self.state.gv_connected,
                "working_port": self.state.gv_working_port,
                "last_error": self.state.last_error,
            },
            "clients": clients,
            "routes": routes,
            "recent_commands": [record.to_dict() for record in reversed(self.state.command_log[-20:])],
            "started": self.state.start_time.isoformat(),
        }

    def _render_status_page(self) -> str:
        return '''<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>K-Frame Quartz Bridge</title>
<style>
  :root { --bg: #1a1a2e; --card: #16213e; --border: #0f3460; --ok: #4ecca3; --warn: #e94560; --muted: #8892a8; --head: #0f3460; --text: #e0e0e0; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); padding: 1.25rem; }
  h1 { font-size: 1.4rem; margin-bottom: 0.25rem; }
  .subtitle { color: var(--muted); font-size: 0.85rem; margin-bottom: 1.25rem; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 6px; padding: 1rem; }
  .card h2 { font-size: 1rem; margin-bottom: 0.6rem; display: flex; align-items: center; gap: 0.4rem; }
  .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  .dot.ok { background: var(--ok); } .dot.warn { background: var(--warn); }
  .kv { display: grid; grid-template-columns: auto 1fr; gap: 0.2rem 0.75rem; font-size: 0.85rem; }
  .kv dt { color: var(--muted); } .kv dd { font-weight: 500; }
  .full { grid-column: 1 / -1; }
  table { border-collapse: collapse; width: 100%; font-size: 0.82rem; }
  th, td { border: 1px solid var(--border); padding: 0.35rem 0.5rem; text-align: left; }
  th { background: var(--head); font-weight: 600; position: sticky; top: 0; color: var(--text); }
  .tbl-wrap { max-height: 420px; overflow-y: auto; }
  .ok-text { color: var(--ok); font-weight: 600; } .warn-text { color: var(--warn); font-weight: 600; }
  .empty { color: var(--muted); font-style: italic; padding: 0.75rem; text-align: center; }
  .pulse { animation: pulse 1s ease-in-out; }
  @keyframes pulse { 0% { background: #1a3a5c; } 100% { background: transparent; } }
  @media (max-width: 720px) { .grid { grid-template-columns: 1fr; } }
</style>
</head><body>
<h1>K-Frame Quartz Bridge</h1>
<p class="subtitle" id="subtitle">Loading...</p>

<div class="grid">
  <div class="card">
    <h2><span class="dot" id="gvDot"></span> K-Frame Connection</h2>
    <dl class="kv" id="gvInfo"></dl>
  </div>
  <div class="card">
    <h2>Quartz Clients</h2>
    <div id="clientsBody"></div>
  </div>
</div>

<div class="card full" style="margin-bottom:1rem;">
  <h2>Current Routes</h2>
  <div class="tbl-wrap">
    <table><thead><tr>
      <th>Level</th><th>Dest</th><th>AUX</th><th>AUX Label</th><th>Quartz Src</th><th>GV Source</th><th>Source Label</th>
    </tr></thead><tbody id="routesBody"></tbody></table>
  </div>
</div>

<div class="card full">
  <h2>Recent Commands</h2>
  <div class="tbl-wrap">
    <table><thead><tr>
      <th>Timestamp</th><th>Level</th><th>Dest</th><th>AUX</th><th>Quartz Src</th><th>GV Source</th><th>Status</th>
    </tr></thead><tbody id="cmdsBody"></tbody></table>
  </div>
</div>

<script>
const REFRESH_MS = 2000;
const destNames = JSON.parse(''' + json.dumps(json.dumps({str(k): v for k, v in self.state.names.destinations.items()})).replace('</', r'<\/') + ''');
const srcNames = JSON.parse(''' + json.dumps(json.dumps({str(k): v for k, v in self.state.names.sources.items()})).replace('</', r'<\/') + ''');

function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }
function fmt(iso) { try { return new Date(iso).toLocaleTimeString(); } catch { return iso; } }
function dur(iso) {
  try {
    let s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 0) s = 0;
    const d = Math.floor(s / 86400); s %= 86400;
    const h = Math.floor(s / 3600); s %= 3600;
    const m = Math.floor(s / 60); s %= 60;
    const p = [];
    if (d) p.push(d + "d");
    if (h || p.length) p.push(h + "h");
    if (m || p.length) p.push(m + "m");
    p.push(s + "s");
    return p.join(" ");
  } catch { return "?"; }
}

let prevRoutes = "";

async function refresh() {
  try {
    const r = await fetch("/health");
    if (!r.ok) return;
    const d = await r.json();

    // Subtitle
    document.getElementById("subtitle").textContent =
      "Started " + fmt(d.started) + " \\u2014 uptime " + dur(d.started);

    // GV connection
    const dot = document.getElementById("gvDot");
    dot.className = "dot " + (d.gv.connected ? "ok" : "warn");
    document.getElementById("gvInfo").innerHTML =
      "<dt>Status</dt><dd class='" + (d.gv.connected ? "ok-text" : "warn-text") + "'>" + (d.gv.connected ? "Connected" : "Disconnected") + "</dd>" +
      "<dt>Host</dt><dd>" + esc(d.gv.host) + "</dd>" +
      "<dt>Suite</dt><dd>" + esc(d.gv.suite) + "</dd>" +
      "<dt>Port</dt><dd>" + (d.gv.working_port || "n/a") + "</dd>" +
      "<dt>Last Error</dt><dd>" + (d.gv.last_error ? esc(d.gv.last_error) : "None") + "</dd>";

    // Clients
    const cb = document.getElementById("clientsBody");
    if (!d.clients.length) {
      cb.innerHTML = '<p class="empty">No active Quartz clients.</p>';
    } else {
      let h = '<table><thead><tr><th>Peer</th><th>Connected</th><th>Duration</th></tr></thead><tbody>';
      d.clients.forEach(c => {
        h += "<tr><td>" + esc(c.peer) + "</td><td>" + fmt(c.connected_since) + "</td><td>" + dur(c.connected_since) + "</td></tr>";
      });
      h += "</tbody></table>";
      cb.innerHTML = h;
    }

    // Routes
    const rb = document.getElementById("routesBody");
    const routeEntries = [];
    for (const [level, dests] of Object.entries(d.routes || {})) {
      for (const [dest, info] of Object.entries(dests)) {
        routeEntries.push([level, parseInt(dest), info]);
      }
    }
    routeEntries.sort((a, b) => a[1] - b[1]);
    const routeSig = JSON.stringify(routeEntries);
    const changed = routeSig !== prevRoutes;
    prevRoutes = routeSig;

    if (!routeEntries.length) {
      rb.innerHTML = '<tr><td colspan="7" class="empty">No routes recorded yet.</td></tr>';
    } else {
      let h = "";
      routeEntries.forEach(([level, dest, info]) => {
        const dl = destNames[String(dest)] || ("DEST" + String(dest).padStart(3, "0"));
        const sl = srcNames[String(info.source)] || ("SRC" + String(info.source).padStart(3, "0"));
        h += "<tr" + (changed ? ' class="pulse"' : "") + ">" +
          "<td>" + esc(level) + "</td>" +
          "<td>" + dest + "</td>" +
          "<td>" + info.aux + "</td>" +
          "<td>" + esc(dl) + "</td>" +
          "<td>" + info.source + "</td>" +
          "<td>" + info.gv_source + "</td>" +
          "<td>" + esc(sl) + "</td></tr>";
      });
      rb.innerHTML = h;
    }

    // Commands
    const cmb = document.getElementById("cmdsBody");
    if (!d.recent_commands || !d.recent_commands.length) {
      cmb.innerHTML = '<tr><td colspan="7" class="empty">No commands processed.</td></tr>';
    } else {
      let h = "";
      d.recent_commands.forEach(c => {
        const cls = c.status === "ok" ? "ok-text" : "warn-text";
        h += "<tr><td>" + fmt(c.timestamp) + "</td>" +
          "<td>" + esc(c.level) + "</td>" +
          "<td>" + c.destination + "</td>" +
          "<td>" + c.aux + "</td>" +
          "<td>" + c.source + "</td>" +
          "<td>" + c.gv_source + "</td>" +
          "<td class='" + cls + "'>" + esc(c.status) + "</td></tr>";
      });
      cmb.innerHTML = h;
    }
  } catch (e) { console.error("Refresh failed:", e); }
}

refresh();
setInterval(refresh, REFRESH_MS);
</script>
</body></html>'''



async def bridge_main(cfg: Optional[BridgeConfig] = None) -> None:
    """Main entry point for the bridge. Accepts an optional pre-built config."""
    if cfg is None:
        cfg = BridgeConfig.from_env()

    state = BridgeState(
        gv_host=cfg.gv.host,
        gv_suite=cfg.gv.suite,
        dest_to_aux=dict(cfg.mappings.dest_to_aux),
        source_to_input=dict(cfg.mappings.source_to_input),
        names=cfg.names,
    )
    gv_controller = GVSwitchController(cfg.gv, cfg.router, state)
    server = QuartzRouterServer(cfg, gv_controller, state)
    http_server = StatusHTTPServer(cfg.http, state)

    stop_event = asyncio.Event()

    def _signal_handler(*_: object) -> None:
        logger.info("Signal received, shutting down")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, _signal_handler)

    await server.start()
    await http_server.start()

    try:
        await gv_controller.ensure_connection()
        logger.info("Initial GV connection established to %s", cfg.gv.host)
    except Exception as exc:
        logger.warning("Initial GV connection attempt failed: %s (reconnection task will retry)", exc)

    reconnect_task = asyncio.create_task(
        gv_controller.reconnection_loop(stop_event),
        name="gv-reconnect",
    )

    await stop_event.wait()

    reconnect_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await reconnect_task

    await asyncio.gather(server.shutdown(), http_server.shutdown())


if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("K_FRAME_QUARTZ_BRIDGE_LOG", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        asyncio.run(bridge_main())
    except KeyboardInterrupt:
        pass
