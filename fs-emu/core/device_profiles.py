"""Device profiles and detection for AJA FS-series emulation."""

import re

_SDI_PARAMS_8 = [
    "eParamID_SDI%dDetectedInputFormat" % (i + 1) for i in range(8)
]

# FS-HDR / FS4 format codes (shared — both support SD through UHD)
_FORMATS_HDR = {
    3: "525i5994",
    7: "625i50",
    17: "720p5994",
    18: "720p60",
    19: "1080i50",
    20: "1080i5994",
    21: "1080i60",
    27: "1080p2398",
    29: "1080p25",
    30: "1080p2997",
    31: "1080p30",
    32: "1080p50",
    33: "1080p5994",
    34: "1080p60",
    56: "UHD2160p2398",
    59: "UHD2160p2997",
    62: "UHD2160p5994",
    63: "UHD2160p60",
    98: "No Input",
}

# FS2 format codes (SD/HD/2K only — no UHD, different "No Input" code)
_FORMATS_FS2 = {
    2: "525PsF2997",
    3: "525i5994",
    6: "625PsF25",
    7: "625i50",
    11: "720p2398",
    12: "720p24",
    13: "720p25",
    14: "720p2997",
    15: "720p30",
    16: "720p50",
    17: "720p5994",
    18: "720p60",
    19: "1080i50",
    20: "1080i5994",
    21: "1080i60",
    22: "1080PsF2398",
    23: "1080PsF24",
    24: "1080PsF25",
    25: "1080PsF2997",
    26: "1080PsF30",
    27: "1080p2398",
    28: "1080p24",
    29: "1080p25",
    30: "1080p2997",
    31: "1080p30",
    32: "1080p50",
    33: "1080p5994",
    34: "1080p60",
    43: "2K1080p2398",
    44: "2K1080p24",
    45: "2K1080p25",
    46: "2K1080p2997",
    47: "2K1080p30",
    48: "2K1080p50",
    49: "2K1080p5994",
    50: "2K1080p60",
    56: "No Input",
}

# FS-HDR / FS4 reference sources
_REF_SOURCES_HDR = {
    0: "Reference BNC",
    1: "Free Run",
    2: "SDI 1",
    3: "SDI 2",
    4: "SDI 3",
    5: "SDI 4",
    6: "SDI 5",
    7: "SDI 6",
    8: "SDI 7",
    9: "SDI 8",
}

# FS2 reference/genlock sources (completely different values)
_REF_SOURCES_FS2 = {
    0: "Reference BNC",
    1: "Vid1 Input",
    2: "Vid2 Input",
    3: "Free Run",
}

DEVICE_PROFILES = {
    "FS-HDR": {
        "product_id": "TORU",
        "hostname": "FS-HDR",
        "display_name": "FS-HDR",
        "banner": "AJA FS-HDR (emulated)",
        "vid_channels": [0, 1, 2, 3, 4],
        "vid_sdi_map": {0: 0, 1: 0, 2: 1, 3: 2, 4: 3},
        "sdi_count": 8,
        "firmware_format": "xz_cpio",
        # FS-HDR has 8 separate SDI detected-format params + derived Vid params
        "sdi_params": list(_SDI_PARAMS_8),
        "derive_vid_from_sdi": True,
        "input_label": "SDI",
        "formats": _FORMATS_HDR,
        "ref_sources": _REF_SOURCES_HDR,
        # Genlock source value 0 = BNC, 1 = Free Run, 2-9 = SDI 1-8
        "ref_bnc_value": 0,
        "ref_freerun_value": 1,
        "no_input_value": 98,
        # Map genlock source value → SDI index (0-based) for auto-sync
        "ref_source_to_sdi": {2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5, 8: 6, 9: 7},
    },
    "FS4": {
        "product_id": "SATO",
        "hostname": "FS4",
        "display_name": "FS4",
        "banner": "AJA FS4 (emulated)",
        "vid_channels": [1, 2, 3, 4],
        "vid_sdi_map": {1: 0, 2: 1, 3: 2, 4: 3},
        "sdi_count": 8,
        "firmware_format": "xz_cpio",
        "sdi_params": list(_SDI_PARAMS_8),
        "derive_vid_from_sdi": True,
        "input_label": "SDI",
        "formats": _FORMATS_HDR,
        "ref_sources": _REF_SOURCES_HDR,
        "ref_bnc_value": 0,
        "ref_freerun_value": 1,
        "no_input_value": 98,
        "ref_source_to_sdi": {2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5, 8: 6, 9: 7},
    },
    "FS2": {
        "product_id": "FS2",
        "hostname": "FS2",
        "display_name": "FS2",
        "banner": "AJA FS2 (emulated)",
        "vid_channels": [1, 2],
        "vid_sdi_map": {1: 0, 2: 1},
        "sdi_count": 2,
        "firmware_format": "uimage_ext2",
        # FS2 has NO per-SDI params — inputs are Vid1/Vid2 directly
        "sdi_params": [
            "eParamID_Vid1DetectedInputFormat",
            "eParamID_Vid2DetectedInputFormat",
        ],
        "derive_vid_from_sdi": False,
        "input_label": "Channel",
        "formats": _FORMATS_FS2,
        "ref_sources": _REF_SOURCES_FS2,
        "ref_bnc_value": 0,
        "ref_freerun_value": 3,
        "no_input_value": 56,
        # Map genlock source value → sdi_params index for auto-sync
        # FS2: 1=Vid1 (index 0), 2=Vid2 (index 1)
        "ref_source_to_sdi": {1: 0, 2: 1},
    },
}

