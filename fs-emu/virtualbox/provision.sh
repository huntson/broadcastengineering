#!/bin/sh
# Provision the Alpine VM with QEMU, Python, Flask, and fs-emu
set -e

echo "=== Enabling community repository ==="
sed -i 's|^#\(http.*/community\)|\1|' /etc/apk/repositories

echo "=== Installing packages ==="
apk update
apk add python3 py3-pip qemu-system-ppc e2fsprogs-extra

echo "=== Installing Flask ==="
pip3 install --break-system-packages flask

echo "=== Installing fs-emu ==="
mkdir -p /opt/fs-emu
cp -r /tmp/fs-emu/* /opt/fs-emu/
mkdir -p /opt/fs-emu/data

echo "=== Installing service ==="
cp /tmp/fs-emu.initd /etc/init.d/fs-emu
chmod 755 /etc/init.d/fs-emu
rc-update add fs-emu default

echo "=== Fixing disk references for VirtualBox (vda -> sda) ==="
# QEMU uses virtio (vda), VirtualBox uses SATA (sda)
# Update fstab, GRUB config, extlinux so both work
for f in /etc/fstab /boot/grub/grub.cfg /boot/extlinux.conf; do
    if [ -f "$f" ] && grep -q vda "$f" 2>/dev/null; then
        sed -i 's|/dev/vda|/dev/sda|g' "$f"
        echo "  Fixed $f"
    fi
done

echo "=== Ensuring EFI fallback boot path ==="
# Copy GRUB to the standard UEFI fallback path so VirtualBox ARM can find it
EFI_DIR=""
if [ -d /boot/efi/EFI ]; then
    EFI_DIR=/boot/efi
elif [ -d /boot/EFI ]; then
    EFI_DIR=/boot
fi
if [ -n "$EFI_DIR" ]; then
    mkdir -p "$EFI_DIR/EFI/BOOT"
    GRUB_EFI=$(find "$EFI_DIR/EFI" -name "grubaa64.efi" 2>/dev/null | head -1)
    if [ -n "$GRUB_EFI" ]; then
        cp "$GRUB_EFI" "$EFI_DIR/EFI/BOOT/BOOTAA64.EFI"
        echo "  Copied $GRUB_EFI -> EFI/BOOT/BOOTAA64.EFI"
    else
        echo "  WARNING: grubaa64.efi not found"
    fi
fi

echo "=== Cleanup ==="
rm -rf /tmp/fs-emu /tmp/fs-emu.initd
apk cache clean 2>/dev/null || true
rm -rf /var/cache/apk/*

echo "=== Done ==="
