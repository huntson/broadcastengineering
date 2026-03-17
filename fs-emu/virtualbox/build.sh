#!/bin/bash
# Build fs-emu VirtualBox OVA appliance
#
# Strategy: VirtualBox ARM doesn't support keyboard input via VBoxManage,
# so we use QEMU to install Alpine to a disk image (with serial console
# automation via expect), then convert to VDI and create the VirtualBox VM.
#
# Prerequisites: qemu-system-aarch64, qemu-img, VBoxManage, expect, sshpass
# On macOS: brew install qemu sshpass; install VirtualBox from virtualbox.org
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
VM_NAME="fs-emu"
OUTPUT_DIR="$SCRIPT_DIR/output"
BUILD_DIR="$SCRIPT_DIR/.build"
ISO_URL="https://dl-cdn.alpinelinux.org/alpine/v3.21/releases/aarch64/alpine-virt-3.21.6-aarch64.iso"
ISO_SHA="7c904247973660f7bcdfad6384e37801a08be05f036405857fa4215bc8a5feaf"
ISO_FILE="$SCRIPT_DIR/alpine-virt-3.21.6-aarch64.iso"
DISK_IMG="$BUILD_DIR/disk.qcow2"
EFI_CODE="/opt/homebrew/share/qemu/edk2-aarch64-code.fd"
EFI_VARS="$BUILD_DIR/efi-vars.fd"
SSH_PASS="fshdr"
SSH_PORT=2222

die() { echo "ERROR: $1" >&2; exit 1; }

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
for cmd in qemu-system-aarch64 qemu-img VBoxManage expect sshpass; do
    command -v "$cmd" >/dev/null || die "$cmd not found"
done
[ -f "$EFI_CODE" ] || die "QEMU EFI firmware not found at $EFI_CODE"

# ─── Download ISO ───────────────────────────────────────────────────────────
echo "=== Downloading Alpine ISO ==="
if [ -f "$ISO_FILE" ]; then
    echo "ISO already cached"
else
    curl -L -o "$ISO_FILE" "$ISO_URL"
fi
echo "$ISO_SHA  $ISO_FILE" | shasum -a 256 -c - || die "ISO checksum mismatch"

# ─── Prepare build directory ────────────────────────────────────────────────
echo "=== Preparing ==="
rm -rf "$BUILD_DIR" "$OUTPUT_DIR"
mkdir -p "$BUILD_DIR" "$OUTPUT_DIR"

qemu-img create -f qcow2 "$DISK_IMG" 4G
cp "$EFI_CODE" "$EFI_VARS"
chmod 644 "$EFI_VARS"

# ─── Phase 1: Install Alpine via QEMU + expect ─────────────────────────────
echo "=== Phase 1: Installing Alpine via QEMU ==="

# Start HTTP server to serve answers file
python3 -m http.server 8099 --directory "$SCRIPT_DIR/http" &>/dev/null &
HTTP_PID=$!
trap "kill $HTTP_PID 2>/dev/null || true" EXIT

# Create expect script for automated Alpine installation
cat > "$BUILD_DIR/install.exp" << 'EXPECT_SCRIPT'
#!/usr/bin/expect -f
set timeout 600

spawn qemu-system-aarch64 \
    -machine virt -cpu cortex-a57 -m 1536 -smp 2 \
    -drive if=pflash,format=raw,file=[lindex $argv 0],readonly=on \
    -drive if=pflash,format=raw,file=[lindex $argv 1] \
    -drive file=[lindex $argv 2],format=qcow2,if=virtio \
    -cdrom [lindex $argv 3] \
    -boot d \
    -netdev user,id=net0,hostfwd=tcp::2222-:22 \
    -device virtio-net-device,netdev=net0 \
    -nographic

# Wait for login prompt
expect {
    "localhost login:" {}
    timeout { puts "TIMEOUT waiting for login"; exit 1 }
}
send "root\r"
expect "localhost:~#"

# Set up networking
send "ifconfig eth0 up && udhcpc -i eth0\r"
expect "localhost:~#"

