# Building the AJA FS Emulator VirtualBox Appliance

Two build scripts are provided:

| Script | Target | Build machine |
|--------|--------|---------------|
| `build.sh` | ARM64 (Apple Silicon Macs) | macOS ARM |
| `build-x86.sh` | x86_64 (Intel/AMD, Windows) | Linux x86_64 or Windows (MSYS2) |

## Prerequisites

### ARM64 (macOS)

```bash
brew install qemu sshpass
# expect is included with macOS
# VirtualBox: download from virtualbox.org
```

### x86_64 (Linux)

```bash
sudo apt install qemu-system-x86 qemu-utils virtualbox expect sshpass curl python3
```

### x86_64 (Windows)

Requires MSYS2 with: `qemu`, `expect`, `sshpass`, `curl`. VirtualBox must be installed separately.

## Build

```bash
cd virtualbox

# ARM64 Mac:
bash build.sh

# x86_64 Linux/Windows:
bash build-x86.sh
```

Output: `output/fs-emu-aarch64.ova` or `output/fs-emu-x86_64.ova` (~100-120MB).

Build takes ~5-10 minutes with hardware acceleration, longer without.

If the build fails, check for stale QEMU processes holding port 2222:
```bash
lsof -ti :2222 | xargs kill
```

### How it works

Both scripts use a three-phase approach:

1. **QEMU install** — Boot Alpine Linux ISO in QEMU with serial console, automate installation via `expect`
2. **SSH provision** — Reboot the installed system, copy app files and run provisioning via SSH (installs Python, Flask, qemu-system-ppc, e2fsprogs)
3. **VBox export** — Convert disk to VDI, create VirtualBox VM with NAT port forwarding, export as OVA

The ARM build requires EFI (GRUB), while x86 uses simpler BIOS boot. The `build-x86.sh` script also handles Windows/MSYS2 with WHPX or TCG acceleration fallback.

## Usage

### For end-users (just the .ova file)

1. Install [VirtualBox](https://www.virtualbox.org/wiki/Downloads)
2. Double-click the `.ova` to import (or File > Import Appliance)
3. Start the VM (headless recommended)
4. Open http://localhost:5050/ in your browser
5. Upload an AJA firmware `.bin` file (FS-HDR, FS4, or FS2) — the emulator starts automatically
6. The device web UI will be at http://localhost:19080/

### Port Mapping

| Host Port | VM Port | Purpose |
|-----------|---------|---------|
| 5050 | 5050 | Flask control panel |
| 19080 | 19080 | Device web UI (via QEMU) |
| 18080 | 18080 | Fallback httpd (via QEMU) |
| 2222 | 22 | SSH (for debugging) |

### SSH Access

```bash
ssh -p 2222 root@localhost    # password: fshdr
```

### Stopping

Power off the VM from VirtualBox. All data (uploaded firmware, saved configuration)
persists inside the VM disk and will be available on next start.

### Factory Reset

Use the "Factory Reset" button in the control panel, or delete and re-import the OVA.

## Files

```
virtualbox/
+-- build.sh              # ARM64 build script
+-- build-x86.sh          # x86_64 build script (Linux + Windows)
+-- provision.sh           # ARM provisioning (runs inside VM)
+-- provision-x86.sh       # x86 provisioning (runs inside VM)
+-- fs-emu.initd           # OpenRC service file
+-- http/
|   +-- answers            # Alpine autoinstall answers file
|   +-- fix.sh             # Post-install SSH fixup
|   +-- setup.sh           # Setup helper
+-- output/                # Built OVA files (gitignored)
```
