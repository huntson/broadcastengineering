"""AJA FS Emulator Control Panel — Flask Application."""

import json
import os
import threading

from flask import Flask, render_template, request, jsonify, send_file
import urllib.request

import config
from core.qemu_manager import QemuManager
from core.firmware_processor import FirmwareProcessor, FirmwareError
from core.webd_client import WebdClient
from core.device_profiles import get_profile, DEVICE_PROFILES

app = Flask(__name__)

# Singletons
qemu = QemuManager()
firmware_proc = FirmwareProcessor()
webd = WebdClient("http://127.0.0.1:%d" % config.DEFAULT_WEB_PORT)

# Cache for live enums fetched from the device's desc.json
_live_formats_cache = {}
_live_ref_cache = {}
_live_ref_formats_cache = {}


def _ensure_dirs():
    """Create runtime directories if they don't exist."""
    for d in [config.DATA_DIR, config.FIRMWARE_DIR, config.CACHE_DIR, config.FLASH_DIR]:
        os.makedirs(d, exist_ok=True)


def _load_config():
    """Load persisted config, or return defaults."""
    defaults = {
        "web_port": config.DEFAULT_WEB_PORT,
        "fallback_port": config.DEFAULT_FALLBACK_PORT,
        "flask_port": config.DEFAULT_FLASK_PORT,
        "last_firmware": None,
        "last_initramfs": None,
        "device_type": None,
        "sdi_formats": [20, 20, 20, 20, 98, 98, 98, 98],
        "ref_source": 0,
        "ref_format": 20,
    }
    if os.path.isfile(config.CONFIG_FILE):
        try:
            with open(config.CONFIG_FILE, "r") as f:
                saved = json.load(f)
            defaults.update(saved)
        except (json.JSONDecodeError, IOError):
            pass
    return defaults


def _save_config(cfg):
    """Save config to disk atomically."""
    _ensure_dirs()
    tmp = config.CONFIG_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, config.CONFIG_FILE)


def _get_current_profile():
    """Get the device profile for the currently loaded firmware, or None."""
    cfg = _load_config()
    if cfg.get("last_firmware") is None:
        return None
    device_type = cfg.get("device_type", config.DEFAULT_DEVICE_TYPE)
    return get_profile(device_type)


def _get_live_formats():
    """Get format enum from the running device's desc.json, with fallback.

    Returns the format dict {int_code: display_name} from the device itself
    when available, otherwise falls back to the static profile.
    """
    global _live_formats_cache
    if _live_formats_cache:
        return _live_formats_cache

    if qemu.state == "running":
        profile = _get_current_profile()
        # Use the first sdi_param to look up formats
        param_id = profile["sdi_params"][0]
        live = webd.get_param_enum(param_id)
        if live:
            _live_formats_cache = live
            return live

    return _get_current_profile()["formats"]


def _get_live_ref_sources():
    """Get reference source enum from the running device's desc.json."""
    global _live_ref_cache
    if _live_ref_cache:
        return _live_ref_cache

    if qemu.state == "running":
        live = webd.get_param_enum("eParamID_GenlockSource")
        if live:
            _live_ref_cache = live
            return live

    return _get_current_profile()["ref_sources"]


def _get_live_ref_formats():
    """Get reference format enum from the running device's desc.json."""
    global _live_ref_formats_cache
    if _live_ref_formats_cache:
        return _live_ref_formats_cache

    if qemu.state == "running":
        live = webd.get_param_enum("eParamID_DetectedReferenceFormat")
        if live:
            _live_ref_formats_cache = live
            return live

    # Fall back to the input formats (same codes on most devices)
    return _get_live_formats()


def _clear_live_caches():
    """Clear cached enums (call when device type changes)."""
    global _live_formats_cache, _live_ref_cache, _live_ref_formats_cache
    _live_formats_cache = {}
    _live_ref_cache = {}
    _live_ref_formats_cache = {}


def _build_sdi_params(format_val, sdi_mask=0xFF):
    """Build (param_id, value) tuples for input format params.

    Uses the device's sdi_params list (8 SDI params on FS-HDR/FS4,
    2 Vid params on FS2).
    """
    profile = _get_current_profile()
    sdi_params = profile["sdi_params"]
    params = []
    for i, param in enumerate(sdi_params):
        if sdi_mask & (1 << i):
            params.append((param, format_val))
    return params


