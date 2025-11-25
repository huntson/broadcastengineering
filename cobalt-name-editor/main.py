from flask import Flask, request, jsonify, render_template
import hashlib
import json
from uuid import uuid4
from device_interface import download_config
from parser import extract_names, rebuild_file as render_config
import tempfile
import os
import requests
import concurrent.futures
import configparser
from pathlib import Path
import tkinter as tk
import sys
import argparse
import threading
from license import LicenseManager, LicenseStatus, storage as license_storage
from gui import CobaltGUI


# Load configuration
config = configparser.ConfigParser()
config_path = Path(__file__).parent / 'config.ini'

# If config.ini doesn't exist, copy from example
if not config_path.exists():
    example_path = Path(__file__).parent / 'config.ini.example'
    if example_path.exists():
        import shutil
        shutil.copy(example_path, config_path)

config.read(config_path)

# Get config values with defaults
HOST = config.get('server', 'host', fallback='0.0.0.0')
PORT = config.getint('server', 'port', fallback=5050)
DEBUG = config.getboolean('server', 'debug', fallback=True)
DOWNLOAD_TIMEOUT = config.getint('timeouts', 'download_timeout', fallback=10)
UPLOAD_TIMEOUT = config.getint('timeouts', 'upload_timeout', fallback=30)

app = Flask(__name__)

def upload_and_capture(ip: str, file_text: str, timeout: int = None) -> str:
    if timeout is None:
        timeout = UPLOAD_TIMEOUT
    base = ip if ip.startswith("http") else f"http://{ip}"
    base = base.rstrip("/")
    url  = f"{base}/cgi-bin/update-config.cgi"
    files = {
        "file_data": ("primary.txt", file_text, "text/plain")
    }
    r = requests.post(url, files=files, timeout=timeout)
    r.raise_for_status()
    return r.text.strip() or "«empty»"


def _identical(texts):
    hashes = [hashlib.sha256(t.encode('utf-8')).hexdigest() for t in texts]
    return len(set(hashes)) == 1

@app.route('/')
def index():
    return render_template('index.html')

@app.route("/get_saved_ips", methods=["GET"])
def get_saved_ips():
    """Retrieve saved device IPs from persistent storage."""
    settings = license_storage.load_settings()
    ips = settings.get("device_ips", "")
    return jsonify(ips=ips)

@app.route("/save_ips", methods=["POST"])
def save_ips():
    """Save device IPs to persistent storage."""
    data = request.get_json()
    ips = data.get("ips", "")
    settings = license_storage.load_settings()
    settings["device_ips"] = ips
    license_storage.save_settings(settings)
    return jsonify(success=True)

@app.route("/get_default_names", methods=["GET"])
def get_default_names():
    """Retrieve saved default device names from persistent storage."""
    settings = license_storage.load_settings()
    default_names = settings.get("default_names", "")
    if default_names:
        # Parse JSON array from string
        try:
            names = json.loads(default_names)
            return jsonify(names=names)
        except:
            return jsonify(names=[])
    return jsonify(names=[])

@app.route("/save_default_names", methods=["POST"])
def save_default_names():
    """Save current device names as default template."""
    data = request.get_json()
    names = data.get("names", [])
    settings = license_storage.load_settings()
    # Store as JSON array string
    settings["default_names"] = json.dumps(names)
    license_storage.save_settings(settings)
    return jsonify(success=True, count=len(names))

@app.route("/download", methods=["POST"])
def download():
    data = request.get_json()
    ips = data.get("ips", [])
    override = data.get("overrideDifferences", False)

    texts, errs = [], {}
    for ip in ips:
        try:
            texts.append(download_config(ip, timeout=DOWNLOAD_TIMEOUT))
        except Exception as e:
            errs[ip] = str(e)

    if errs:
        return jsonify(error="Download errors", details=errs), 400
    if not override and not _identical(texts):
        return jsonify(error="Configs differ"), 409

    token = os.urandom(8).hex()
    tmp = tempfile.gettempdir()
    with open(f"{tmp}/{token}.orig", "w") as f:
        f.write(texts[0])
    with open(f"{tmp}/{token}.ips", "w") as f:
        f.write("\n".join(ips))

    return jsonify(token=token, names=extract_names(texts[0]))


def threaded_upload(ip, newfile):
    try:
        return ip, upload_and_capture(ip, newfile)
    except Exception as e:
        return ip, f"UPLOAD FAILED: {e}"

@app.route("/save", methods=["POST"])
def save():
    token  = request.form["token"]
    names  = json.loads(request.form["names"])
    tmpdir = tempfile.gettempdir()

    with open(f"{tmpdir}/{token}.orig") as f:
        orig = f.read()

    with open(f"{tmpdir}/{token}.ips") as f:
        ips = [l.strip() for l in f if l.strip()]

    newfile = render_config(orig, names)

    results = {}
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(threaded_upload, ip, newfile) for ip in ips]
        for future in concurrent.futures.as_completed(futures):
            ip, result = future.result()
            results[ip] = result

    http_code = 200 if all("FAILED" not in v for v in results.values()) else 207
    return jsonify(results=results), http_code

def check_license():
    """Show license dialog and verify before starting Flask."""
    root = tk.Tk()
    root.withdraw()  # Hide main window
    root.update()  # Process pending events

    license_valid = False

    def on_status_change(status: LicenseStatus):
        nonlocal license_valid
        license_valid = status.ok
        if status.ok:
            root.quit()  # Exit Tkinter loop when valid

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
    parser = argparse.ArgumentParser(description='Cobalt Name Editor')
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
            print("ERROR: Valid license required to run Cobalt Name Editor")
            print("="*60)
            print("\nPlease contact your administrator for a license key.")
            print("\nPress Enter to exit...")
            input()
            exit(1)

        print("\n" + "="*60)
        print("✓ License validated")
        print("="*60)

    # Start server based on mode
    if args.console:
        # Console mode - original behavior
        print(f"\nStarting Cobalt Name Editor on http://{HOST}:{PORT}\n")
        app.run(debug=DEBUG, host=HOST, port=PORT)
    else:
        # GUI mode - run Flask in background thread
        print(f"Starting Cobalt Name Editor on http://{HOST}:{PORT}")

        def run_flask():
            app.run(debug=False, host=HOST, port=PORT, use_reloader=False)

        # Start Flask in daemon thread
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()

        # Create and run GUI
        gui = CobaltGUI(HOST, PORT)
        gui.run()
