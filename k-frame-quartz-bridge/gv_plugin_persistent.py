#!/usr/bin/env python3
"""
GV Plugin Persistent Connection - Keeps connection alive with heartbeats

Special thanks to Brad Shaffer, @orthicon
"""

import socket
import struct
import time
import random
import threading
import signal
import sys
from typing import Optional, Callable, List, Tuple

class GVPluginPersistent:
    """Persistent connection with heartbeat maintenance"""

    def __init__(
        self,
        target_ip: str = "127.0.0.1",
        suite: str = "suite1a",
        bind_host: str = "127.0.0.1",
        message_callback: Optional[Callable[[bytes], None]] = None,
        protocol: str = "auto",
    ):
        self.target_ip = target_ip
        self.suite = suite
        self.bind_host = bind_host
        self.main_client_socket = None
        self.listener_socket = None
        self.connected = False
        self.working_port = 0
        self.running = False
        self.heartbeat_thread = None
        self.listener_thread = None
        self.message_callback = message_callback
        self.protocol_preference = (protocol or "auto").lower()
        self.protocol = None  # "udp" or "tcp"
        self._tcp_buffer = bytearray()
        self._tcp_fake_counter = 0

        # Heartbeat packets from plugin analysis
        self.HEARTBEAT_REQ = bytes([0x00, 0x01, 0x00, 0x00])
        self.HEARTBEAT_RESP = bytes([0x00, 0x02, 0x00, 0x00])

        self.SESSION_HEADER = bytes.fromhex("b9916f84")
        self.SESSION_TRAILER = bytes.fromhex("3762c5d9")

        # All packet definitions (same as before)
        self.PACKETS = {
            'P1': bytes([0x00, 0x06, 0x00, 0x00]),
            'P2': bytes([0x00, 0x02, 0x00, 0x00]),
            'P3': bytes([0x00, 0x01, 0x00, 0x00]),
            'P4': bytes([0x00, 0x02, 0x00, 0x00]),
            'P5': bytes.fromhex('000400010002001f0000000b0000002c00010000636c69656e7400'),
            'P6': bytes([0x00, 0x02, 0x00, 0x01]),
            'P7': bytes([0x00, 0x01, 0x00, 0x00]),
            'P8': bytes([0x00, 0x02, 0x00, 0x00]),
            'P9_ACK': bytes([0x00, 0x02, 0x00, 0x01]),
            'P12': bytes([0x00, 0x06, 0x00, 0x00]),
            'P13': bytes([0x00, 0x02, 0x00, 0x00]),
            'P14': bytes([0x00, 0x01, 0x00, 0x00]),
            'P15': bytes([0x00, 0x02, 0x00, 0x00]),
            'P16_PREFIX': bytes.fromhex('000400010002001f0000000b0000002c'),
            'P16_SUFFIX': bytes.fromhex('636c69656e7400'),
            'P17': bytes([0x00, 0x02, 0x00, 0x01]),
        }

        # Suite commands
        self.SUITE_COMMANDS = {
            'suite1a': [
                bytes.fromhex('0004017c000200060000000c0000001417960200010000070000000a'),
                bytes.fromhex('000407a700020005000000090000001004b600000100000700'),
            ],
            'suite1b': [
                bytes.fromhex('0004017c000200060000000c0000001417960200010000070000000b'),
                bytes.fromhex('000407a700020005000000090000001004b600000100000700'),
            ],
            'suite2a': [
                bytes.fromhex('0004017a000200060000000c0000001417960200010000070000000c'),
                bytes.fromhex('000407a700020005000000090000001004b600000100000700'),
            ],
            'suite2b': [
                bytes.fromhex('0004017a000200060000000c0000001417960200010000070000000d'),
                bytes.fromhex('000407a700020005000000090000001004b600000100000700'),
            ],
            'suite3a': [
                bytes.fromhex('0004017e000200060000000c0000001417960200010000070000000e'),
                bytes.fromhex('000407ab00020005000000090000001004b600000100000700'),
            ],
            'suite3b': [
                bytes.fromhex('0004017e000200060000000c0000001417960200010000070000000f'),
                bytes.fromhex('000407ab00020005000000090000001004b600000100000700'),
            ],
            'suite4a': [
                bytes.fromhex('000401f7000200060000000c00000014179602000100000700000010'),
                bytes.fromhex('000407ab00020005000000090000001004b600000100000700'),
            ],
            'suite4b': [
                bytes.fromhex('00040232000200060000000c00000014179602000100000700000011'),
                bytes.fromhex('000407ab00020005000000090000001004b600000100000700'),
            ],
        }

    def create_sockets(self) -> bool:
        """Create and bind UDP sockets"""
        try:
            self.main_client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.main_client_socket.bind((self.bind_host, 6130))
            print(f"Main Client bound to {self.bind_host}:6130 (TRANSMIT)")

            self.listener_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.listener_socket.bind((self.bind_host, 6131))
            print(f"Listener Client bound to {self.bind_host}:6131 (RECEIVE)")

            self.main_client_socket.settimeout(15.0)
            self.listener_socket.settimeout(15.0)
            return True

        except Exception as e:
            print(f"Error creating sockets: {e}")
            return False

    def send_packet(self, socket, packet, port, label):
        """Send packet with logging"""
        try:
            bytes_sent = socket.sendto(packet, (self.target_ip, port))
            print(f"[{label}] Sent to {self.target_ip}:{port} ({packet.hex().upper()})")
            return True
        except Exception as e:
            print(f"Failed to send {label}: {e}")
            return False

    def _close_sockets(self) -> None:
        """Close and clear both sockets (safe to call when partially created)."""
        for attr in ("main_client_socket", "listener_socket"):
            sock = getattr(self, attr, None)
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
                setattr(self, attr, None)

    def _perform_udp_handshake(self) -> bool:
        """Complete UDP (V14) handshake"""
        print(f"[Handshake] Starting handshake with {self.target_ip}")

        if not self.create_sockets():
            return False

        success = False
        try:
            # P1 -> P2
            if not self.send_packet(self.main_client_socket, self.PACKETS['P1'], 5000, 'P1'):
                return False

            response, addr = self.main_client_socket.recvfrom(1024)
            if addr[1] == 5000 and response == self.PACKETS['P2']:
                print(f"[Handshake] Received P2")
                # P3 -> P4
                if not self.send_packet(self.main_client_socket, self.PACKETS['P3'], 5000, 'P3'):
                    return False
            else:
                return False

            response, addr = self.main_client_socket.recvfrom(1024)
            if addr[1] == 5000 and response == self.PACKETS['P4']:
                print(f"[Handshake] Received P4")
                # P5 -> P6
                if not self.send_packet(self.main_client_socket, self.PACKETS['P5'], 5000, 'P5'):
                    return False
            else:
                return False

            response, addr = self.main_client_socket.recvfrom(1024)
            if addr[1] == 5000 and response == self.PACKETS['P6']:
                print(f"[Handshake] Received P6")
            else:
                return False

            # Handle P7 and port announcement
            print("[Handshake] Waiting for P7 and port announcement...")

            while True:
                response, addr = self.listener_socket.recvfrom(1024)

                if addr[1] != 5001:
                    continue

                if response == self.PACKETS['P7']:
                    print(f"[Handshake] Received P7")
                    self.send_packet(self.listener_socket, self.PACKETS['P8'], addr[1], 'P8')
                    continue

                if len(response) >= 20:
                    port_candidate = struct.unpack('>H', response[18:20])[0]
                    if 0 < port_candidate < 65536:
                        self.working_port = port_candidate
                        print(f"[Handshake] Port announcement: {port_candidate}")

                        # Send P9 ACK
                        self.send_packet(self.listener_socket, self.PACKETS['P9_ACK'], addr[1], 'P9_ACK')

                        # Send P12 to working port
                        self.send_packet(self.main_client_socket, self.PACKETS['P12'], self.working_port, 'P12')
                        break

            # Complete handshake P13-P17
            response, addr = self.main_client_socket.recvfrom(1024)
            if response == self.PACKETS['P13']:
                print(f"[Handshake] Received P13")
                self.send_packet(self.main_client_socket, self.PACKETS['P14'], self.working_port, 'P14')

            response, addr = self.main_client_socket.recvfrom(1024)
            if response == self.PACKETS['P15']:
                print(f"[Handshake] Received P15")
                # Build P16
                sequence_buf = struct.pack('>H', 3)
                packet16 = self.PACKETS['P16_PREFIX'] + sequence_buf + bytes(2) + self.PACKETS['P16_SUFFIX']
                self.send_packet(self.main_client_socket, packet16, self.working_port, 'P16')

            response, addr = self.main_client_socket.recvfrom(1024)
            if response == self.PACKETS['P17']:
                print(f"[Handshake] Received P17 - Handshake complete!")

                # Send suite commands
                self.protocol = "udp"
                self.send_suite_command()
                success = True
                return True

            return False

        except Exception as e:
            print(f"[Handshake] Error: {e}")
            return False
        finally:
            if not success:
                self._close_sockets()
                self.working_port = 0
                self.protocol = None

    def _perform_tcp_handshake(self) -> bool:
        """Attempt TCP (V18+) handshake."""
        print(f"[Handshake] Attempting TCP session with {self.target_ip}:5000")
        try:
            tcp_sock = socket.create_connection((self.target_ip, 5000), timeout=2.0)
        except OSError as exc:
            print(f"[Handshake] TCP connect failed: {exc}")
            return False

        tcp_sock.settimeout(5.0)
        self.main_client_socket = tcp_sock
        self.protocol = "tcp"
        self.working_port = 5000
        self._tcp_buffer = bytearray()
        self._tcp_fake_counter = 0

        success = False
        try:
            if not self._tcp_send_payload(self._tcp_auth_payload(seq=0x0001), label="TCP-AUTH1"):
                return False

            if not self._tcp_wait_for_payload(timeout=5.0):
                print("[Handshake] No response to TCP auth packet 1")
                return False

            time.sleep(0.5)
            if not self._tcp_send_payload(self._tcp_auth_payload(seq=0x0003), label="TCP-AUTH3"):
                return False
            self._tcp_wait_for_payload(timeout=1.0)

            registration = self._tcp_subscribe(
                sub_id=0x0005,
                flags=b'\x00\x00\x00\x03\x00\x01\x00\x02\x00\x00',
                sig_and_params=b'\x11\xe5\x00\x00\x22\x00\x00\x00',
            )
            self._tcp_send_payload(registration, label="TCP-REG11E5")
            self._tcp_wait_for_payload(timeout=1.0)

            print("[Handshake] TCP authentication complete")
            self.send_suite_command()
            success = True
            return True
        finally:
            if not success:
                if self.main_client_socket:
                    try:
                        self.main_client_socket.close()
                    except OSError:
                        pass
                self.main_client_socket = None
                self.protocol = None
                self.working_port = 0
                self._tcp_buffer = bytearray()
        # no finally block, because success already returned

    def send_suite_command(self):
        """Send suite command after handshake"""
        suite = self.SUITE_COMMANDS.get(self.suite)
        if not suite:
            print(f"Unknown suite '{self.suite}'")
            return

        for i, buf in enumerate(suite):
            time.sleep(i * 0.1)
            if self.protocol == "tcp":
                payload = self._strip_udp_header(buf)
                self._tcp_send_payload(payload, label=f'Suite-{i+1}-TCP')
            else:
                self.send_packet(self.main_client_socket, buf, self.working_port, f'Suite-{i+1}')

    def _strip_udp_header(self, packet: bytes) -> bytes:
        if len(packet) >= 4 and packet[0] == 0x00 and packet[1] in (0x02, 0x04, 0x06):
            return packet[4:]
        return packet

    def _prepend_udp_header(self, payload: bytes) -> bytes:
        self._tcp_fake_counter = (self._tcp_fake_counter + 1) & 0xFFFF
        return b'\x00\x04' + struct.pack('>H', self._tcp_fake_counter) + payload

    def _tcp_wrap(self, payload: bytes) -> bytes:
        return (
            self.SESSION_HEADER
            + struct.pack('>H', len(payload))
            + payload
            + self.SESSION_TRAILER
        )

    def _tcp_auth_payload(self, seq: int, client_id: int = 0) -> bytes:
        payload = b'\x00\x02\x00\x1f\x00\x00\x00\x0b\x00\x00\x00\x2c'
        payload += struct.pack('>H', seq & 0xFFFF)
        payload += struct.pack('>H', client_id & 0xFFFF)
        payload += b'client\x00'
        return payload

    def _tcp_subscribe(self, sub_id: int, flags: bytes, sig_and_params: bytes) -> bytes:
        payload = b'\x00\x02\x00\x08'
        payload += b'\x00\x00\x00\x24'
        payload += b'\x00\x00\x00\x2e'
        payload += b'\x00' * 16
        payload += struct.pack('>H', sub_id & 0xFFFF)
        payload += flags
        payload += sig_and_params
        return payload

    def _tcp_send_payload(self, payload: bytes, label: str = "TCP") -> bool:
        if not self.main_client_socket:
            print(f"[{label}] TCP socket not available")
            return False
        frame = self._tcp_wrap(payload)
        try:
            self.main_client_socket.sendall(frame)
            print(f"[{label}] TCP payload sent ({len(frame)} bytes)")
            return True
        except OSError as exc:
            print(f"[{label}] TCP send failed: {exc}")
            return False

    def _tcp_drain_frames(self) -> List[bytes]:
        frames: List[bytes] = []
        buffer = self._tcp_buffer
        while True:
            header_index = buffer.find(self.SESSION_HEADER)
            if header_index == -1:
                buffer.clear()
                break
            if len(buffer) < header_index + 6:
                if header_index > 0:
                    del buffer[:header_index]
                break
            length = struct.unpack('>H', buffer[header_index + 4:header_index + 6])[0]
            frame_end = header_index + 6 + length + 4
            if len(buffer) < frame_end:
                if header_index > 0:
                    del buffer[:header_index]
                break
            trailer = buffer[frame_end - 4:frame_end]
            if trailer != self.SESSION_TRAILER:
                del buffer[:header_index + 4]
                continue
            frames.append(bytes(buffer[header_index + 6:frame_end - 4]))
            del buffer[:frame_end]
        return frames

    def _tcp_wait_for_payload(self, timeout: float = 5.0) -> bool:
        if not self.main_client_socket:
            return False
        deadline = time.time() + timeout
        self.main_client_socket.settimeout(0.5)
        while time.time() < deadline:
            try:
                data = self.main_client_socket.recv(4096)
                if not data:
                    return False
                self._tcp_buffer.extend(data)
                frames = self._tcp_drain_frames()
                if frames:
                    return True
            except socket.timeout:
                continue
            except OSError as exc:
                print(f"[TCP] Receive error: {exc}")
                return False
        return False

    def _dispatch_message(self, payload: bytes) -> None:
        if self.protocol == "tcp":
            payload = self._prepend_udp_header(payload)
        if self.message_callback:
            try:
                self.message_callback(payload)
            except Exception as callback_error:
                print(f"[Recv] Callback error: {callback_error}")
        else:
            print(f"[Recv] Message: {payload.hex().upper()}")

    def _tcp_receive_loop(self) -> None:
        if not self.main_client_socket:
            return
        self.main_client_socket.settimeout(0.5)
        while self.running:
            try:
                data = self.main_client_socket.recv(65535)
                if not data:
                    print("[TCP] Connection closed by frame")
                    break
                self._tcp_buffer.extend(data)
                frames = self._tcp_drain_frames()
                for frame in frames:
                    self._dispatch_message(frame)
            except socket.timeout:
                continue
            except OSError as exc:
                print(f"[TCP] Receive exception: {exc}")
                break
        self.connected = False
        if self.running:
            print("[TCP] Receive loop stopped")

    def build_aux_command(self, aux_number: int, source_number: int) -> bytes:
        """Build aux command"""
        message_id = random.randint(0, 0xFFFF)
        message_hex = f"{message_id:04x}"
        aux_hex = f"{aux_number - 1:02x}"
        source_hex = f"{source_number:04x}"
        payload_hex = f"0004{message_hex}000200050000000c00000013007e0000190001{aux_hex}{source_hex}0001"

        print(f"[AUX] Aux {aux_number} -> Source {source_number} (ID: 0x{message_hex})")
        return bytes.fromhex(payload_hex)

    def send_aux_command(self, aux_number: int, source_number: int) -> bool:
        """Send aux command"""
        if not self.connected:
            print("[AUX] Error: Not connected")
            return False

        try:
            packet = self.build_aux_command(aux_number, source_number)
            if self.protocol == "tcp":
                payload = self._strip_udp_header(packet)
                if self._tcp_send_payload(payload, label="AUX"):
                    print("[AUX] Command sent via TCP")
                    return True
                return False

            bytes_sent = self.main_client_socket.sendto(packet, (self.target_ip, self.working_port))
            print(f"[AUX] Command sent ({bytes_sent} bytes)")
            return True
        except Exception as e:
            print(f"[AUX] Error: {e}")
            return False

    def send_raw_packet(self, payload: bytes, label: str = 'RAW') -> bool:
        if not self.connected:
            print(f'[{label}] Error: Not connected')
            return False
        try:
            if self.protocol == "tcp":
                tcp_payload = self._strip_udp_header(payload)
                return self._tcp_send_payload(tcp_payload, label=label)

            bytes_sent = self.main_client_socket.sendto(payload, (self.target_ip, self.working_port))
            print(f'[{label}] Sent ({bytes_sent} bytes)')
            return True
        except Exception as exc:
            print(f'[{label}] Error: {exc}')
            return False

    def heartbeat_loop(self):
        """Heartbeat thread to keep connection alive"""
        print("[Heartbeat] Starting heartbeat thread")
        last_heartbeat = time.time()

        try:
            while self.running:
                if self.protocol == "tcp":
                    self._tcp_receive_loop()
                    if self.running:
                        print("[Heartbeat] TCP receive loop ended, marking disconnected")
                    break

                try:
                    # Send heartbeat every 2 seconds
                    if time.time() - last_heartbeat >= 2.0:
                        self.main_client_socket.sendto(self.HEARTBEAT_REQ, (self.target_ip, self.working_port))
                        print("[Heartbeat] Request sent")
                        last_heartbeat = time.time()

                    # Check for responses (non-blocking)
                    self.main_client_socket.settimeout(0.1)
                    try:
                        response, addr = self.main_client_socket.recvfrom(4096)
                        if response == self.HEARTBEAT_RESP:
                            print("[Heartbeat] Response received")
                        else:
                            if self.message_callback:
                                try:
                                    self.message_callback(response)
                                except Exception as callback_error:
                                    print(f"[Recv] Callback error: {callback_error}")
                            else:
                                print(f"[Recv] Other message: {response.hex().upper()}")
                    except socket.timeout:
                        pass

                    time.sleep(0.1)

                except Exception as e:
                    if self.running:
                        print(f"[Heartbeat] Error: {e}")
                    break
        finally:
            self.connected = False
            self.running = False

    def _listener_receive_loop(self):
        """Listener socket receive thread (UDP only).

        Handles heartbeat ACKs and dispatches subscription data
        arriving on the listener socket (port 6131).
        """
        print("[Listener] Starting listener receive thread")
        self.listener_socket.settimeout(0.5)
        while self.running:
            try:
                data, addr = self.listener_socket.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            # Heartbeat on listener: 4-byte 0x00010000
            if len(data) == 4 and data == self.HEARTBEAT_REQ:
                self.listener_socket.sendto(self.HEARTBEAT_RESP, addr)
                continue

            # Data packet: extract sequence, send ACK, dispatch
            if len(data) > 4:
                seq = struct.unpack_from('>H', data, 2)[0]
                ack = struct.pack('>HH', 0x0002, seq)
                self.listener_socket.sendto(ack, addr)

                if self.message_callback:
                    try:
                        self.message_callback(data)
                    except Exception as callback_error:
                        print(f"[Listener] Callback error: {callback_error}")
                else:
                    print(f"[Listener] Data: {data.hex().upper()}")

        print("[Listener] Listener receive thread exited")

    def connect(self) -> bool:
        """Connect and start persistent session"""
        print("=== GV PLUGIN PERSISTENT CONNECTION ===")
        print(f"Target: {self.target_ip}")
        print(f"Suite: {self.suite}")
        print()

        handshake_attempts: List[Tuple[str, bool]] = []

        if self.protocol_preference in ("auto", "tcp"):
            tcp_ok = self._perform_tcp_handshake()
            handshake_attempts.append(("tcp", tcp_ok))
            if tcp_ok:
                self.connected = True
        if not self.connected and self.protocol_preference in ("auto", "udp"):
            udp_ok = self._perform_udp_handshake()
            handshake_attempts.append(("udp", udp_ok))
            if udp_ok:
                self.connected = True

        if self.connected:
            self.running = True
            self.connected = True
            print(f"SUCCESS: Connected to {self.target_ip}, working port: {self.working_port}")

            # Start heartbeat thread
            self.heartbeat_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
            self.heartbeat_thread.start()

            # Start listener receive thread (UDP only)
            if self.protocol == "udp" and self.listener_socket is not None:
                self.listener_thread = threading.Thread(target=self._listener_receive_loop, daemon=True)
                self.listener_thread.start()

            return True
        else:
            last_attempt = handshake_attempts[-1][0] if handshake_attempts else "none"
            print(f"FAILED: Handshake failed (last attempt: {last_attempt})")
            return False

    def disconnect(self):
        """Disconnect and fully reset state so connect() can be called again."""
        print("[Disconnect] Shutting down...")
        self.running = False
        self.connected = False

        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=2.0)
        self.heartbeat_thread = None

        if self.listener_thread and self.listener_thread.is_alive():
            self.listener_thread.join(timeout=2.0)
        self.listener_thread = None

        self._close_sockets()

        self.working_port = 0
        self.protocol = None
        self._tcp_buffer = bytearray()
        self._tcp_fake_counter = 0
        print("Disconnected")

