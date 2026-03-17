#!/bin/sh
# Post-install: enable SSH root login on installed system
mount /dev/vda3 /mnt 2>/dev/null || mount /dev/vda2 /mnt 2>/dev/null
echo "PermitRootLogin yes" >> /mnt/etc/ssh/sshd_config
umount /mnt