def _build_vid_params(sdi_formats):
    """Build (param_id, value) tuples for Vid detected input formats.

    Derives each Vid's format from the SDI it reads from.
    Skipped on FS2 where sdi_params already ARE the Vid params.
    """
    profile = _get_current_profile()
    if not profile["derive_vid_from_sdi"]:
        return []
    vid_sdi_map = profile["vid_sdi_map"]
    params = []
    for vid, sdi_idx in vid_sdi_map.items():
        fmt = sdi_formats[sdi_idx]
        params.append(("eParamID_Vid%dDetectedInputFormat" % vid, fmt))
    return params


# Params that webd allows writing (control params, not hardware-detected status)
_WEBD_WRITABLE = {"eParamID_RemoteControl"}


def _apply_params(params):
    """Apply param tuples using webd for writable params, serial for the rest.

    Returns (ok_count, error_msg_or_None).
    """
    webd_params = [(p, v) for p, v in params if p in _WEBD_WRITABLE]
    serial_params = [(p, v) for p, v in params if p not in _WEBD_WRITABLE]

    ok = 0
    if webd_params:
        ok += webd.set_params(webd_params)

    if serial_params:
        # Fire-and-forget: send all config_cli calls as background jobs.
        # No marker detection needed — we don't need the output.
        for pid, val in serial_params:
            qemu.send_raw(
                "config_cli --set %s %s 2>/dev/null &" % (pid, val)
            )
        ok += len(serial_params)

    return (ok, None)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    cfg = _load_config()
    profile = _get_current_profile()
    has_firmware = profile is not None
    return render_template("index.html",
                           sdi_formats=_get_live_formats() if has_firmware else {},
                           ref_sources=_get_live_ref_sources() if has_firmware else {},
                           ref_formats=_get_live_ref_formats() if has_firmware else {},
                           config=cfg,
                           has_firmware=has_firmware,
                           device_type=cfg.get("device_type") if has_firmware else None,
                           device_name=profile["display_name"] if has_firmware else None,
                           input_count=len(profile["sdi_params"]) if has_firmware else 0,
                           input_label=profile["input_label"] if has_firmware else "",
                           ref_bnc_value=profile["ref_bnc_value"] if has_firmware else 0)


@app.route("/api/status")
def api_status():
    cfg = _load_config()
    emu_config = qemu.get_config()
    web_port = emu_config.get("web_port", cfg.get("web_port", config.DEFAULT_WEB_PORT))
    has_firmware = cfg.get("last_firmware") is not None
    device_type = cfg.get("device_type") if has_firmware else None
    profile = get_profile(device_type) if device_type else None
    return jsonify({
        "state": qemu.state,
        "firmware": cfg.get("last_firmware"),
        "web_port": web_port,
        "uptime": qemu.get_uptime(),
        "device_url": "http://localhost:%d/" % web_port,
        "device_type": device_type,
        "device_name": profile["display_name"] if profile else None,
        "vid_channels": profile["vid_channels"] if profile else [],
        "input_count": len(profile["sdi_params"]) if profile else 0,
        "input_label": profile["input_label"] if profile else "",
        "log_lines": len(qemu.boot_log),
    })


@app.route("/api/firmware/upload", methods=["POST"])
def api_firmware_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No file selected"}), 400

    _ensure_dirs()
    save_path = os.path.join(config.FIRMWARE_DIR, f.filename)
    f.save(save_path)

    try:
        cpio_path, device_type = firmware_proc.process(save_path)
    except FirmwareError as e:
        return jsonify({"error": str(e)}), 400

    cfg = _load_config()
    cfg["last_firmware"] = f.filename
    cfg["last_initramfs"] = cpio_path
    cfg["device_type"] = device_type
    _save_config(cfg)
    _clear_live_caches()

    return jsonify({
        "firmware": f.filename,
        "initramfs": cpio_path,
        "device_type": device_type,
        "message": "Firmware processed — detected %s" % device_type,
    })


@app.route("/api/firmware/list")
def api_firmware_list():
    _ensure_dirs()
    files = []
    for name in sorted(os.listdir(config.FIRMWARE_DIR)):
        if name.endswith(".bin"):
            path = os.path.join(config.FIRMWARE_DIR, name)
            files.append({
                "name": name,
                "size_mb": round(os.path.getsize(path) / 1024 / 1024, 1),
            })
    cfg = _load_config()
    return jsonify({
        "firmware": files,
        "selected": cfg.get("last_firmware"),
    })


