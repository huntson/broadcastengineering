"""Configuration constants and defaults for the AJA FS Emulator Control Panel."""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
DATA_DIR = os.path.join(BASE_DIR, "data")
FIRMWARE_DIR = os.path.join(DATA_DIR, "firmware")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
FLASH_DIR = os.path.join(DATA_DIR, "flash")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

# Flash images to persist (guest /tmp/flash/<name>.img)
FLASH_IMAGES = ["configa", "configb", "presetsa", "presetsb"]

# Bundled asset filenames
KERNEL_FILE = os.path.join(ASSETS_DIR, "vmlinux-mtd-stripped")
DTB_FILE = os.path.join(ASSETS_DIR, "qemu-fs.dtb")
STUB_LIB = os.path.join(ASSETS_DIR, "stub_ntv4.so")
INIT_SCRIPT = os.path.join(ASSETS_DIR, "init")
INIT_TEMPLATE = os.path.join(ASSETS_DIR, "init.tmpl")
INPUT_SIM_SCRIPT = os.path.join(ASSETS_DIR, "input_sim")

# Default device type (backward compat)
DEFAULT_DEVICE_TYPE = "FS-HDR"

# Default ports
DEFAULT_WEB_PORT = 19080
DEFAULT_FALLBACK_PORT = 18080
DEFAULT_SERIAL_PORT = 14500
DEFAULT_FLASK_PORT = 5050

# XZ magic bytes for firmware scanning
XZ_MAGIC = b'\xFD7zXZ\x00'

# Approximate offset where XZ rootfs starts in AJA firmware .bin files
XZ_SCAN_START = 0x2D0000

QEMU_BINARY = "qemu-system-ppc"

# Format and reference source maps are now per-device in core/device_profiles.py.
# These legacy globals are kept for backward compatibility only.
SDI_FORMATS = {
    3: "525i5994", 7: "625i50", 17: "720p5994", 18: "720p60",
    19: "1080i50", 20: "1080i5994", 21: "1080i60", 27: "1080p2398",
    29: "1080p25", 30: "1080p2997", 31: "1080p30", 32: "1080p50",
    33: "1080p5994", 34: "1080p60", 56: "UHD2160p2398", 59: "UHD2160p2997",
    62: "UHD2160p5994", 63: "UHD2160p60", 98: "No Input",
}
REF_SOURCES = {
    0: "Reference BNC", 1: "Free Run", 2: "SDI 1", 3: "SDI 2",
    4: "SDI 3", 5: "SDI 4", 6: "SDI 5", 7: "SDI 6", 8: "SDI 7", 9: "SDI 8",
}

# Max cached .cpio files to keep
MAX_CACHE_FILES = 3

# Boot log max lines
MAX_LOG_LINES = 10000
