"""Pure-Python CPIO newc (SVR4 no CRC) reader/writer for initramfs archives."""

import struct
import io

CPIO_MAGIC = b"070701"
TRAILER = "TRAILER!!!"


class CpioEntry:
    """Represents a single entry in a CPIO newc archive."""

    __slots__ = (
        "name", "ino", "mode", "uid", "gid", "nlink", "mtime",
        "data", "devmajor", "devminor", "rdevmajor", "rdevminor",
    )

    def __init__(self, name, mode=0, uid=0, gid=0, nlink=1, mtime=0,
                 data=b"", devmajor=0, devminor=0, rdevmajor=0, rdevminor=0,
                 ino=0):
        self.name = name
        self.ino = ino
        self.mode = mode
        self.uid = uid
        self.gid = gid
        self.nlink = nlink
        self.mtime = mtime
        self.data = data
        self.devmajor = devmajor
        self.devminor = devminor
        self.rdevmajor = rdevmajor
        self.rdevminor = rdevminor

    def is_dir(self):
        return (self.mode & 0o170000) == 0o040000

    def is_file(self):
        return (self.mode & 0o170000) == 0o100000

    def is_symlink(self):
        return (self.mode & 0o170000) == 0o120000

    def is_device(self):
        typ = self.mode & 0o170000
        return typ == 0o060000 or typ == 0o020000  # block or char

    def __repr__(self):
        return "CpioEntry(%r, mode=0o%06o, size=%d)" % (
            self.name, self.mode, len(self.data))


def _align4(n):
    """Round up to next 4-byte boundary."""
    return (n + 3) & ~3


def read_cpio(source):
    """Read a CPIO newc archive from a file path or bytes.

    Returns a list of CpioEntry objects (excluding the TRAILER).
    """
    if isinstance(source, (str, bytes)) and not isinstance(source, bytes):
        with open(source, "rb") as f:
            data = f.read()
    elif isinstance(source, bytes):
        data = source
    else:
        data = source.read()

    entries = []
    pos = 0
    data_len = len(data)

    while pos < data_len:
        # Need at least 110 bytes for the header
        if pos + 110 > data_len:
            break

        # Check magic
        magic = data[pos:pos + 6]
        if magic != CPIO_MAGIC:
            break

        # Parse header fields (all 8-char hex strings)
        hdr = data[pos:pos + 110]
        try:
            ino = int(hdr[6:14], 16)
            mode = int(hdr[14:22], 16)
            uid = int(hdr[22:30], 16)
            gid = int(hdr[30:38], 16)
            nlink = int(hdr[38:46], 16)
            mtime = int(hdr[46:54], 16)
            filesize = int(hdr[54:62], 16)
            devmajor = int(hdr[62:70], 16)
            devminor = int(hdr[70:78], 16)
            rdevmajor = int(hdr[78:86], 16)
            rdevminor = int(hdr[86:94], 16)
            namesize = int(hdr[94:102], 16)
            check = int(hdr[102:110], 16)
        except ValueError:
            break

        # Filename starts at pos+110, length namesize (includes trailing NUL)
        name_start = pos + 110
        name_end = name_start + namesize
        if name_end > data_len:
            break
        # Strip trailing NUL
        name = data[name_start:name_end].rstrip(b"\x00").decode("utf-8", errors="replace")

        # Data starts after header+name, aligned to 4 bytes
        data_start = _align4(name_end)
        data_end = data_start + filesize
        if data_end > data_len:
            break
        file_data = data[data_start:data_end]

        # Next entry starts after data, aligned to 4 bytes
        pos = _align4(data_end)

        # Skip trailer
        if name == TRAILER:
            break

        entry = CpioEntry(
            name=name, ino=ino, mode=mode, uid=uid, gid=gid,
            nlink=nlink, mtime=mtime, data=file_data,
            devmajor=devmajor, devminor=devminor,
            rdevmajor=rdevmajor, rdevminor=rdevminor,
        )
        entries.append(entry)

    return entries


def write_cpio(entries, dest):
    """Write a CPIO newc archive from a list of CpioEntry objects.

    dest can be a file path (str) or a writable binary stream.
    Assigns sequential inode numbers starting from 1.
    """
    buf = io.BytesIO()
    ino_counter = 1

    for entry in entries:
        _write_entry(buf, entry, ino_counter)
        ino_counter += 1

    # Write trailer
    trailer = CpioEntry(name=TRAILER, nlink=1)
    _write_entry(buf, trailer, 0)

    # Pad archive to 512-byte boundary (some implementations expect this)
    total = buf.tell()
    remainder = total % 512
    if remainder:
        buf.write(b"\x00" * (512 - remainder))

    result = buf.getvalue()

    if isinstance(dest, str):
        with open(dest, "wb") as f:
            f.write(result)
    else:
        dest.write(result)

    return result


def _write_entry(buf, entry, ino):
    """Write a single CPIO newc entry to the buffer."""
    name_bytes = entry.name.encode("utf-8") + b"\x00"
    namesize = len(name_bytes)
    filesize = len(entry.data)

    # Build 110-byte header
    hdr = b"070701"
    hdr += b"%08X" % ino
    hdr += b"%08X" % entry.mode
    hdr += b"%08X" % entry.uid
    hdr += b"%08X" % entry.gid
    hdr += b"%08X" % entry.nlink
    hdr += b"%08X" % entry.mtime
    hdr += b"%08X" % filesize
    hdr += b"%08X" % entry.devmajor
    hdr += b"%08X" % entry.devminor
    hdr += b"%08X" % entry.rdevmajor
    hdr += b"%08X" % entry.rdevminor
    hdr += b"%08X" % namesize
    hdr += b"%08X" % 0  # check (always 0 for newc)

    buf.write(hdr)
    buf.write(name_bytes)

    # Pad header+name to 4-byte boundary
    total_hdr = 110 + namesize
    pad = _align4(total_hdr) - total_hdr
    if pad:
        buf.write(b"\x00" * pad)

    # Write file data
    if filesize:
        buf.write(entry.data)
        # Pad data to 4-byte boundary
        pad = _align4(filesize) - filesize
        if pad:
            buf.write(b"\x00" * pad)
