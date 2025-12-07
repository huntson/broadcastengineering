#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
fs_mon.py – AJA FS-HDR/FS4/FS2 Monitoring Dashboard
Monitor and control AJA FS framestore units
"""

import os
import sys
import json
import copy
import threading
import time
import re
import requests
import tkinter as tk
import argparse
from pathlib import Path
from flask import Flask, render_template_string, request, redirect, url_for, jsonify, send_file

# GUI dialogs for license and settings
from gui_dialogs import LicenseDialog, PortSettingsDialog

app = Flask(__name__)

# ── Format maps ─────────────────────────────────────────────────────────────
FORMAT_MAP = {
    "525i5994": 3, "720p5994": 17, "1080i5994": 20, "1080PsF2398": 22,
    "1080PsF2997": 25, "1080p2398": 27, "1080p2997": 30, "1080p5994": 33,
    "2Kp2398": 43, "2Kp2997": 46, "2Kp5994": 49
}

print(f"[init] FORMAT_MAP size={len(FORMAT_MAP)}", flush=True)

# Configuration file - single JSON file for all settings
def _get_config_path():
    """Get config file path - next to exe in production, in app/ during development."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle (.exe) - store next to exe
        return os.path.join(os.path.dirname(sys.executable), "config.json")
    else:
        # Running as Python script (development) - store in app/ directory
        return os.path.join(os.path.dirname(__file__), "config.json")

CONFIG_FILE = _get_config_path()

prev_error_counts = {}      # (ip, channel) → last error total

PARAMS = {"name": "eParamID_SystemName", "temp": "eParamID_Temperature"}
for i in range(1, 5):
    PARAMS[f"sdi{i}"] = f"eParamID_Vid{i}DetectedInputFormat"
    PARAMS[f"vid{i}"] = f"eParamID_Vid{i}OutputFormat"


def _coerce_int(val):
    """Convert numeric strings to ints when possible for cleaner JSON."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return val


def _fs_audio_param(ch: int) -> str:
    return f"eParamID_Audio{ch}SamplesDelay"


def _fs_frame_param(ch: int) -> str:
    return f"eParamID_Vid{ch}ExtraFrameDelay"


def _fs_get_param(ip: str, paramid: str):
    resp = requests.get(
        f"http://{ip}/config",
        params={"action": "get", "paramid": paramid},
        timeout=1
    )
    resp.raise_for_status()
    js = resp.json()
    raw_val = js.get("value")
    return {
        "value": _coerce_int(raw_val),
        "display": js.get("value_name", raw_val)
    }


def _fs_set_param(ip: str, paramid: str, value):
    requests.get(
        f"http://{ip}/config",
        params={"action": "set", "paramid": paramid, "value": value},
        timeout=1
    ).raise_for_status()

# Note: License checking is now done via GUI in the main block

# ── Configuration Management ──────────────────────────────────────────────
def get_default_config():
    """Return default configuration structure."""
    return {
        "settings": {
            "host": "0.0.0.0",
            "port": 5070,
            "poll_interval": 1
        },
        "fs_units": [],
        "presets": {
            "1": {"name": "Preset 1", "fs_value": 1},
            "2": {"name": "Preset 2", "fs_value": 2},
            "3": {"name": "Preset 3", "fs_value": 3},
            "4": {"name": "Preset 4", "fs_value": 4}
        }
    }

def load_config():
    """Load configuration from config.json, create default if missing.
    Returns (config, is_first_run) tuple."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as fh:
                config = json.load(fh)
                # Ensure all sections exist (backward compatibility)
                default = get_default_config()
                if "settings" not in config:
                    config["settings"] = default["settings"]
                if "fs_units" not in config:
                    config["fs_units"] = default["fs_units"]
                if "presets" not in config:
                    config["presets"] = default["presets"]
                return config, False  # Not first run
        except Exception as e:
            print(f"[warn] Error loading config: {e}, using defaults", flush=True)
            default = get_default_config()
            return default, True  # Treat error as first run
    else:
        # Create default config file
        default = get_default_config()
        save_config(default)
        print(f"[init] Created default config at {CONFIG_FILE}", flush=True)
        return default, True  # First run

def save_config(config):
    """Save entire configuration to config.json."""
    with config_lock:
        with open(CONFIG_FILE, "w") as fh:
            json.dump(config, fh, indent=2)

# Note: Port configuration is now done via GUI in the main block

# Load configuration at startup
CONFIG, IS_FIRST_RUN = load_config()
POLL_INTERVAL = CONFIG["settings"]["poll_interval"]

# ── Helper functions for backward compatibility ────────────────────────────
def load_units():
    """Return list of FS units from config."""
    with config_lock:
        return list(CONFIG.get("fs_units", []))  # Return a copy to avoid external mutations

def save_units(lst):
    """Update FS units in config and save."""
    with config_lock:
        CONFIG["fs_units"] = lst
    save_config(CONFIG)

def load_presets():
    """Return presets structure from config."""
    with config_lock:
        # Return a deep copy to avoid external mutations
        return {"presets": copy.deepcopy(CONFIG.get("presets", {}))}

def save_presets(presets_data):
    """Update presets in config and save."""
    with config_lock:
        CONFIG["presets"] = presets_data.get("presets", {})
    save_config(CONFIG)

fs_units = {}
fs_units_lock = threading.Lock()
config_lock = threading.Lock()

