"""QEMU process lifecycle management for the AJA FS emulator."""

import os
import sys
import shutil
import socket
import subprocess
import threading
import time

import config


class QemuManager:
    """Manages a single QEMU ppce500 instance.

    Serial console is exposed via TCP (-serial tcp:...) for both
    boot log capture and guest command injection.
    """

    def __init__(self):
        self.process = None
        self.boot_log = []
        self.state = "stopped"  # stopped, starting, running, error
        self._log_thread = None
        self._monitor_thread = None
        self._lock = threading.Lock()
        self._start_time = None
        self._current_config = {}
        self._serial_sock = None
        self._serial_lock = threading.Lock()
        self._serial_port = config.DEFAULT_SERIAL_PORT

    def adopt_existing(self, web_port=None, fallback_port=None, serial_port=None,
                       initrd=None):
        """Try to adopt an already-running QEMU process (e.g. after Flask restart).

        Connects to the serial port to verify QEMU is alive, then sets state
        to 'running' so the admin panel reflects reality.  Returns True if
        a running instance was found and adopted.
        """
        serial_port = serial_port or config.DEFAULT_SERIAL_PORT
        web_port = web_port or config.DEFAULT_WEB_PORT
        fallback_port = fallback_port or config.DEFAULT_FALLBACK_PORT

        # Quick probe: can we connect to the serial TCP port?
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        try:
            sock.connect(("127.0.0.1", serial_port))
        except (ConnectionRefusedError, OSError):
            sock.close()
            return False

        # Serial port is open — QEMU is running
        with self._lock:
            self.state = "running"
            self._start_time = time.time()
            self._serial_port = serial_port
            self._current_config = {
                "web_port": web_port,
                "fallback_port": fallback_port,
                "serial_port": serial_port,
                "initrd": initrd,
            }

        self._serial_sock = sock
        sock.settimeout(1.0)

        # Start serial capture thread (reads ongoing output)
        self._log_thread = threading.Thread(
            target=self._read_serial_loop, daemon=True
        )
        self._log_thread.start()

        return True

    def _read_serial_loop(self):
        """Read from an already-connected serial socket (used by adopt)."""
        sock = self._serial_sock
        if not sock:
            return
        buf = b""
        try:
            while True:
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line_bytes, buf = buf.split(b"\n", 1)
                        line = line_bytes.decode("utf-8", errors="replace").rstrip("\r")
                        with self._lock:
                            self.boot_log.append(line)
                            if len(self.boot_log) > config.MAX_LOG_LINES:
                                self.boot_log = self.boot_log[-config.MAX_LOG_LINES:]
                except socket.timeout:
                    continue
                except (IOError, OSError):
                    break
        except Exception:
            pass

    def start(self, initrd, web_port=None, fallback_port=None, serial_port=None):
        """Launch QEMU with the given initramfs and port configuration."""
        with self._lock:
            if self.state in ("starting", "running"):
                raise RuntimeError("Emulator is already running")

        kernel = config.KERNEL_FILE
        dtb = config.DTB_FILE

        if not os.path.isfile(kernel):
            raise FileNotFoundError("Kernel not found: %s" % kernel)
        if not os.path.isfile(initrd):
            raise FileNotFoundError("Initramfs not found: %s" % initrd)

        web_port = web_port or config.DEFAULT_WEB_PORT
        fallback_port = fallback_port or config.DEFAULT_FALLBACK_PORT
        serial_port = serial_port or config.DEFAULT_SERIAL_PORT
        self._serial_port = serial_port

        qemu_bin = self._find_qemu()

        cmd = [
            qemu_bin,
            "-M", "ppce500",
            "-cpu", "e500v2",
            "-m", "768",
            "-kernel", kernel,
            "-initrd", initrd,
            "-display", "none",
            "-no-reboot",
            "-serial", "tcp:127.0.0.1:%d,server,nowait" % serial_port,
            "-monitor", "none",
            "-netdev", "user,id=net0,"
                       "hostfwd=tcp::%d-:80,"
                       "hostfwd=tcp::%d-:8080" % (web_port, fallback_port),
            "-device", "e1000,netdev=net0,romfile=",
        ]

        if os.path.isfile(dtb):
            cmd.extend(["-dtb", dtb])

        with self._lock:
            self.boot_log = []
            self.state = "starting"
            self._start_time = time.time()
            self._current_config = {
                "web_port": web_port,
                "fallback_port": fallback_port,
                "serial_port": serial_port,
                "initrd": initrd,
            }

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )

        # Start thread to connect to serial port and capture boot log
        self._log_thread = threading.Thread(
            target=self._capture_serial_output, daemon=True
        )
        self._log_thread.start()

        # Start thread to monitor process health
        self._monitor_thread = threading.Thread(
            target=self._monitor_process, daemon=True
        )
        self._monitor_thread.start()

    def stop(self):
        """Stop the QEMU process (handles both managed and adopted instances)."""
        # Close serial socket first
        if self._serial_sock:
            try:
                self._serial_sock.close()
            except Exception:
                pass
            self._serial_sock = None

        proc = self.process
        if proc is not None:
            if sys.platform == "win32":
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(proc.pid)],
                        capture_output=True,
                    )
                except Exception:
                    proc.kill()
            else:
                try:
                    proc.terminate()
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        elif self.state == "running":
            # Adopted process — no Popen handle, kill by name
            subprocess.run(
                ["pkill", "-f", "qemu-system-ppc.*ppce500"],
                capture_output=True,
            )

        with self._lock:
            self.process = None
            self.state = "stopped"
            self._start_time = None

    def restart(self, **kwargs):
        """Stop then start with same or updated parameters."""
        old_config = self._current_config.copy()
        self.stop()
        time.sleep(1)

        initrd = kwargs.get("initrd", old_config.get("initrd"))
        if not initrd:
            raise RuntimeError("No initramfs configured")

        self.start(
            initrd=initrd,
            web_port=kwargs.get("web_port", old_config.get("web_port")),
            fallback_port=kwargs.get("fallback_port", old_config.get("fallback_port")),
            serial_port=kwargs.get("serial_port", old_config.get("serial_port")),
        )

    def send_raw(self, command):
        """Send a command to the guest shell without waiting for output.

        Fire-and-forget — useful for config_cli -set calls where we don't
        need the response.  Much faster than send_command() since it skips
        marker injection and log scanning.
        """
        if self.state != "running" and not self.is_running():
            raise RuntimeError("Emulator is not running")
        if not self._serial_sock:
            raise RuntimeError("Serial console not connected. Wait for boot.")
        with self._serial_lock:
            try:
                self._serial_sock.sendall(("%s\n" % command).encode())
            except (BrokenPipeError, OSError):
                raise RuntimeError("Lost connection to emulator")

    def send_command(self, command, timeout=30.0):
        """Send a command to the guest shell via TCP serial and capture output."""
        if self.state != "running" and not self.is_running():
            raise RuntimeError("Emulator is not running")
        if not self._serial_sock:
            raise RuntimeError("Serial console not connected. Wait for boot.")

        import uuid
        marker_id = uuid.uuid4().hex[:12]
        start_marker = "===S_%s===" % marker_id
        end_marker = "===E_%s===" % marker_id

        with self._serial_lock:
            try:
                # Send all three lines in one burst — the serial buffer and
                # shell line discipline handle them sequentially.
                payload = "echo '%s'\n%s\necho '%s'\n" % (
                    start_marker, command, end_marker)
                self._serial_sock.sendall(payload.encode())
            except (BrokenPipeError, OSError):
                raise RuntimeError("Lost connection to emulator")

        # Wait for the end marker to appear as a STANDALONE line in the log.
        # The terminal echoes typed characters back immediately (e.g. the line
        # "echo '===E_xxx==='" appears in output while the command is still
        # running).  We must only match the actual echo output — a line whose
        # stripped content is exactly the marker string.
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                log_lines = list(self.boot_log[-500:])

            # Scan for markers as standalone lines
            start_line = None
            end_line = None
            for idx, line in enumerate(log_lines):
                s = line.strip()
                if s == start_marker and start_line is None:
                    start_line = idx
                if s == end_marker:
                    end_line = idx

            if start_line is not None and end_line is not None and end_line > start_line:
                content_lines = log_lines[start_line + 1:end_line]
                filtered = []
                for line in content_lines:
                    s = line.strip()
                    if not s:
                        continue
                    if s.startswith("echo '==="):
                        continue
                    if s == command.strip():
                        continue
                    filtered.append(line)
                return "\n".join(filtered)

            time.sleep(0.15)

        raise RuntimeError("Command timed out after %ds" % int(timeout))

    def is_running(self):
        if self.process is not None:
            return self.process.poll() is None
        # Adopted process — no Popen handle; trust state + serial socket
        return self.state == "running" and self._serial_sock is not None

    def get_log(self, last_n=0):
        with self._lock:
            if last_n > 0:
                return list(self.boot_log[-last_n:])
            return list(self.boot_log)

    def get_uptime(self):
        if self._start_time and self.state in ("starting", "running"):
            return int(time.time() - self._start_time)
        return None

    def get_config(self):
        return dict(self._current_config)

    def _capture_serial_output(self):
        """Connect to QEMU's TCP serial port and capture boot output."""
        # Retry connecting for up to 30 seconds (QEMU needs time to start)
        sock = None
        for _ in range(60):
            if not self.is_running():
                return
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                sock.connect(("127.0.0.1", self._serial_port))
                break
            except (ConnectionRefusedError, OSError):
                try:
                    sock.close()
                except Exception:
                    pass
                sock = None
                time.sleep(0.5)

        if not sock:
            with self._lock:
                self.boot_log.append("[fs-emu] Failed to connect to serial console")
            return

        self._serial_sock = sock
        buf = b""

        try:
            sock.settimeout(1.0)
            while self.is_running():
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line_bytes, buf = buf.split(b"\n", 1)
                        line = line_bytes.decode("utf-8", errors="replace").rstrip("\r")
                        with self._lock:
                            self.boot_log.append(line)
                            if len(self.boot_log) > config.MAX_LOG_LINES:
                                self.boot_log = self.boot_log[-config.MAX_LOG_LINES:]
                            if "Web UI:" in line and self.state == "starting":
                                self.state = "running"
                except socket.timeout:
                    continue
                except (IOError, OSError):
                    break
        except Exception:
            pass

    def _monitor_process(self):
        """Monitor QEMU process health."""
        while self.is_running():
            time.sleep(2)
        with self._lock:
            if self.state == "starting":
                self.state = "error"
            elif self.state == "running":
                self.state = "stopped"
            self.process = None

    def _find_qemu(self):
        found = shutil.which(config.QEMU_BINARY)
        if found:
            return found

        candidates = []
        if sys.platform == "darwin":
            candidates = [
                "/opt/homebrew/bin/qemu-system-ppc",
                "/usr/local/bin/qemu-system-ppc",
            ]
        elif sys.platform == "win32":
            candidates = [
                r"C:\Program Files\qemu\qemu-system-ppc.exe",
                r"C:\Program Files (x86)\qemu\qemu-system-ppc.exe",
            ]
        else:
            candidates = [
                "/usr/bin/qemu-system-ppc",
                "/usr/local/bin/qemu-system-ppc",
            ]

        for path in candidates:
            if os.path.isfile(path):
                return path

        raise FileNotFoundError(
            "qemu-system-ppc not found. Install QEMU:\n"
            "  macOS: brew install qemu\n"
            "  Linux: apt install qemu-system-ppc\n"
            "  Windows: choco install qemu"
        )