# Download answers file
send "wget http://10.0.2.2:8099/answers -O /tmp/answers\r"
expect "localhost:~#"

# Run setup-alpine
send "ERASE_DISKS=/dev/vda setup-alpine -f /tmp/answers\r"

# Handle password prompts
expect {
    "New password:" {}
    "password:" {}
    timeout { puts "TIMEOUT waiting for password prompt"; exit 1 }
}
send "fshdr\r"

expect {
    "Retype password:" {}
    "again:" {}
    timeout { puts "TIMEOUT waiting for password confirm"; exit 1 }
}
send "fshdr\r"

# Handle "Setup a user?" prompt (Alpine 3.21+) and other interactive prompts
expect {
    "Setup a user?" { send "no\r"; exp_continue }
    "enter a lower-case loginname" { send "no\r"; exp_continue }
    "Which SSH server?" { send "openssh\r"; exp_continue }
    "Which disk" { send "/dev/vda\r"; exp_continue }
    "How would you like" { send "sys\r"; exp_continue }
    "WARNING:" { send "y\r"; exp_continue }
    "Erase" { send "y\r"; exp_continue }
    "Installation is complete" {}
    "localhost:~#" {}
    timeout { puts "TIMEOUT waiting for installation"; exit 1 }
}
sleep 2

# Post-install: enable SSH root login, fix serial console for VirtualBox
send "mount /dev/vda3 /mnt 2>/dev/null || mount /dev/vda2 /mnt\r"
expect "#"
send "echo 'PermitRootLogin yes' >> /mnt/etc/ssh/sshd_config\r"
expect "#"
# Remove serial console (ttyAMA0) — not available in VirtualBox
send "sed -i '/ttyAMA0/d' /mnt/etc/inittab\r"
expect "#"
send "umount /mnt\r"
expect "#"

# Power off
send "poweroff\r"
expect {
    "reboot: System halted" {}
    "Power down" {}
    eof {}
    timeout { puts "TIMEOUT waiting for poweroff"; exit 1 }
}

puts "\n=== Alpine installation complete ==="
exit 0
EXPECT_SCRIPT

echo "Running automated Alpine installation (this takes 3-5 minutes)..."
expect "$BUILD_DIR/install.exp" "$EFI_CODE" "$EFI_VARS" "$DISK_IMG" "$ISO_FILE" || die "Alpine installation failed"

# Stop HTTP server
kill $HTTP_PID 2>/dev/null || true

# ─── Phase 2: Boot installed system, provision via SSH ──────────────────────
echo ""
echo "=== Phase 2: Provisioning via SSH ==="

qemu-system-aarch64 \
    -machine virt -cpu cortex-a57 -m 1536 -smp 2 \
    -drive if=pflash,format=raw,file="$EFI_CODE",readonly=on \
    -drive if=pflash,format=raw,file="$EFI_VARS" \
    -drive file="$DISK_IMG",format=qcow2,if=virtio \
    -netdev user,id=net0,hostfwd=tcp::${SSH_PORT}-:22 \
    -device virtio-net-device,netdev=net0 \
    -serial none -display none -daemonize

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
scp_cmd "$SCRIPT_DIR/provision.sh" root@127.0.0.1:/tmp/provision.sh

echo "Running provisioning script..."
ssh_cmd "sh /tmp/provision.sh"

echo "Shutting down..."
ssh_cmd "poweroff" 2>/dev/null || true
sleep 10
pkill -f "qemu-system-aarch64.*disk.qcow2" 2>/dev/null || true
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

VM_DIR="$HOME/VirtualBox VMs/$VM_NAME"

VBoxManage createvm --name "$VM_NAME" --ostype Linux_arm64 --register
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
    --output "$OUTPUT_DIR/fs-emu-aarch64.ova" \
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
echo "  OVA built: $OUTPUT_DIR/fs-emu-aarch64.ova"
echo "  Size: $(ls -lh "$OUTPUT_DIR/fs-emu-aarch64.ova" | awk '{print $5}')"
echo "============================================"
echo ""
echo "To use: Import in VirtualBox, Start VM, open http://localhost:5050/"