# ── polling FS-HDR ─────────────────────────────────────────────────────────
def poll_unit(ip, model="FS4/HDR"):
    out = {"ip": ip, "error": False, "data": {}}
    max_ch = 2 if model == "FS2" else 4      # ← NEW
    for key, pid in PARAMS.items():
        if (m := re.match(r"(sdi|vid)(\d+)", key)) and int(m.group(2)) > max_ch:
            continue
        actual_pid = pid + "_5923" if key.startswith("vid") else pid
        try:
            js = requests.get(
                f"http://{ip}/config",
                params={"action": "get", "paramid": actual_pid},
                timeout=1
            ).json()

            # ---------- INPUT (SDI-x) channels ----------
            if key.startswith("sdi"):
                raw = js.get("value_name", js.get("value", "ERR"))
                fmt_only = raw.split(",", 1)[0].strip()          # "1080i 59.94"
                m = re.search(r"(\d+)\s+Errors", raw)
                err_cnt = int(m.group(1)) if m else 0

                ch = int(key[-1])                               # 1‒4
                inc = False
                if (ip, ch) in prev_error_counts and err_cnt > prev_error_counts[(ip, ch)]:
                    inc = True
                prev_error_counts[(ip, ch)] = err_cnt

                out["data"][key]              = fmt_only
                out["data"][f"err_inc_{ch}"]  = inc

            # ---------- OUTPUT (VID-x) channels ----------
            elif key.startswith("vid"):
                code = js.get("value")
                try:
                    code_int = int(code)
                except ValueError:
                    code_int = code
                out["data"][key] = next(
                    (k for k, v in FORMAT_MAP.items() if v == code_int),
                    str(code_int)
                )

            # ---------- everything else ----------
            else:
                out["data"][key] = js.get("value_name", js.get("value", "ERR"))

        except Exception:
            out["error"]      = True
            out["data"][key]  = "ERR"

    return out

# ── background loops ───────────────────────────────────────────────────────
def poll_loop():
    while True:
        for u in load_units():
            result = poll_unit(u["ip"], u.get("model", "FS4/HDR"))
            with fs_units_lock:
                fs_units[u["ip"]] = result
        time.sleep(POLL_INTERVAL)

# ── Flask routes ───────────────────────────────────────────────────────────
@app.route("/")
def index():
    with fs_units_lock:
        units = [
            fs_units.get(u["ip"], {"ip": u["ip"], "error": True, "data": {}})
            for u in load_units()
        ]
    model_map = {u["ip"]: u.get("model", "FS4/HDR") for u in load_units()}
    return render_template_string(
        MAIN_TEMPLATE,
        units=units,
        formats=list(FORMAT_MAP.keys()),
        model_map=json.dumps(model_map)
    )

@app.route("/compact")
def compact():
    # rebuild model_map here just like in index()
    model_map = {u["ip"]: u.get("model", "FS4/HDR") for u in load_units()}
    return render_template_string(
        COMPACT_TEMPLATE,
        model_map=json.dumps(model_map)
    )
@app.route("/add", methods=["POST"])
def add():
    ip = request.form.get("ip")
    model = request.form.get("model", "FS4/HDR")
    lst = load_units()
    if ip and not any(u["ip"] == ip for u in lst):
        lst.append({"ip": ip, "model": model})
        save_units(lst)
    return redirect(url_for("index"))

@app.route("/remove/<ip>")
def remove(ip):
    lst = load_units()
    lst2 = [u for u in lst if u["ip"] != ip]
    if len(lst2) != len(lst):
        save_units(lst2)
        with fs_units_lock:
            fs_units.pop(ip, None)
    return redirect(url_for("index"))

@app.route("/export")
def export():
    # Create a combined export file with both units and presets
    export_data = {
        "units": load_units(),
        "presets": load_presets()
    }

    # Store export file in same directory as config file
    export_file = os.path.join(os.path.dirname(CONFIG_FILE), "export.json")
    with open(export_file, "w") as fh:
        json.dump(export_data, fh, indent=2)

    return send_file(export_file, as_attachment=True, download_name="fs_dashboard_export.json")

@app.route("/import", methods=["POST"])
def import_file():
    # Maximum file size: 10MB
    MAX_FILE_SIZE = 10 * 1024 * 1024

    f = request.files.get("file")
    if not f:
        return "No file uploaded", 400

    # Validate file extension
    if not f.filename.endswith(".json"):
        return "Only .json files are allowed", 400

    # Validate content type
    if f.content_type and not f.content_type.startswith("application/json"):
        # Allow text/plain and empty content-type as some browsers send these for .json files
        if f.content_type not in ("text/plain", "application/octet-stream"):
            return "Invalid file type", 400

    # Store import temp file in same directory as config file
    import_file_path = os.path.join(os.path.dirname(CONFIG_FILE), "import_temp.json")

    try:
        # Read file with size limit
        file_content = f.read(MAX_FILE_SIZE + 1)
        if len(file_content) > MAX_FILE_SIZE:
            return "File too large (max 10MB)", 400

        # Write to temporary file
        with open(import_file_path, 'wb') as fh:
            fh.write(file_content)

        # Parse and validate JSON
        with open(import_file_path, 'r') as fh:
            import_data = json.load(fh)

        # Validate JSON structure
        if isinstance(import_data, dict):
            # New format with both units and presets
            if "units" in import_data:
                if not isinstance(import_data["units"], list):
                    raise ValueError("'units' must be a list")
                save_units(import_data["units"])
            if "presets" in import_data:
                if not isinstance(import_data["presets"], dict):
                    raise ValueError("'presets' must be a dictionary")
                save_presets(import_data["presets"])
        elif isinstance(import_data, list):
            # Legacy format - just units list
            save_units(import_data)
        else:
            raise ValueError("Invalid import format: expected object or array")

        # Clean up temporary file
        os.remove(import_file_path)

        return redirect(url_for("index"))

    except json.JSONDecodeError as e:
        # Clean up on error
        if os.path.exists(import_file_path):
            os.remove(import_file_path)
        return f"Invalid JSON file: {str(e)}", 400
    except ValueError as e:
        # Clean up on error
        if os.path.exists(import_file_path):
            os.remove(import_file_path)
        return f"Invalid data format: {str(e)}", 400
    except Exception as e:
        # Clean up on error
        if os.path.exists(import_file_path):
            os.remove(import_file_path)
        print(f"Error importing file: {e}")
        return f"Error importing file: {str(e)}", 500

