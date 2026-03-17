"""Firmware extraction, patching, and initramfs generation."""

import gzip
import hashlib
import lzma
import os
import shutil
import stat
import struct
import subprocess
import tempfile
import glob

import config
from core.cpio import read_cpio, write_cpio, CpioEntry
from core.device_profiles import (
    detect_device_from_content,
    detect_device_from_filename,
    get_profile,
    UIMAGE_MAGIC,
)


class FirmwareError(Exception):
    pass


class FirmwareProcessor:
    """Extracts an AJA FS firmware .bin, patches the rootfs, and
    produces a QEMU-bootable initramfs .cpio file."""

    def __init__(self, assets_dir=None, cache_dir=None):
        self.assets_dir = assets_dir or config.ASSETS_DIR
        self.cache_dir = cache_dir or config.CACHE_DIR

    def process(self, firmware_path, device_type=None):
        """Process a firmware .bin file and return (cpio_path, device_type).

        Auto-detects device type if not provided.
        Uses caching: if a .cpio for this firmware hash already exists, return it.
        """
        if not os.path.isfile(firmware_path):
            raise FirmwareError("Firmware file not found: %s" % firmware_path)

        fw_hash = self._compute_hash(firmware_path)

        # Read firmware for detection and extraction
        with open(firmware_path, "rb") as f:
            fw_data = f.read()

        # Auto-detect device type
        if not device_type:
            filename = os.path.basename(firmware_path)
            device_type = detect_device_from_filename(filename)
            if not device_type:
                device_type = detect_device_from_content(fw_data, filename)
            if not device_type:
                raise FirmwareError(
                    "Could not detect device type from firmware. "
                    "Filename should contain FSHDR, FS4, or FS2."
                )

        # Include device type in cache key so switching devices re-processes
        cache_path = os.path.join(
            self.cache_dir, "%s_%s.cpio" % (fw_hash[:16], device_type)
        )

        if os.path.isfile(cache_path):
            return cache_path, device_type

        os.makedirs(self.cache_dir, exist_ok=True)

        profile = get_profile(device_type)

        # Extract rootfs based on firmware format
        if profile["firmware_format"] == "uimage_ext2":
            debugfs_bin = self._find_debugfs()
            entries = self._extract_rootfs_ext2(fw_data, debugfs_bin)
        else:
            cpio_data = self._extract_rootfs_xz(fw_data)
            entries = read_cpio(cpio_data)

        if not entries:
            raise FirmwareError("No filesystem entries found in firmware")

        # Patch the rootfs
        entries = self._patch_rootfs(entries, profile)

        # Write the patched CPIO
        write_cpio(entries, cache_path)

        # Cleanup old cache files
        self._cleanup_cache()

        return cache_path, device_type

    def _compute_hash(self, path):
        """SHA-256 of the firmware file."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    # ------------------------------------------------------------------
    # XZ + CPIO extraction (FS-HDR, FS4)
    # ------------------------------------------------------------------

    def _extract_rootfs_xz(self, fw_data):
        """Find and decompress the XZ-compressed CPIO rootfs in the firmware."""
        xz_pos = fw_data.find(config.XZ_MAGIC, config.XZ_SCAN_START)

        if xz_pos < 0:
            xz_pos = fw_data.find(config.XZ_MAGIC)

        if xz_pos < 0:
            raise FirmwareError(
                "No XZ-compressed rootfs found in firmware. "
                "File may not be a valid AJA FS-HDR/FS4 firmware."
            )

        xz_data = fw_data[xz_pos:]
        try:
            decompressor = lzma.LZMADecompressor(format=lzma.FORMAT_XZ)
            result = b""
            chunk_size = 1024 * 1024
            pos = 0
            while pos < len(xz_data) and not decompressor.eof:
                end = min(pos + chunk_size, len(xz_data))
                result += decompressor.decompress(xz_data[pos:end])
                pos = end
            return result
        except lzma.LZMAError as e:
            raise FirmwareError("Failed to decompress rootfs: %s" % e)

    # ------------------------------------------------------------------
    # uImage + gzip + ext2 extraction (FS2)
    # ------------------------------------------------------------------

    def _find_debugfs(self):
        """Find the debugfs binary. Returns the path or raises FirmwareError."""
        found = shutil.which("debugfs")
        if found:
            return found
        # Homebrew on macOS installs to sbin
        candidates = [
            "/opt/homebrew/opt/e2fsprogs/sbin/debugfs",
            "/opt/homebrew/sbin/debugfs",
            "/usr/local/opt/e2fsprogs/sbin/debugfs",
            "/usr/local/sbin/debugfs",
            "/usr/sbin/debugfs",
            "/sbin/debugfs",
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path
        raise FirmwareError(
            "FS2 firmware requires e2fsprogs (debugfs). Install it:\n"
            "  macOS: brew install e2fsprogs\n"
            "  Linux: apt install e2fsprogs\n"
            "  Alpine: apk add e2fsprogs-extra"
        )

    def _extract_rootfs_ext2(self, fw_data, debugfs_bin="debugfs"):
        """Extract rootfs from FS2 firmware (uImage+gzip+ext2) into CPIO entries."""
        # Find the ramdisk uImage (second uImage header — first is the kernel)
        first_pos = fw_data.find(UIMAGE_MAGIC)
        if first_pos < 0:
            raise FirmwareError("No uImage header found in firmware")

        ramdisk_pos = fw_data.find(UIMAGE_MAGIC, first_pos + 64)
        if ramdisk_pos < 0:
            raise FirmwareError("No ramdisk uImage header found in firmware")

        # Parse uImage header (64 bytes)
        hdr = fw_data[ramdisk_pos:ramdisk_pos + 64]
        ih_size = struct.unpack(">I", hdr[12:16])[0]

        # Extract gzip payload (starts after 64-byte header)
        gz_data = fw_data[ramdisk_pos + 64:ramdisk_pos + 64 + ih_size]
        if gz_data[:2] != b'\x1f\x8b':
            raise FirmwareError("Ramdisk payload is not gzip-compressed")

        try:
            ext2_data = gzip.decompress(gz_data)
        except Exception as e:
            raise FirmwareError("Failed to decompress ramdisk: %s" % e)

        # Write ext2 image to temp file and extract with debugfs
        tmpdir = tempfile.mkdtemp(prefix="fs_emu_ext2_")
        ext2_path = os.path.join(tmpdir, "rootfs.ext2")
        extract_dir = os.path.join(tmpdir, "rootfs")

        try:
            with open(ext2_path, "wb") as f:
                f.write(ext2_data)

            os.makedirs(extract_dir, exist_ok=True)

            result = subprocess.run(
                [debugfs_bin, "-R", "rdump / %s" % extract_dir, ext2_path],
                capture_output=True, timeout=120,
            )
            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", errors="replace")
                # debugfs often prints warnings to stderr even on success
                # Only fail if the extract dir is empty
                if not os.listdir(extract_dir):
                    raise FirmwareError(
                        "debugfs extraction failed: %s" % stderr[:500]
                    )

            # Walk the extracted tree and build CPIO entries
            entries = self._dir_to_cpio_entries(extract_dir)
            return entries

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _dir_to_cpio_entries(self, root_dir):
        """Convert a directory tree into a list of CpioEntry objects."""
        entries = []
        for dirpath, dirnames, filenames in os.walk(root_dir):
            rel_dir = os.path.relpath(dirpath, root_dir)
            if rel_dir == ".":
                rel_dir = ""

            # Add directory entry (skip root ".")
            if rel_dir:
                dir_stat = os.lstat(os.path.join(dirpath))
                entries.append(CpioEntry(
                    name=rel_dir,
                    mode=stat.S_IFDIR | (dir_stat.st_mode & 0o7777),
                    data=b"",
                    nlink=2,
                ))

            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                rel_path = os.path.join(rel_dir, fname) if rel_dir else fname
                fstat = os.lstat(full_path)

                if stat.S_ISLNK(fstat.st_mode):
                    # Symlink
                    target = os.readlink(full_path)
                    entries.append(CpioEntry(
                        name=rel_path,
                        mode=stat.S_IFLNK | 0o777,
                        data=target.encode("utf-8"),
                        nlink=1,
                    ))
                elif stat.S_ISREG(fstat.st_mode):
                    with open(full_path, "rb") as f:
                        data = f.read()
                    entries.append(CpioEntry(
                        name=rel_path,
                        mode=stat.S_IFREG | (fstat.st_mode & 0o7777),
                        data=data,
                        nlink=1,
                    ))

        return entries

    # ------------------------------------------------------------------
    # Rootfs patching
    # ------------------------------------------------------------------

    def _render_init_script(self, profile):
        """Render the init script template with device-specific values."""
        tmpl_path = config.INIT_TEMPLATE
        if not os.path.isfile(tmpl_path):
            # Fall back to static init script (backward compat)
            with open(config.INIT_SCRIPT, "rb") as f:
                return f.read()

        with open(tmpl_path, "r") as f:
            template = f.read()

        vid_channels_str = " ".join(str(v) for v in profile["vid_channels"])
        sdi_param_list_str = " ".join(profile["sdi_params"])
        derive_vid_str = "1" if profile["derive_vid_from_sdi"] else "0"

        template = template.replace("__PRODUCT_ID__", profile["product_id"])
        template = template.replace("__HOSTNAME__", profile["hostname"])
        template = template.replace("__BANNER__", profile["banner"])
        template = template.replace("__PRODUCT_NAME__", profile["display_name"])
        template = template.replace("__VID_CHANNELS__", vid_channels_str)
        template = template.replace("__SDI_PARAM_LIST__", sdi_param_list_str)
        template = template.replace("__DERIVE_VID__", derive_vid_str)

        return template.encode("utf-8")

    def _patch_rootfs(self, entries, profile=None):
        """Apply all patches to the CPIO entries."""
        # Build a name -> index map for quick lookup
        name_map = {}
        for i, entry in enumerate(entries):
            name_map[entry.name] = i

        # 1. Replace /init with rendered init script
        if profile:
            init_data = self._render_init_script(profile)
            resolved = self._resolve_path(name_map, "init")
            if resolved in name_map:
                idx = name_map[resolved]
                entries[idx].data = init_data
                entries[idx].mode = 0o100755
            else:
                entry = CpioEntry(
                    name=resolved, mode=0o100755, data=init_data, nlink=1,
                )
                entries.append(entry)
                name_map[resolved] = len(entries) - 1
        else:
            # Legacy path: use static init file
            init_path = os.path.join(self.assets_dir, "init")
            self._replace_file(entries, name_map, "init", init_path, mode=0o100755)

        # 2. Replace libntv4.so with stub
        stub_path = os.path.join(self.assets_dir, "stub_ntv4.so")
        self._replace_file(entries, name_map, "usr/local/lib/libntv4.so",
                           stub_path, mode=0o100755)

        # 3. Replace/insert input_sim
        sim_path = os.path.join(self.assets_dir, "input_sim")
        self._replace_file(entries, name_map, "usr/local/bin/input_sim",
                           sim_path, mode=0o100755)

        # 4. Fix nsswitch.conf
        nsswitch_key = self._resolve_path(name_map, "etc/nsswitch.conf")
        if nsswitch_key in name_map:
            idx = name_map[nsswitch_key]
            old_data = entries[idx].data
            new_data = old_data.replace(b"passwd:         compat",
                                        b"passwd:         files")
            new_data = new_data.replace(b"passwd:\tcompat",
                                        b"passwd:\tfiles")
            new_data = new_data.replace(b"group:          compat",
                                        b"group:          files")
            new_data = new_data.replace(b"group:\tcompat",
                                        b"group:\tfiles")
            new_data = new_data.replace(b"shadow:         compat",
                                        b"shadow:         files")
            new_data = new_data.replace(b"shadow:\tcompat",
                                        b"shadow:\tfiles")
            entries[idx].data = new_data

        return entries

    def _resolve_path(self, name_map, path):
        """Find the actual CPIO path, trying both bare and ./ prefixed variants."""
        bare = path.lstrip("./")
        if bare in name_map:
            return bare
        dotslash = "./" + bare
        if dotslash in name_map:
            return dotslash
        return bare  # default to bare for new entries

    def _replace_file(self, entries, name_map, cpio_path, local_path, mode=None):
        """Replace or insert a file in the CPIO entry list."""
        if not os.path.isfile(local_path):
            raise FirmwareError("Asset not found: %s" % local_path)

        with open(local_path, "rb") as f:
            new_data = f.read()

        resolved = self._resolve_path(name_map, cpio_path)
        if resolved in name_map:
            idx = name_map[resolved]
            entries[idx].data = new_data
            if mode is not None:
                entries[idx].mode = mode
        else:
            entry = CpioEntry(
                name=resolved,
                mode=mode or 0o100755,
                data=new_data,
                nlink=1,
            )
            entries.append(entry)
            name_map[resolved] = len(entries) - 1

    def _cleanup_cache(self):
        """Keep only the most recent N cached .cpio files."""
        pattern = os.path.join(self.cache_dir, "*.cpio")
        files = sorted(glob.glob(pattern), key=os.path.getmtime)
        while len(files) > config.MAX_CACHE_FILES:
            oldest = files.pop(0)
            try:
                os.remove(oldest)
            except OSError:
                pass