@app.route("/api/firmware/delete", methods=["POST"])
def api_firmware_delete():
    if qemu.state in ("starting", "running"):
        return jsonify({"error": "Stop the emulator first"}), 409

    data = request.get_json(force=True)
    name = data.get("name")
    if not name:
        return jsonify({"error": "No firmware name provided"}), 400

    fw_path = os.path.join(config.FIRMWARE_DIR, name)
    if not os.path.isfile(fw_path):
        return jsonify({"error": "Firmware file not found"}), 404

    os.remove(fw_path)

    cfg = _load_config()
    if cfg.get("last_firmware") == name:
        cfg["last_firmware"] = None
        cfg["last_initramfs"] = None
        _save_config(cfg)
        _clear_live_caches()

    return jsonify({"message": "Deleted %s" % name})


@app.route("/api/firmware/select", methods=["POST"])
def api_firmware_select():
    data = request.get_json(force=True)
    name = data.get("name")
    if not name:
        return jsonify({"error": "No firmware name provided"}), 400

    fw_path = os.path.join(config.FIRMWARE_DIR, name)
    if not os.path.isfile(fw_path):
        return jsonify({"error": "Firmware file not found"}), 404

    try:
        cpio_path, device_type = firmware_proc.process(fw_path)
    except FirmwareError as e:
        return jsonify({"error": str(e)}), 400

    cfg = _load_config()
    cfg["last_firmware"] = name
    cfg["last_initramfs"] = cpio_path
    cfg["device_type"] = device_type
    _save_config(cfg)
    _clear_live_caches()

    return jsonify({
        "firmware": name,
        "initramfs": cpio_path,
        "device_type": device_type,
    })


def _restore_saved_config():
    """Wait for emulator to boot, then re-apply saved SDI/reference formats."""
    import time

    for _ in range(120):
        if qemu.state == "running":
            break
        if qemu.state in ("stopped", "error"):
            return
        time.sleep(1)
    else:
        return

    cfg = _load_config()

    # Build param tuples for all saved settings
    params = []

    sdi_formats = cfg.get("sdi_formats")
    if sdi_formats:
        profile = _get_current_profile()
        sdi_params = profile["sdi_params"]
        for i, fmt in enumerate(sdi_formats):
            if i < len(sdi_params):
                params.append((sdi_params[i], fmt))
        params.extend(_build_vid_params(sdi_formats))

    # Restore BNC reference format if saved (genlock source is a device
    # setting — we don't restore it, only the simulated BNC signal)
    ref_format = cfg.get("ref_format")
    if ref_format is not None:
        params.append(("eParamID_DetectedReferenceFormat", ref_format))

    if not params:
        return

    # Wait for serial console to be ready, then apply
    time.sleep(3)
    _apply_params(params)


@app.route("/api/emulator/start", methods=["POST"])
def api_emulator_start():
    cfg = _load_config()
    data = request.get_json(force=True) if request.is_json else {}

    initrd = data.get("initramfs") or cfg.get("last_initramfs")
    if not initrd or not os.path.isfile(initrd):
        return jsonify({"error": "No firmware processed. Upload firmware first."}), 400

    web_port = data.get("web_port", cfg.get("web_port", config.DEFAULT_WEB_PORT))
    fallback_port = data.get("fallback_port", cfg.get("fallback_port", config.DEFAULT_FALLBACK_PORT))
    serial_port = config.DEFAULT_SERIAL_PORT

    try:
        qemu.start(
            initrd=initrd,
            web_port=web_port,
            fallback_port=fallback_port,
            serial_port=serial_port,
        )
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 500
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 409

    cfg["web_port"] = web_port
    cfg["fallback_port"] = fallback_port
    _save_config(cfg)

    # Restore saved SDI/reference config once the emulator finishes booting
    threading.Thread(target=_restore_saved_config, daemon=True).start()

    return jsonify({"message": "Emulator starting", "state": qemu.state})


@app.route("/api/emulator/stop", methods=["POST"])
def api_emulator_stop():
    qemu.stop()
    _clear_live_caches()
    return jsonify({"message": "Emulator stopped", "state": qemu.state})