@app.route("/data")
def data():
    with fs_units_lock:
        units_data = [
            fs_units.get(u["ip"], {"ip": u["ip"], "error": True, "data": {}})
            for u in load_units()
        ]
    return jsonify(units_data)


def _ensure_channel(ch):
    try:
        ch_int = int(ch)
    except (ValueError, TypeError):
        raise ValueError("Invalid channel")
    if ch_int < 1 or ch_int > 4:
        raise ValueError("Channel out of range")
    return ch_int


@app.route("/channel_params", methods=["POST"])
def channel_params():
    d = request.get_json(force=True) or {}
    ip = d.get("ip")
    ch = d.get("ch")
    if not ip:
        return jsonify(success=False, error="Missing IP"), 400
    try:
        ch_int = _ensure_channel(ch)
        audio_val = _fs_get_param(ip, _fs_audio_param(ch_int))
        frame_val = _fs_get_param(ip, _fs_frame_param(ch_int))
    except ValueError as ve:
        return jsonify(success=False, error=str(ve)), 400
    except Exception as exc:
        return jsonify(success=False, error=str(exc)), 500
    return jsonify(success=True, audio=audio_val, frame=frame_val)


@app.route("/channel_params/update", methods=["POST"])
def update_channel_params():
    d = request.get_json(force=True) or {}
    ip = d.get("ip")
    ch = d.get("ch")
    audio_delay = d.get("audio_delay")
    frame_delay = d.get("frame_delay")
    if not ip:
        return jsonify(success=False, error="Missing IP"), 400
    if audio_delay is None and frame_delay is None:
        return jsonify(success=False, error="Nothing to update"), 400
    try:
        ch_int = _ensure_channel(ch)
        if audio_delay is not None:
            _fs_set_param(ip, _fs_audio_param(ch_int), audio_delay)
        if frame_delay is not None:
            _fs_set_param(ip, _fs_frame_param(ch_int), frame_delay)
    except ValueError as ve:
        return jsonify(success=False, error=str(ve)), 400
    except Exception as exc:
        return jsonify(success=False, error=str(exc)), 500
    return jsonify(success=True)

@app.route("/set_format", methods=["POST"])
def set_format():
    d = request.get_json(force=True) or {}
    ip, ch, fmt = d.get("ip"), d.get("ch"), d.get("format")
    if not ip or not ch or fmt not in FORMAT_MAP:
        return jsonify(success=False), 400
    pid = f"{PARAMS[f'vid{ch}']}_5923"
    try:
        requests.get(
            f"http://{ip}/config",
            params={"action": "set", "paramid": pid, "value": FORMAT_MAP[fmt]},
            timeout=1
        ).raise_for_status()
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500
    return jsonify(success=True)

@app.route("/presets")
def get_presets():
    return jsonify(load_presets())

@app.route("/presets", methods=["POST"])
def update_presets():
    presets_data = request.get_json(force=True) or {}
    save_presets(presets_data)
    return jsonify(success=True)

@app.route("/recall_preset", methods=["POST"])
def recall_preset():
    d = request.get_json(force=True) or {}
    preset_num = d.get("preset")
    selected_fs_units = d.get("fs_units", [])

    presets_data = load_presets()
    preset = presets_data.get("presets", {}).get(str(preset_num))

    if not preset:
        return jsonify(success=False, error="Preset not found"), 400

    results = {"fs_results": []}

    # FS-HDR/FS2 preset recall
    for ip in selected_fs_units:
        try:
            # Send recall command to FS unit
            response = requests.get(
                f"http://{ip}/config",
                params={
                    "action": "set",
                    "paramid": "eParamID_RegisterRecall",
                    "value": preset["fs_value"]
                },
                timeout=1
            )
            response.raise_for_status()
            results["fs_results"].append({"ip": ip, "success": True})
        except Exception as e:
            results["fs_results"].append({"ip": ip, "success": False, "error": str(e)})

    return jsonify(results)