# uImage magic bytes
UIMAGE_MAGIC = b'\x27\x05\x19\x56'

# Filename patterns for device detection
_FILENAME_PATTERNS = [
    (re.compile(r'(?i)FSHDR|FS-HDR|FS_HDR'), "FS-HDR"),
    (re.compile(r'(?i)FS4'), "FS4"),
    (re.compile(r'(?i)FS2'), "FS2"),
]


def detect_device_from_filename(filename):
    """Detect device type from firmware filename.

    Returns device type string ('FS-HDR', 'FS4', 'FS2') or None.
    """
    for pattern, device_type in _FILENAME_PATTERNS:
        if pattern.search(filename):
            return device_type
    return None


def detect_device_from_content(fw_data, filename=None):
    """Detect device type from firmware binary content and optional filename.

    Returns device type string ('FS-HDR', 'FS4', 'FS2') or None.
    """
    # Check for uImage magic — indicates FS2 (uImage+gzip+ext2 format)
    if fw_data[:4] == UIMAGE_MAGIC or fw_data.find(UIMAGE_MAGIC) >= 0:
        # FS-HDR/FS4 may also have uImage-like bytes in their larger binaries,
        # but they have XZ rootfs too.  Check for XZ magic first.
        from config import XZ_MAGIC, XZ_SCAN_START
        xz_pos = fw_data.find(XZ_MAGIC, XZ_SCAN_START)
        if xz_pos < 0:
            xz_pos = fw_data.find(XZ_MAGIC)
        if xz_pos >= 0:
            # Has XZ rootfs — it's FS-HDR or FS4, not FS2
            pass
        else:
            return "FS2"

    # Check for XZ rootfs — FS-HDR or FS4
    from config import XZ_MAGIC, XZ_SCAN_START
    xz_pos = fw_data.find(XZ_MAGIC, XZ_SCAN_START)
    if xz_pos < 0:
        xz_pos = fw_data.find(XZ_MAGIC)
    if xz_pos >= 0:
        # Differentiate FS-HDR vs FS4 by filename or firmware size
        if filename:
            fname_type = detect_device_from_filename(filename)
            if fname_type in ("FS-HDR", "FS4"):
                return fname_type
        # Heuristic: FS-HDR firmware is typically larger (~60MB vs ~32MB for FS4)
        if len(fw_data) > 45_000_000:
            return "FS-HDR"
        else:
            return "FS4"

    return None


def get_profile(device_type):
    """Get the device profile dict for a given device type.

    Falls back to FS-HDR if device_type is unknown.
    """
    return DEVICE_PROFILES.get(device_type, DEVICE_PROFILES["FS-HDR"])