@app.route("/api/emulator/restart", methods=["POST"])
def api_emulator_restart():
    cfg = _load_config()
    data = request.get_json(force=True) if request.is_json else {}

    try:
        qemu.restart(
            web_port=data.get("web_port", cfg.get("web_port")),
            fallback_port=data.get("fallback_port", cfg.get("fallback_port")),
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if "web_port" in data:
        cfg["web_port"] = data["web_port"]
    _save_config(cfg)

    return jsonify({"message": "Emulator restarting", "state": qemu.state})


@app.route("/api/sdi/set", methods=["POST"])
def api_sdi_set():
    if qemu.state != "running":
        return jsonify({"error": "Emulator is not running"}), 409

    data = request.get_json(force=True)
    cfg = _load_config()

    # Handle "all" shortcut
    if "all" in data:
        fmt = int(data["all"])
        sdi_formats = [fmt] * 8
        params = _build_sdi_params(fmt, sdi_mask=0xFF)
        params.extend(_build_vid_params(sdi_formats))
        ok, err = _apply_params(params)
        if err:
            return jsonify({"error": err}), 500

        cfg["sdi_formats"] = sdi_formats
        _save_config(cfg)
        return jsonify({"message": "All SDIs set to %d" % fmt, "set": ok})

    # Handle per-channel
    channels = data.get("channels", {})
    if not channels:
        return jsonify({"error": "No channels specified"}), 400

    profile = _get_current_profile()
    sdi_params = profile["sdi_params"]
    params = []
    sdi_formats = list(cfg.get("sdi_formats", [20, 20, 20, 20, 98, 98, 98, 98]))
    for ch, fmt in channels.items():
        ch_idx = int(ch) - 1
        fmt = int(fmt)
        sdi_formats[ch_idx] = fmt
        if ch_idx < len(sdi_params):
            params.append((sdi_params[ch_idx], fmt))

    # Also set Vid formats in the same pass (no polling delay)
    params.extend(_build_vid_params(sdi_formats))

    ok, err = _apply_params(params)
    if err:
        return jsonify({"error": err}), 500

    cfg["sdi_formats"] = sdi_formats
    _save_config(cfg)
    return jsonify({"message": "SDI formats updated", "set": ok})


@app.route("/api/reference/status")
def api_reference_status():
    """Read the current genlock source from the live device."""
    profile = _get_current_profile()
    result = {
        "bnc_value": profile["ref_bnc_value"] if profile else 0,
        "source": None,
        "source_name": None,
        "is_bnc": False,
    }
    if profile and qemu.state == "running":
        ref_sources = _get_live_ref_sources()
        val = webd.get_param("eParamID_GenlockSource", timeout=3.0)
        if val is not None:
            result["source"] = int(val)
            result["source_name"] = ref_sources.get(
                int(val), ref_sources.get(val, "Unknown"))
            result["is_bnc"] = int(val) == profile["ref_bnc_value"]
    return jsonify(result)


@app.route("/api/reference/set", methods=["POST"])
def api_reference_set():
    """Set the simulated BNC reference format (only valid when device is on BNC)."""
    if qemu.state != "running":
        return jsonify({"error": "Emulator is not running"}), 409

    data = request.get_json(force=True)
    ref_format = data.get("format")
    if ref_format is None:
        return jsonify({"error": "No format specified"}), 400

    # Verify the device is actually set to BNC
    profile = _get_current_profile()
    current_source = webd.get_param("eParamID_GenlockSource", timeout=3.0)
    if current_source is not None and int(current_source) != profile["ref_bnc_value"]:
        return jsonify({
            "error": "Genlock source is not set to Reference BNC. "
                     "Change it in the device web UI first."
        }), 409

    params = [("eParamID_DetectedReferenceFormat", int(ref_format))]
    ok, err = _apply_params(params)
    if err:
        return jsonify({"error": err}), 500

    cfg = _load_config()
    cfg["ref_format"] = int(ref_format)
    _save_config(cfg)

    return jsonify({"message": "BNC reference format set", "set": ok})


@app.route("/api/log")
def api_log():
    last_n = request.args.get("last", 0, type=int)
    return jsonify({"lines": qemu.get_log(last_n)})


@app.route("/api/formats")
def api_formats():
    profile = _get_current_profile()
    return jsonify({
        "sdi_formats": _get_live_formats() if profile else {},
        "ref_sources": _get_live_ref_sources() if profile else {},
        "input_count": len(profile["sdi_params"]) if profile else 0,
        "input_label": profile["input_label"] if profile else "",
    })


@app.route("/api/guest/exec", methods=["POST"])
def api_guest_exec():
    if qemu.state != "running":
        return jsonify({"error": "Emulator is not running"}), 409
    data = request.get_json(force=True)
    cmd = data.get("cmd", "")
    if not cmd:
        return jsonify({"error": "No command specified"}), 400
    try:
        output = qemu.send_command(cmd)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"output": output})


