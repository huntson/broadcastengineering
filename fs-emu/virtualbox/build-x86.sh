#!/bin/bash
# Build fs-emu VirtualBox OVA appliance — x86_64 version
#
# Run this on an x86_64 Linux or Windows machine with:
#   qemu-system-x86_64, qemu-img, VBoxManage, expect, sshpass
#
# On Ubuntu/Debian: apt install qemu-system-x86 qemu-utils virtualbox expect sshpass
# On Fedora/RHEL:   dnf install qemu-system-x86 qemu-img VirtualBox expect sshpass
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
VM_NAME="fs-emu"
OUTPUT_DIR="$SCRIPT_DIR/output"
BUILD_DIR="$SCRIPT_DIR/.build"
ISO_URL="https://dl-cdn.alpinelinux.org/alpine/v3.21/releases/x86_64/alpine-virt-3.21.6-x86_64.iso"
ISO_SHA="f19e1e35ebae247b11d0499ea6cf59991fb0c01d836bd84b83064334349bf936"
ISO_FILE="$SCRIPT_DIR/alpine-virt-3.21.6-x86_64.iso"
DISK_IMG="$BUILD_DIR/disk.qcow2"
SSH_PASS="fshdr"
SSH_PORT=2222

die() { echo "ERROR: $1" >&2; exit 1; }

# ─── Platform detection ────────────────────────────────────────────────────
IS_WINDOWS=false
QEMU_ACCEL="-enable-kvm"
if [[ "$(uname -s)" == MINGW* ]] || [[ "$(uname -s)" == MSYS* ]] || [[ "$(uname -s)" == CYGWIN* ]]; then
    IS_WINDOWS=true
    # Add MSYS2 tools and VirtualBox to PATH
    export PATH="/c/msys64/mingw64/bin:/c/msys64/usr/bin:/c/Program Files/Oracle/VirtualBox:$PATH"
    # Use WHPX if available, otherwise fall back to TCG
    if qemu-system-x86_64 -accel help 2>&1 | grep -q whpx; then
        QEMU_ACCEL="-accel whpx,kernel-irqchip=off"
        echo "Using WHPX acceleration"
    else
        QEMU_ACCEL="-accel tcg"
        echo "Using TCG software emulation (slower)"
    fi
fi

ssh_cmd() {
    sshpass -p "$SSH_PASS" ssh \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR \
        -p "$SSH_PORT" root@127.0.0.1 "$@"
}

scp_cmd() {
    sshpass -p "$SSH_PASS" scp \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR \
        -P "$SSH_PORT" "$@"
}

# ─── Prerequisites ──────────────────────────────────────────────────────────
for cmd in qemu-system-x86_64 qemu-img VBoxManage expect sshpass; do
    command -v "$cmd" >/dev/null || die "$cmd not found"
done

# ─── Download ISO ───────────────────────────────────────────────────────────
echo "=== Downloading Alpine x86_64 ISO ==="
if [ -f "$ISO_FILE" ]; then
    echo "ISO already cached"
else
    curl -L -o "$ISO_FILE" "$ISO_URL"
fi
# Try sha256sum (Linux) or shasum (macOS)
if command -v sha256sum >/dev/null; then
    echo "$ISO_SHA  $ISO_FILE" | sha256sum -c - || die "ISO checksum mismatch"
else
    echo "$ISO_SHA  $ISO_FILE" | shasum -a 256 -c - || die "ISO checksum mismatch"
fi

# ─── Prepare build directory ────────────────────────────────────────────────
echo "=== Preparing ==="
rm -rf "$BUILD_DIR" "$OUTPUT_DIR"
mkdir -p "$BUILD_DIR" "$OUTPUT_DIR"

qemu-img create -f qcow2 "$DISK_IMG" 4G

# ─── Phase 1: Install Alpine via QEMU + expect ─────────────────────────────
echo "=== Phase 1: Installing Alpine via QEMU ==="

# Start HTTP server to serve answers file
if $IS_WINDOWS; then
    # On Windows/MSYS2, use MSYS2's python3 or system python
    if command -v /c/msys64/mingw64/bin/python3 >/dev/null 2>&1; then
        PYTHON3=/c/msys64/mingw64/bin/python3
    else
        PYTHON3=python3
    fi
else
    PYTHON3=python3
fi
$PYTHON3 -m http.server 8099 --directory "$SCRIPT_DIR/http" &>/dev/null &
HTTP_PID=$!
trap "kill $HTTP_PID 2>/dev/null || true" EXIT

# Create expect script for automated Alpine installation
# x86 uses BIOS boot — much simpler than ARM EFI
cat > "$BUILD_DIR/install.exp" << 'EXPECT_SCRIPT'
#!/usr/bin/expect -f
set timeout 600

