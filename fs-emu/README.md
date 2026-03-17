# AJA FS Emulator Control Panel

Browser-based control panel for emulating AJA FS-series devices (FS-HDR, FS4, FS2) via QEMU.
Upload firmware, start/stop the emulator, simulate SDI input formats, and access the
device web UI — all from a single dashboard.

## Supported Devices

| Device | Product ID | Firmware Format | Inputs |
|--------|-----------|-----------------|--------|
| FS-HDR | TORU | XZ+CPIO | 8 SDI |
| FS4 | SATO | XZ+CPIO | 8 SDI |
| FS2 | FS2 | uImage+ext2 | 2 Channel |

Device type is auto-detected from the firmware file.

## Quick Start (VirtualBox)

1. Install [VirtualBox](https://www.virtualbox.org/wiki/Downloads)
2. Import the `.ova` file (double-click or File > Import Appliance)
3. Start the VM (headless recommended)
4. Open **http://localhost:5050/** in your browser
5. Upload an AJA firmware `.bin` file — the emulator starts automatically
6. Once running, click the device web UI link to access the emulated device at **http://localhost:19080/**

See [`virtualbox/README.md`](virtualbox/README.md) for building the OVA from source.

## Quick Start (manual)

Requires Python 3.8+, Flask, `qemu-system-ppc`, and `e2fsprogs` (for FS2 firmware).

```bash
pip install flask
python3 app.py
```

Open **http://localhost:5050/** and upload firmware.

## Features

- **Multi-device** — Supports FS-HDR, FS4, and FS2 with auto-detection
- **Firmware Management** — Upload `.bin` files, automatic extraction and patching
- **Emulator Controls** — Start, stop, restart with status monitoring
- **Input Simulation** — Set format per-channel or all at once (device-specific format lists pulled from firmware)
- **Reference/Genlock** — Simulate BNC reference signal when device is set to Reference BNC
- **Flash Persistence** — Save/restore device configuration across reboots
- **Boot Log** — Live boot output viewer

## Architecture

```
Browser --> Flask Control Panel (localhost:5050)
              |
              +-- Firmware Processor (XZ/CPIO or uImage/ext2 extraction + rootfs patching)
              +-- QEMU Manager (process lifecycle + TCP serial console)
              |     |
              |     +-- qemu-system-ppc (ppce500, 768MB RAM)
              |           +-- Serial: TCP :14500 (boot log + command injection)
              |           +-- Web: :19080 -> guest :80 (webd/configd)
              |           +-- Fallback: :18080 -> guest :8080 (busybox httpd)
              |
              +-- webd Client (HTTP API for device params)
              +-- Config persistence (data/config.json)
```

## API

All endpoints return JSON.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | Emulator state, firmware, device type, uptime |
| POST | `/api/firmware/upload` | Upload `.bin` file (multipart form) |
| GET | `/api/firmware/list` | Available firmware files |
| POST | `/api/firmware/select` | Select firmware by name |
| POST | `/api/firmware/delete` | Delete firmware file |
| POST | `/api/emulator/start` | Start QEMU |
| POST | `/api/emulator/stop` | Stop QEMU |
| POST | `/api/emulator/restart` | Restart QEMU |
| POST | `/api/sdi/set` | Set input formats (`{all: 33}` or `{channels: {1: 20}}`) |
| GET | `/api/reference/status` | Current genlock source (read from device) |
| POST | `/api/reference/set` | Set BNC reference format (`{format: 20}`) |
| GET | `/api/log?last=N` | Boot log lines |
| GET | `/api/formats` | Device-specific format and reference source lists |
| POST | `/api/config` | Update port settings |
| GET | `/api/flash/status` | Flash save state |
| POST | `/api/flash/save` | Save flash images from guest |
| POST | `/api/flash/reset` | Delete saved flash (factory reset) |
| POST | `/api/guest/exec` | Run shell command in guest (`{cmd: "..."}`) |

## Project Structure

```
fs-emu/
+-- app.py                       # Flask entry point + all routes
+-- config.py                    # Constants and defaults
+-- requirements.txt             # flask
+-- core/
|   +-- device_profiles.py       # Per-device config (product IDs, params, formats)
|   +-- cpio.py                  # Pure-Python CPIO newc reader/writer
|   +-- firmware_processor.py    # Extract .bin -> patch rootfs -> .cpio
|   +-- qemu_manager.py          # QEMU lifecycle, serial log, command injection
|   +-- webd_client.py           # HTTP client for webd REST API
+-- assets/                      # Bundled (kernel, DTB, init template, input_sim, stub lib)
+-- templates/                   # Jinja2 templates
+-- static/                      # CSS + JS
+-- data/                        # Runtime (config, firmware uploads, CPIO cache, flash)
+-- virtualbox/                  # VirtualBox OVA build scripts (ARM + x86)
```