@app.route("/api/flash/status")
def api_flash_status():
    _ensure_dirs()
    images = {}
    total_size = 0
    for name in config.FLASH_IMAGES:
        path = os.path.join(config.FLASH_DIR, "%s.img" % name)
        exists = os.path.isfile(path)
        images[name] = exists
        if exists:
            total_size += os.path.getsize(path)
    return jsonify({
        "saved": any(images.values()),
        "images": images,
        "total_size": total_size,
    })


@app.route("/api/flash/download/<name>")
def api_flash_download(name):
    if name not in config.FLASH_IMAGES:
        return "", 404
    path = os.path.join(config.FLASH_DIR, "%s.img" % name)
    if not os.path.isfile(path):
        return "", 404
    return send_file(path, mimetype="application/octet-stream")


@app.route("/api/flash/save", methods=["POST"])
def api_flash_save():
    if qemu.state != "running":
        return jsonify({"error": "Emulator is not running"}), 409

    _ensure_dirs()
    cfg = _load_config()
    fallback_port = cfg.get("fallback_port", config.DEFAULT_FALLBACK_PORT)

    saved = []
    errors = []
    for name in config.FLASH_IMAGES:
        guest_src = "/tmp/flash/%s.img" % name
        guest_tmp = "/var/www/html/_flash_%s.img" % name
        host_dst = os.path.join(config.FLASH_DIR, "%s.img" % name)

        try:
            # Copy flash image to busybox httpd web root
            output = qemu.send_command(
                "cp %s %s && echo FLASH_CP_OK" % (guest_src, guest_tmp),
                timeout=10.0,
            )
            if "FLASH_CP_OK" not in output:
                errors.append("%s: copy failed" % name)
                continue

            # Download via HTTP from fallback httpd
            url = "http://127.0.0.1:%d/_flash_%s.img" % (fallback_port, name)
            tmp_path = host_dst + ".tmp"
            urllib.request.urlretrieve(url, tmp_path)
            os.replace(tmp_path, host_dst)
            saved.append(name)

        except Exception as e:
            errors.append("%s: %s" % (name, str(e)))
        finally:
            # Clean up guest copy
            try:
                qemu.send_command("rm -f %s" % guest_tmp, timeout=5.0)
            except Exception:
                pass

    if errors and not saved:
        return jsonify({"error": "Save failed: " + "; ".join(errors)}), 500

    total_size = sum(
        os.path.getsize(os.path.join(config.FLASH_DIR, "%s.img" % n))
        for n in saved if os.path.isfile(os.path.join(config.FLASH_DIR, "%s.img" % n))
    )
    msg = "Saved %d/%d flash images" % (len(saved), len(config.FLASH_IMAGES))
    if errors:
        msg += " (errors: %s)" % "; ".join(errors)
    return jsonify({"message": msg, "saved": saved, "total_size": total_size})


@app.route("/api/flash/reset", methods=["POST"])
def api_flash_reset():
    _ensure_dirs()
    removed = 0
    for name in config.FLASH_IMAGES:
        path = os.path.join(config.FLASH_DIR, "%s.img" % name)
        if os.path.isfile(path):
            os.remove(path)
            removed += 1
    return jsonify({
        "message": "Factory reset: removed %d saved images" % removed,
    })


@app.route("/api/config", methods=["POST"])
def api_config_update():
    data = request.get_json(force=True)
    cfg = _load_config()
    for key in ("web_port", "fallback_port", "flask_port"):
        if key in data:
            cfg[key] = int(data[key])
    _save_config(cfg)
    return jsonify({"message": "Configuration saved", "config": cfg})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _try_adopt_existing():
    """On startup, check if QEMU is already running and re-attach to it."""
    cfg = _load_config()
    adopted = qemu.adopt_existing(
        web_port=cfg.get("web_port", config.DEFAULT_WEB_PORT),
        fallback_port=cfg.get("fallback_port", config.DEFAULT_FALLBACK_PORT),
        initrd=cfg.get("last_initramfs"),
    )
    if adopted:
        print("  Re-adopted running QEMU instance")


if __name__ == "__main__":
    _ensure_dirs()
    _try_adopt_existing()
    cfg = _load_config()
    port = cfg.get("flask_port", config.DEFAULT_FLASK_PORT)
    print("AJA FS Emulator Control Panel")
    print("  Control Panel: http://localhost:%d/" % port)
    print()
    app.run(host="0.0.0.0", port=port, debug=False)