def main():
    """Main interactive session"""
    plugin = GVPluginPersistent("127.0.0.1", "suite1a")

    # Setup signal handlers for clean shutdown
    def signal_handler(sig, frame):
        print("\nReceived interrupt signal")
        plugin.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        if plugin.connect():
            print("\n=== CONNECTION ESTABLISHED ===")
            print("Connection is now persistent with heartbeats")
            print("Commands:")
            print("  aux <aux_num> <source_num>  - Route aux to source")
            print("  status                      - Show connection status")
            print("  quit                        - Disconnect and exit")
            print("  Ctrl+C                      - Emergency exit")
            print()

            while plugin.running:
                try:
                    command = input("GV> ").strip().lower()

                    if command == 'quit':
                        break
                    elif command == 'status':
                        status = "CONNECTED" if plugin.connected else "DISCONNECTED"
                        print(f"Status: {status}, Working Port: {plugin.working_port}")
                    elif command.startswith('aux '):
                        try:
                            parts = command.split()
                            if len(parts) == 3:
                                aux_num = int(parts[1])
                                source_num = int(parts[2])
                                plugin.send_aux_command(aux_num, source_num)
                            else:
                                print("Usage: aux <aux_number> <source_number>")
                        except ValueError:
                            print("Invalid numbers. Usage: aux <aux_number> <source_number>")
                    elif command == '':
                        continue
                    else:
                        print("Unknown command. Type 'quit' to exit.")

                except EOFError:
                    break
                except KeyboardInterrupt:
                    break

    finally:
        plugin.disconnect()

if __name__ == "__main__":
    main()