# ── HTML templates (MAIN + COMPACT) ─────────────────────────────────────────
MAIN_TEMPLATE = """
<!DOCTYPE html><html><head>
<title>Pegasus Frame Sync Dashboard</title>
<style>
 :root{--bg:#111;--fg:#eee;--tile:#222;--border:#444;--yellow:#5a5200;--error:#300}
 body{background:var(--bg);color:var(--fg);font-family:sans-serif;padding:20px;}
 h1{text-align:center;margin-bottom:20px}
 .unit{margin-bottom:12px}
 .unit-header{font-weight:bold;margin-bottom:8px;font-size:1.1em;text-align:center}
 .tile-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:0}
.tile{
  position:relative;
  background:var(--tile);
  padding:4px;
  border:1px solid var(--border);
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:flex-start;
  height:50px;
  font-size:.8em;
  line-height:1.1em
}

 .tile.highlight{background:var(--yellow)} .tile.error{background:var(--error)}
 .tile.good{background:#28a745}
 .top-actions{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:15px;justify-content:space-between}
 .preset-container{display:flex;flex-direction:column;align-items:center;gap:5px;background:var(--tile);border:1px solid var(--border);border-radius:6px;padding:8px 12px}
 .preset-container::before{content:"PRESETS: (right-click to rename)";font-size:0.8em;color:var(--fg);margin-bottom:5px;font-weight:bold}
 .preset-buttons{display:flex;gap:5px}
 .preset-recall-btn{padding:6px 12px;font-size:0.9em}
 .custom-dropdown{position:absolute;top:4px;right:4px}
 .dropdown-button{background:var(--tile);border:1px solid var(--border);padding:.3em .8em .3em .5em;
                  cursor:pointer;color:var(--fg);position:relative}
 .dropdown-button::after{content:"▼";position:absolute;right:.4em;top:50%;transform:translateY(-50%);
                         font-size:.6em;pointer-events:none}
 .dropdown-menu{position:absolute;top:100%;right:0;background:var(--tile);border:1px solid var(--border);
                list-style:none;margin:0;padding:0;max-height:200px;overflow-y:auto;z-index:100;display:none}
 .dropdown-menu li{padding:.3em .5em;cursor:pointer}
 .dropdown-menu li:hover{background:var(--border)}

/* Preset Dialog Styles */
#preset-dialog {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.7);
  display: none;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

#preset-dialog-content {
  background: var(--tile);
  border: 2px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  max-width: 600px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
}

.preset-section {
  margin-bottom: 20px;
}

.preset-section h3 {
  color: var(--fg);
  margin-bottom: 10px;
}

.preset-buttons {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.preset-button {
  padding: 10px 20px;
  background: var(--tile);
  border: 1px solid var(--border);
  color: var(--fg);
  cursor: pointer;
  border-radius: 4px;
}

.preset-button:hover {
  background: var(--border);
}

.preset-button.selected {
  background: var(--yellow);
  color: #000;
}

.unit-checkbox {
  margin: 5px 0;
}

.unit-checkbox label {
  margin-left: 8px;
  cursor: pointer;
}

.dialog-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 20px;
}

/* Channel Control Dialog */
#channel-dialog {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.7);
  display: none;
  justify-content: center;
  align-items: center;
  z-index: 1002;
}

#channel-dialog .dialog-content {
  background: var(--tile);
  border: 2px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  width: 95%;
  max-width: 420px;
  color: var(--fg);
}

#channel-dialog .control-row {
  margin-bottom: 16px;
}

#channel-dialog .control-label {
  font-size: 0.9em;
  margin-bottom: 6px;
  display: block;
}

#channel-dialog .slider-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
}

#channel-dialog input[type="range"] {
  flex: 1;
  -webkit-appearance: none;
  height: 4px;
  border-radius: 4px;
  background: var(--border);
  outline: none;
}

#channel-dialog input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #28a745;
  cursor: pointer;
}

#channel-dialog .slider-value {
  min-width: 60px;
  text-align: right;
  font-family: monospace;
  font-size: 0.9em;
}

#channel-dialog small {
  display: block;
  font-size: 0.75em;
  color: #bbb;
  margin: 4px 0 12px;
}

#channel-dialog .dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 10px;
}

.dialog-actions button {
  padding: 8px 16px;
  border: 1px solid var(--border);
  background: var(--tile);
  color: var(--fg);
  cursor: pointer;
  border-radius: 4px;
}

.dialog-actions button:hover {
  background: var(--border);
}

.dialog-actions button.primary {
  background: #28a745;
  color: white;
}

.dialog-actions button.primary:hover {
  background: #218838;
}

</style></head><body>
<h1>Pegasus Frame Sync Dashboard</h1>

<div class="top-actions">
  <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center">
    <form method="POST" action="/add" style="display:flex;gap:8px;align-items:center">
      <input type="text" name="ip" placeholder="FS IP address" required>
      <select name="model"><option value="FS4/HDR">FS4/HDR</option><option value="FS2">FS2</option></select>
      <button>Add</button>
    </form>
    <form method="POST" action="/import" enctype="multipart/form-data">
      <input type="file" name="file" accept=".json" required><button>Import</button></form>
    <form method="GET" action="/export"><button>Export</button></form>
    <a href="/compact"><button type="button">Compact View</button></a>
  </div>
  <div class="preset-container">
    <div class="preset-buttons">
      <button type="button" class="preset-recall-btn" onclick="showPresetRecallDialog('1')">Preset 1</button>
      <button type="button" class="preset-recall-btn" onclick="showPresetRecallDialog('2')">Preset 2</button>
      <button type="button" class="preset-recall-btn" onclick="showPresetRecallDialog('3')">Preset 3</button>
      <button type="button" class="preset-recall-btn" onclick="showPresetRecallDialog('4')">Preset 4</button>
    </div>
  </div>
</div>

<div id="units-container"></div>

<!-- Preset Dialog -->
<div id="preset-dialog">
  <div id="preset-dialog-content">
    <h2 id="preset-dialog-title">Preset Recall</h2>

    <div class="preset-section">
      <h3>Select FS-HDR/FS2 Units: <button type="button" onclick="selectAllFs()" style="margin-left: 10px; padding: 2px 8px; font-size: 0.8em;">Select All</button></h3>
      <div id="fs-checkboxes"></div>
    </div>
    
    <div class="dialog-actions">
      <button onclick="closePresetDialog()">Cancel</button>
      <button class="primary" onclick="recallPreset()">Recall Preset</button>
    </div>
  </div>
</div>

<!-- Preset Name Edit Dialog -->
<div id="preset-edit-dialog" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.7); display: none; justify-content: center; align-items: center; z-index: 1001;">
  <div style="background: var(--tile); border: 2px solid var(--border); border-radius: 8px; padding: 20px; max-width: 400px; width: 90%;">
    <h3>Edit Preset Name</h3>
    <input type="text" id="preset-name-input" placeholder="Enter preset name" style="width: 100%; padding: 8px; margin: 10px 0;">
    <div style="text-align: right; margin-top: 15px;">
      <button onclick="cancelPresetEdit()" style="margin-right: 10px;">Cancel</button>
      <button onclick="savePresetName()" class="primary">Save</button>
    </div>
  </div>
</div>

<!-- Channel Control Dialog -->
<div id="channel-dialog">
  <div class="dialog-content">
    <h3 id="channel-dialog-title">Channel Controls</h3>
    <div class="control-row">
      <span class="control-label">Audio Samples Delay</span>
      <div class="slider-wrapper">
        <input type="range" id="audio-delay-slider" min="-768" max="12288" step="1">
        <span class="slider-value" id="audio-delay-value">0</span>
      </div>
      <small id="audio-delay-display"></small>
    </div>
    <div class="control-row">
      <span class="control-label">Extra Frame Delay</span>
      <div class="slider-wrapper">
        <input type="range" id="frame-delay-slider" min="0" max="6" step="1">
        <span class="slider-value" id="frame-delay-value">0</span>
      </div>
      <small id="frame-delay-display"></small>
    </div>
    <div id="channel-dialog-error" style="color:#f66;font-size:0.85em;min-height:18px;"></div>
    <div class="dialog-actions">
      <button onclick="closeChannelDialog()">Close</button>
    </div>
  </div>
</div>

<script>
const FORMAT_LIST = {{ formats|tojson }};
const MODEL_MAP   = {{ model_map|safe }};
const pending     = {};

let selectedPreset = null;
let presetsData = null;
let editingPresetNumber = null;
let channelDialogTarget = null;
let channelDialogSnapshot = null;
const channelUpdateState = { timer: null, inflight: false, pending: false };

const channelControls = {
  audio: {
    slider: document.getElementById('audio-delay-slider'),
    valueEl: document.getElementById('audio-delay-value'),
    displayEl: document.getElementById('audio-delay-display'),
    resetValue: 0
  },
  frame: {
    slider: document.getElementById('frame-delay-slider'),
    valueEl: document.getElementById('frame-delay-value'),
    displayEl: document.getElementById('frame-delay-display'),
    resetValue: 0
  }
};

Object.entries(channelControls).forEach(([key, ctrl]) => {
  ctrl.slider.addEventListener('input', () => {
    updateControlValue(key);
    scheduleChannelUpdate();
  });
  ctrl.slider.addEventListener('dblclick', () => {
    ctrl.slider.value = ctrl.resetValue;
    updateControlValue(key);
    scheduleChannelUpdate();
  });
});

function updateControlValue(key) {
  const ctrl = channelControls[key];
  ctrl.valueEl.textContent = ctrl.slider.value;
}

function setControlData(key, data) {
  const ctrl = channelControls[key];
  let val = data && data.value;
  if (val === undefined || val === null || val === '') {
    val = ctrl.resetValue;
  }
  val = Number(val);
  if (Number.isNaN(val)) {
    val = ctrl.resetValue;
  }
  // clamp to slider bounds
  const min = Number(ctrl.slider.min);
  const max = Number(ctrl.slider.max);
  if (!Number.isNaN(min)) val = Math.max(val, min);
  if (!Number.isNaN(max)) val = Math.min(val, max);
  ctrl.slider.value = val;
  ctrl.valueEl.textContent = val;
  ctrl.displayEl.textContent = data && data.display ? `Reported: ${data.display}` : '';
}

function setChannelDialogError(msg = '') {
  document.getElementById('channel-dialog-error').textContent = msg;
}

function setChannelDialogLoading(isLoading, message = '') {
  channelControls.audio.slider.disabled = isLoading;
  channelControls.frame.slider.disabled = isLoading;
  setChannelDialogError(message);
}

function populateChannelDialog(audio, frame) {
  setControlData('audio', audio);
  setControlData('frame', frame);
}

function resetChannelUpdateState() {
  if (channelUpdateState.timer) {
    clearTimeout(channelUpdateState.timer);
    channelUpdateState.timer = null;
  }
  channelUpdateState.inflight = false;
  channelUpdateState.pending = false;
}

function openChannelDialog(ip, ch, label) {
  channelDialogTarget = { ip, ch };
  channelDialogSnapshot = null;
  resetChannelUpdateState();
  document.getElementById('channel-dialog-title').textContent = `${label} – ${ip}`;
  document.getElementById('channel-dialog').style.display = 'flex';
  populateChannelDialog(null, null);
  setChannelDialogLoading(true, 'Loading…');
  fetch('/channel_params', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ip, ch })
  })
    .then(r => r.json())
    .then(data => {
      if (!data.success) throw new Error(data.error || 'Unable to load');
      populateChannelDialog(data.audio, data.frame);
      channelDialogSnapshot = {
        audio: Number(channelControls.audio.slider.value),
        frame: Number(channelControls.frame.slider.value)
      };
      setChannelDialogLoading(false, '');
    })
    .catch(err => {
      setChannelDialogLoading(false, err.message);
    });
}

function closeChannelDialog() {
  document.getElementById('channel-dialog').style.display = 'none';
  channelDialogTarget = null;
  channelDialogSnapshot = null;
  resetChannelUpdateState();
  setChannelDialogError('');
  populateChannelDialog(null, null);
}

function scheduleChannelUpdate() {
  if (!channelDialogTarget) return;
  setChannelDialogError('');
  if (channelUpdateState.inflight) {
    channelUpdateState.pending = true;
    return;
  }
  if (channelUpdateState.timer) {
    clearTimeout(channelUpdateState.timer);
  }
  channelUpdateState.timer = setTimeout(pushChannelUpdates, 200);
}

function pushChannelUpdates() {
  channelUpdateState.timer = null;
  if (!channelDialogTarget) return;
  const payload = { ip: channelDialogTarget.ip, ch: channelDialogTarget.ch };
  const audioVal = Number(channelControls.audio.slider.value);
  const frameVal = Number(channelControls.frame.slider.value);
  const snapshot = channelDialogSnapshot || {};
  let hasChange = false;
  if (!Number.isNaN(audioVal) && (snapshot.audio === undefined || audioVal !== snapshot.audio)) {
    payload.audio_delay = audioVal;
    hasChange = true;
  }
  if (!Number.isNaN(frameVal) && (snapshot.frame === undefined || frameVal !== snapshot.frame)) {
    payload.frame_delay = frameVal;
    hasChange = true;
  }
  if (!hasChange) return;
  channelUpdateState.inflight = true;
  fetch('/channel_params/update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
    .then(r => r.json())
    .then(data => {
      if (!data.success) throw new Error(data.error || 'Update failed');
      if (!channelDialogSnapshot) channelDialogSnapshot = {};
      if ('audio_delay' in payload) {
        channelDialogSnapshot.audio = payload.audio_delay;
        channelControls.audio.displayEl.textContent = `Reported: ${payload.audio_delay}`;
      }
      if ('frame_delay' in payload) {
        channelDialogSnapshot.frame = payload.frame_delay;
        channelControls.frame.displayEl.textContent = `Reported: ${payload.frame_delay}`;
      }
      loadData();
    })
    .catch(err => {
      setChannelDialogError(err.message);
    })
    .finally(() => {
      channelUpdateState.inflight = false;
      if (channelUpdateState.pending) {
        channelUpdateState.pending = false;
        scheduleChannelUpdate();
      }
    });
}

function showPresetRecallDialog(presetNumber) {
  selectedPreset = presetNumber;
  
  fetch('/presets')
    .then(r => r.json())
    .then(data => {
      presetsData = data;
      const presetName = presetsData.presets[presetNumber] ? presetsData.presets[presetNumber].name : 'Preset ' + presetNumber;
      document.getElementById('preset-dialog-title').textContent = 'Recall: ' + presetName;
      populateUnitCheckboxes();
      document.getElementById('preset-dialog').style.display = 'flex';
    });
}

function closePresetDialog() {
  document.getElementById('preset-dialog').style.display = 'none';
  selectedPreset = null;
}

function updatePresetButtonLabels() {
  if (!presetsData) return;
  
  const buttons = document.querySelectorAll('.preset-recall-btn');
  buttons.forEach((btn, index) => {
    const presetNum = (index + 1).toString();
    const preset = presetsData.presets[presetNum];
    if (preset) {
      btn.textContent = preset.name;
    }
  });
}

function selectAllFs() {
  const checkboxes = document.querySelectorAll('#fs-checkboxes input[type="checkbox"]');
  checkboxes.forEach(cb => cb.checked = true);
}

function populateUnitCheckboxes() {
  // Populate FS unit checkboxes
  fetch('/data')
    .then(r => r.json())
    .then(units => {
      const fsContainer = document.getElementById('fs-checkboxes');
      fsContainer.innerHTML = '';
      units.forEach(unit => {
        if (!unit.error) {
          const div = document.createElement('div');
          div.className = 'unit-checkbox';
          div.innerHTML = 
            '<input type="checkbox" id="fs-' + unit.ip + '" value="' + unit.ip + '">' +
            '<label for="fs-' + unit.ip + '">' + (unit.data.name || 'UNKNOWN') + ' (' + unit.ip + ')</label>';
          fsContainer.appendChild(div);
        }
      });
    });
}

function recallPreset() {
  if (!selectedPreset) {
    alert('Please select a preset first.');
    return;
  }

  const selectedFsUnits = Array.from(document.querySelectorAll('#fs-checkboxes input[type="checkbox"]:checked'))
    .map(cb => cb.value);

  if (selectedFsUnits.length === 0) {
    alert('Please select at least one FS unit.');
    return;
  }

  fetch('/recall_preset', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      preset: selectedPreset,
      fs_units: selectedFsUnits
    })
  })
  .then(r => r.json())
  .then(results => {
    let message = 'Preset recall completed:\\n\\n';

    if (results.fs_results.length > 0) {
      message += 'FS Unit Results:\\n';
      results.fs_results.forEach(result => {
        message += '  ' + result.ip + ': ' + (result.success ? 'Success' : 'Failed - ' + result.error) + '\\n';
      });
    }

    alert(message);
    closePresetDialog();
  })
  .catch(error => {
    alert('Error recalling preset: ' + error.message);
  });
}

function editPresetName(presetNumber) {
  editingPresetNumber = presetNumber;
  
  fetch('/presets')
    .then(r => r.json())
    .then(data => {
      presetsData = data;
      const currentName = presetsData.presets[presetNumber] ? presetsData.presets[presetNumber].name : 'Preset ' + presetNumber;
      document.getElementById('preset-name-input').value = currentName;
      document.getElementById('preset-edit-dialog').style.display = 'flex';
    });
}

function savePresetName() {
  if (!editingPresetNumber) return;
  
  const newName = document.getElementById('preset-name-input').value.trim();
  if (!newName) {
    alert('Please enter a preset name.');
    return;
  }
  
  if (!presetsData.presets[editingPresetNumber]) {
    presetsData.presets[editingPresetNumber] = {};
  }
  presetsData.presets[editingPresetNumber].name = newName;
  
  fetch('/presets', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(presetsData)
  })
  .then(r => r.json())
  .then(result => {
    if (result.success) {
      updatePresetButtonLabels();
      cancelPresetEdit();
    } else {
      alert('Error saving preset name.');
    }
  })
  .catch(error => {
    alert('Error saving preset name: ' + error.message);
  });
}

function cancelPresetEdit() {
  document.getElementById('preset-edit-dialog').style.display = 'none';
  document.getElementById('preset-name-input').value = '';
  editingPresetNumber = null;
}

function getChannelLabels(name,n){
  if(name){
    let m=name.match(/(\\d+)\\s*-\\s*(\\d+)/);
    if(m){let a=parseInt(m[1]);return Array.from({length:n},(_,i)=>"FS "+(a+i));}
    m=name.match(/(\\d+)(?!.*-)/);
    if(m){let a=parseInt(m[1]);return Array.from({length:n},(_,i)=>"FS "+(a+i));}
  }
  return Array.from({length:n},(_,i)=>"VIDEO "+(i+1));
}

function loadData(){
  if([...document.querySelectorAll('.dropdown-menu')].some(m=>getComputedStyle(m).display==='block')) return;

  /* FS-HDR units */
  fetch('/data').then(r=>r.json()).then(units=>{
    const container=document.getElementById('units-container');
    container.querySelectorAll('.unit').forEach(e=>e.remove());
    units.forEach(u=>{
      const model=MODEL_MAP[u.ip]||"FS4/HDR";
      const numCh= model==="FS2"?2:4;
      const sec=document.createElement('div');sec.className='unit';
      const hdr=document.createElement('div');hdr.className='unit-header';
hdr.innerHTML = `
  <a href="http://${u.ip}" target="_blank" style="color:inherit;
      text-decoration:none;display:block;">
    <strong>${u.data.name || 'UNKNOWN'}</strong>
     | ${u.ip} | Temp: ${u.data.temp || 'N/A'}
     <span style="font-size:.8em;color:#9ef">[${model}]</span>
  </a>
  <a href="/remove/${u.ip}" style="float:right;color:red">🗑</a>
`;

      sec.appendChild(hdr);

      const grid=document.createElement('div');grid.className='tile-grid';
      grid.style.gridTemplateColumns=`repeat(${numCh},1fr)`;
      const labels = getChannelLabels(u.data.name, numCh);

      for(let i=1;i<=numCh;i++){
        const t=document.createElement('div');t.className='tile';
        if(u.error){ t.classList.add('error'); grid.appendChild(t); continue; }
        const sdi=u.data['sdi'+i], vid=u.data['vid'+i];
        const inc = u.data['err_inc_' + i];          // boolean from poll_unit
        if (sdi !== vid || inc) {
            t.classList.add('highlight');   // yellow when SDI ≠ OUT
        } else {
            t.classList.add('good');        // green when SDI = OUT
        }
        t.addEventListener('contextmenu', e => {
          e.preventDefault();
          openChannelDialog(u.ip, i, labels[i-1]);
        });
        const key=`${u.ip}_${i}`, display=pending[key]||vid;
        const dd=document.createElement('div');dd.className='custom-dropdown';
        const btn=document.createElement('button');btn.className='dropdown-button';btn.textContent=display;
        const menu=document.createElement('ul');menu.className='dropdown-menu';

        FORMAT_LIST.forEach(fm=>{
          const li=document.createElement('li');
          li.textContent=fm;
          li.onclick=()=>{
            pending[key]=fm;
            btn.textContent=fm;
            menu.style.display='none';
            fetch('/set_format',{
              method:'POST',
              headers:{'Content-Type':'application/json'},
              body:JSON.stringify({ip:u.ip,ch:i,format:fm})
            }).then(()=>loadData());
          };
          menu.appendChild(li);
        });

        menu.style.display = 'none';
btn.addEventListener('click', e => {
  e.stopPropagation();
  // close any other open dropdown
  document.querySelectorAll('.dropdown-menu').forEach(m => {
    if (m !== menu) m.style.display = 'none';
  });
  // toggle this one
  menu.style.display =
    getComputedStyle(menu).display === 'block' ? 'none' : 'block';
});

        t.innerHTML = `<div><strong>${labels[i-1]}</strong></div>
                       <div>IN: ${sdi}</div><div>OUT: ${display}</div>`;
        dd.appendChild(btn);
        dd.appendChild(menu);
        t.appendChild(dd);
        grid.appendChild(t);
      }

      sec.appendChild(grid);
      container.appendChild(sec);
    });
  });
}

// periodically reload
setInterval(loadData,1000);
loadData();

// Add event listeners for preset buttons
document.addEventListener('contextmenu', function(e) {
  if (e.target.classList.contains('preset-recall-btn')) {
    e.preventDefault();
    const presetNumber = Array.from(document.querySelectorAll('.preset-recall-btn')).indexOf(e.target) + 1;
    editPresetName(presetNumber.toString());
  }
});

document.getElementById('channel-dialog').addEventListener('click', function(e) {
  if (e.target.id === 'channel-dialog') {
    closeChannelDialog();
  }
});

// Load preset names on page load
function loadPresetNames() {
  fetch('/presets')
    .then(r => r.json())
    .then(data => {
      presetsData = data;
      updatePresetButtonLabels();
    });
}

// Load preset names when page loads
loadPresetNames();

// only close menus when clicking outside a .custom-dropdown
 document.addEventListener('click', e => {
   if (!e.target.closest('.custom-dropdown')) {
     document.querySelectorAll('.dropdown-menu')
             .forEach(m => m.style.display = 'none');
   }
 });
</script>
</body></html>
"""