# Slow character sending: 1 char at a time, 150ms between each
# Prevents character drops on QEMU serial console (especially Windows)
set send_slow {1 .15}

spawn qemu-system-x86_64 \
    -m 1536 -smp 2 __QEMU_ACCEL__ \
    -drive file=[lindex $argv 0],format=qcow2,if=virtio \
    -cdrom [lindex $argv 1] \
    -boot d \
    -netdev user,id=net0,hostfwd=tcp::2222-:22 \
    -device virtio-net-pci,netdev=net0 \
    -nographic

# Wait for login prompt
expect {
    "localhost login:" {}
    timeout { puts "TIMEOUT waiting for login"; exit 1 }
}
sleep 2
send -s "root\r"

# Wait for the welcome message to confirm we're logged in
expect {
    "setup-alpine" {}
    timeout { puts "TIMEOUT waiting for motd"; exit 1 }
}
sleep 3

# Set up networking
send -s "ifconfig eth0 up\r"
sleep 5
send -s "udhcpc -i eth0\r"
sleep 10

# Download answers file
send -s "wget 10.0.2.2:8099/answers -O /tmp/a\r"
sleep 10

# Run setup-alpine (split into shorter commands for serial reliability)
send -s "export ERASE_DISKS=/dev/vda\r"
sleep 3
send -s "setup-alpine -f /tmp/a\r"

# Handle password prompts
expect {
    "New password:" {}
    "password:" {}
    timeout { puts "TIMEOUT waiting for password prompt"; exit 1 }
}
sleep 1
send -s "fshdr\r"

expect {
    "Retype password:" {}
    "again:" {}
    timeout { puts "TIMEOUT waiting for password confirm"; exit 1 }
}
sleep 1
send -s "fshdr\r"

# Handle interactive prompts
expect {
    "Setup a user?" { sleep 1; send -s "no\r"; exp_continue }
    "enter a lower-case loginname" { sleep 1; send -s "no\r"; exp_continue }
    "Which SSH server?" { sleep 1; send -s "openssh\r"; exp_continue }
    "Which disk" { sleep 1; send -s "/dev/vda\r"; exp_continue }
    "How would you like" { sleep 1; send -s "sys\r"; exp_continue }
    "WARNING:" { sleep 1; send -s "y\r"; exp_continue }
    "Erase" { sleep 1; send -s "y\r"; exp_continue }
    "Installation is complete" {}
    timeout { puts "TIMEOUT waiting for installation"; exit 1 }
}
sleep 5

# Post-install: enable SSH root login via HTTP-served script
send -s "wget -qO- 10.0.2.2:8099/fix.sh|sh\r"
sleep 10

# Power off
send -s "poweroff\r"
expect {
    "reboot: System halted" {}
    "Power down" {}
    eof {}
    timeout { puts "TIMEOUT waiting for poweroff"; exit 1 }
}

puts "\n=== Alpine installation complete ==="
exit 0
EXPECT_SCRIPT

# Substitute the QEMU accelerator into the expect script
sed -i "s|__QEMU_ACCEL__|$QEMU_ACCEL|g" "$BUILD_DIR/install.exp"

echo "Running automated Alpine installation (this takes 3-5 minutes)..."
expect "$BUILD_DIR/install.exp" "$DISK_IMG" "$ISO_FILE" || die "Alpine installation failed"

# Stop HTTP server
kill $HTTP_PID 2>/dev/null || true

# ─── Phase 2: Boot installed system, provision via SSH ──────────────────────
echo ""
echo "=== Phase 2: Provisioning via SSH ==="

if $IS_WINDOWS; then
    # Windows QEMU doesn't support -daemonize; run in background
    qemu-system-x86_64 \
        -m 1536 -smp 2 $QEMU_ACCEL \
        -drive file="$DISK_IMG",format=qcow2,if=virtio \
        -netdev user,id=net0,hostfwd=tcp::${SSH_PORT}-:22 \
        -device virtio-net-pci,netdev=net0 \
        -display none &
    QEMU_PID=$!
else
    qemu-system-x86_64 \
        -m 1536 -smp 2 $QEMU_ACCEL \
        -drive file="$DISK_IMG",format=qcow2,if=virtio \
        -netdev user,id=net0,hostfwd=tcp::${SSH_PORT}-:22 \
        -device virtio-net-pci,netdev=net0 \
        -display none -daemonize
fi

