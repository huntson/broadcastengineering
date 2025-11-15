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

@app.route('/sync', methods=['POST'])
def sync():
    token     = request.form.get('token')
    sheet_url = request.form.get('sheet_url')

    if not token:
        return jsonify(error="Missing token"), 400

    tmpdir = tempfile.gettempdir()
    orig_path = f"{tmpdir}/{token}.orig"

    if not os.path.exists(orig_path):
        return jsonify(error="Invalid or expired token"), 400

    original = open(orig_path).read()

    # TODO: Replace this with actual sheet parsing logic
    names = []  # e.g. names = pull_names(sheet_url)

    new_config = render_config(original, names)
    with open(orig_path, "w") as f:
        f.write(new_config)

    return jsonify(names=names)

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
    orig   = open(f"{tmpdir}/{token}.orig").read()
    ips    = [l.strip() for l in open(f"{tmpdir}/{token}.ips") if l.strip()]
    newfile = render_config(orig, names)

    results = {}
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(threaded_upload, ip, newfile) for ip in ips]
        for future in concurrent.futures.as_completed(futures):
            ip, result = future.result()
            results[ip] = result

    http_code = 200 if all("FAILED" not in v for v in results.values()) else 207
    return jsonify(results=results), http_code

if __name__ == '__main__':
    app.run(debug=DEBUG, host=HOST, port=PORT)