COMPACT_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Compact FS-HDR Monitor</title>
  <style>
    body{background:#000;color:#eee;font-family:sans-serif;padding:10px;font-size:.9em;}
    .unit-container{display:flex;flex-wrap:wrap;gap:20px;margin-bottom:20px;}
    .bullets{display:inline-flex;gap:4px;margin-left:4px;}
    .bullet{width:10px;height:10px;border-radius:50%;background:green;display:inline-block;}
    .bullet.yellow{background:yellow;}
  </style>
</head>
<body>
  <h2>FS-HDR Video Paths</h2>
  <div id="fs" class="unit-container"></div>

<script>
function bullet(y){ return `<span class='bullet${y?" yellow":""}'></span>`; }
const MODEL_MAP = {{ model_map | safe }};
function load(){
  // FS-HDR
  fetch('/data').then(r=>r.json()).then(units=>{
    const c = document.getElementById('fs');
    c.innerHTML = '';
    units.forEach(u=>{
      if(u.error) return;
      // look up model (e.g. "FS2" or "FS-2") and pick 2 vs 4 channels
        const model = MODEL_MAP[u.ip] || "FS4/HDR";
        const numCh = /FS-?2/i.test(model) ? 2 : 4;
        let mismatch = false, dots = [];
        for (let i = 1; i <= numCh; i++) {
         const inc = u.data['err_inc_' + i];                  // NEW
          const h   = (u.data['sdi' + i] !== u.data['vid' + i]) || inc;
          dots.push(`<span class='bullet${h ? " yellow" : ""}'></span>`);
          if (h) mismatch = true;
        }
      const div = document.createElement('div');
      div.className = 'unit';
      div.innerHTML = `<div><strong>${u.data.name||'UNKNOWN'}</strong> (${u.ip})</div>
                       <div class='bullets'>${dots.join(' ')}</div>`;
      c.appendChild(div);
    });
  });
}
setInterval(load,1000);
load();
</script>
</body></html>
"""

def check_license():
    """Show license dialog and verify before starting Flask."""
    root = tk.Tk()
    root.withdraw()  # Hide main window
    root.update()  # Process pending events

    license_valid = False

    def on_status_change(status):
        nonlocal license_valid
        license_valid = status.ok
        if status.ok:
            root.quit()  # Exit Tkinter loop when valid

    from license import LicenseManager, LicenseStatus
    manager = LicenseManager(
        root,
        on_status_change=on_status_change
    )

    manager.ensure_dialog()  # Show dialog if not licensed

    if not license_valid:
        root.deiconify()  # Make sure root is visible for the dialog
        root.lift()  # Bring to front
        root.mainloop()  # Block until license validated

    # Check if window still exists before destroying
    try:
        if root.winfo_exists():
            root.destroy()
    except:
        pass  # Window already destroyed

    return license_valid

if __name__ == '__main__':
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='FS-HDR Monitor')
    parser.add_argument('-f', '--force', action='store_true',
                        help='Force run without license (testing only)')
    parser.add_argument('--console', action='store_true',
                        help='Run in console mode without GUI')
    args = parser.parse_args()

    # License check
    if args.force:
        print("\n" + "="*60)
        print("⚠️  RUNNING UNLICENSED (Testing Mode)")
        print("="*60)
    else:
        # Check license before starting server
        if not check_license():
            print("\n" + "="*60)
            print("ERROR: Valid license required to run FS-HDR Monitor")
            print("="*60)
            print("\nPlease contact your administrator for a license key.")
            print("\nPress Enter to exit...")
            input()
            exit(1)

        print("\n" + "="*60)
        print("✓ License validated")
        print("="*60)

    # Prompt for port configuration on first run with GUI dialog
    if IS_FIRST_RUN and not args.console:
        from gui_dialogs import PortSettingsDialog
        startup_root = tk.Tk()
        startup_root.withdraw()
        port_dialog = PortSettingsDialog(startup_root, Path(CONFIG_FILE))
        new_port = port_dialog.prompt_for_port(CONFIG["settings"]["port"])
        if new_port and new_port != CONFIG["settings"]["port"]:
            CONFIG["settings"]["port"] = new_port
        startup_root.destroy()

    # Start background polling thread
    threading.Thread(target=poll_loop, daemon=True).start()

    # Get final settings
    host = CONFIG["settings"]["host"]
    port = CONFIG["settings"]["port"]

    # Start server based on mode
    if args.console:
        # Console mode - original behavior
        print(f"\nStarting FS-HDR Monitor on http://{host}:{port}\n")
        app.run(debug=False, host=host, port=port)
    else:
        # GUI mode - run Flask in background thread
        print(f"Starting FS-HDR Monitor on http://{host}:{port}")

        def run_flask():
            app.run(debug=False, host=host, port=port, use_reloader=False)

        # Start Flask in daemon thread
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()

        # Create and run GUI
        from gui import FSHDRMonitorGUI

        def quit_callback():
            """Called when GUI is closed."""
            sys.exit(0)

        gui = FSHDRMonitorGUI(host, port, Path(CONFIG_FILE), on_quit_callback=quit_callback)
        gui.run()