echo "Waiting for SSH..."
for i in $(seq 1 40); do
    if ssh_cmd "echo SSH_OK" 2>/dev/null | grep -q SSH_OK; then
        echo "SSH connected!"
        break
    fi
    if [ "$i" -eq 40 ]; then
        die "SSH timeout"
    fi
    sleep 5
done

echo "Copying application files..."
ssh_cmd "mkdir -p /tmp/fs-emu/core /tmp/fs-emu/templates /tmp/fs-emu/static /tmp/fs-emu/assets"
scp_cmd "$APP_DIR/app.py" "$APP_DIR/config.py" "$APP_DIR/requirements.txt" root@127.0.0.1:/tmp/fs-emu/
scp_cmd -r "$APP_DIR/core" "$APP_DIR/assets" "$APP_DIR/templates" "$APP_DIR/static" root@127.0.0.1:/tmp/fs-emu/
scp_cmd "$SCRIPT_DIR/fs-emu.initd" root@127.0.0.1:/tmp/fs-emu.initd
scp_cmd "$SCRIPT_DIR/provision-x86.sh" root@127.0.0.1:/tmp/provision.sh

echo "Running provisioning script..."
ssh_cmd "sh /tmp/provision.sh"

echo "Shutting down..."
ssh_cmd "poweroff" 2>/dev/null || true
sleep 10
if $IS_WINDOWS; then
    kill $QEMU_PID 2>/dev/null || true
else
    pkill -f "qemu-system-x86_64.*disk.qcow2" 2>/dev/null || true
fi
sleep 2

# ─── Phase 3: Convert to VDI and create VirtualBox VM ──────────────────────
echo ""
echo "=== Phase 3: Creating VirtualBox VM ==="

VDI_FILE="$BUILD_DIR/disk.vdi"
qemu-img convert -f qcow2 -O vdi "$DISK_IMG" "$VDI_FILE"

# Clean up any previous VM
VBoxManage controlvm "$VM_NAME" poweroff 2>/dev/null || true
sleep 1
VBoxManage unregistervm "$VM_NAME" --delete 2>/dev/null || true

if $IS_WINDOWS; then
    WIN_HOME="${USERPROFILE:-C:\\Users\\$(whoami)}"
    VM_DIR="$(cygpath -u "$WIN_HOME")/VirtualBox VMs/$VM_NAME"
else
    VM_DIR="$HOME/VirtualBox VMs/$VM_NAME"
fi

VBoxManage createvm --name "$VM_NAME" --ostype Linux26_64 --register
cp "$VDI_FILE" "$VM_DIR/disk.vdi"

VBoxManage storagectl "$VM_NAME" --name "SATA" --add sata --controller IntelAhci --portcount 2
VBoxManage storageattach "$VM_NAME" --storagectl "SATA" --port 0 --device 0 --type hdd --medium "$VM_DIR/disk.vdi"

VBoxManage modifyvm "$VM_NAME" --memory 1536 --cpus 2
VBoxManage modifyvm "$VM_NAME" --boot1 disk --boot2 none --boot3 none --boot4 none
VBoxManage modifyvm "$VM_NAME" --graphicscontroller vmsvga --vram 16
VBoxManage modifyvm "$VM_NAME" --nic1 nat
VBoxManage modifyvm "$VM_NAME" --nat-localhostreachable1 on
VBoxManage modifyvm "$VM_NAME" --natpf1 "flask,tcp,,5050,,5050"
VBoxManage modifyvm "$VM_NAME" --natpf1 "fshdr-web,tcp,,19080,,19080"
VBoxManage modifyvm "$VM_NAME" --natpf1 "fshdr-fallback,tcp,,18080,,18080"
VBoxManage modifyvm "$VM_NAME" --natpf1 "ssh,tcp,,2222,,22"

# ─── Export OVA ─────────────────────────────────────────────────────────────
echo ""
echo "=== Exporting OVA ==="
VBoxManage export "$VM_NAME" \
    --output "$OUTPUT_DIR/fs-emu-x86_64.ova" \
    --ovf20 \
    --options manifest \
    --vsys 0 \
    --product "AJA FS Emulator" \
    --description "AJA FS-HDR/FS4/FS2 firmware emulator — upload firmware at http://localhost:5050/"

# Cleanup
VBoxManage unregistervm "$VM_NAME" --delete 2>/dev/null || true
rm -rf "$BUILD_DIR"

echo ""
echo "============================================"
echo "  OVA built: $OUTPUT_DIR/fs-emu-x86_64.ova"
echo "  Size: $(ls -lh "$OUTPUT_DIR/fs-emu-x86_64.ova" | awk '{print $5}')"
echo "============================================"
echo ""
echo "To use: Import in VirtualBox, Start VM, open http://localhost:5050/"
