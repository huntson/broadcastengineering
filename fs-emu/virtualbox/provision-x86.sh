#!/bin/sh
# Provision the Alpine VM with QEMU, Python, Flask, and fs-emu
# x86_64 version — no EFI fixups needed (BIOS boot)
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
for f in /etc/fstab /boot/grub/grub.cfg /boot/extlinux.conf; do
    if [ -f "$f" ] && grep -q vda "$f" 2>/dev/null; then
        sed -i 's|/dev/vda|/dev/sda|g' "$f"
        echo "  Fixed $f"
    fi
done

echo "=== Cleanup ==="
rm -rf /tmp/fs-emu /tmp/fs-emu.initd
apk cache clean 2>/dev/null || true
rm -rf /var/cache/apk/*

echo "=== Done ==="
