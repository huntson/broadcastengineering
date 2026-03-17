/* AJA FS Emulator Control Panel — Frontend JS */

let logVisible = false;
let currentState = 'stopped';
let inputCount = 8;  // updated from status API

// --- Status Polling ---

function pollStatus() {
    fetch('/api/status')
        .then(r => r.json())
        .then(data => {
            currentState = data.state;
            updateStatusUI(data);
            const interval = (data.state === 'running' || data.state === 'starting') ? 2000 : 5000;
            setTimeout(pollStatus, interval);
        })
        .catch(() => setTimeout(pollStatus, 5000));
}

function updateStatusUI(data) {
    // Badge
    const badge = document.getElementById('status-badge');
    badge.className = 'badge ' + data.state;
    badge.textContent = data.state.charAt(0).toUpperCase() + data.state.slice(1);

    // Info
    document.getElementById('state-text').textContent = data.state;
    document.getElementById('firmware-text').textContent = data.firmware || 'None';

    if (data.uptime != null) {
        const m = Math.floor(data.uptime / 60);
        const s = data.uptime % 60;
        document.getElementById('uptime-text').textContent = m + 'm ' + s + 's';
    } else {
        document.getElementById('uptime-text').textContent = '-';
    }

    // Device type
    const deviceText = document.getElementById('device-type-text');
    if (deviceText) {
        deviceText.textContent = data.device_name || '-';
    }

    // Track input channel count for SDI controls
    if (data.input_count) {
        inputCount = data.input_count;
    }

    // Device web UI link — hide when no firmware loaded
    const linkWrapper = document.getElementById('device-link-wrapper');
    const link = document.getElementById('device-link');
    if (linkWrapper) {
        linkWrapper.style.display = data.device_name ? '' : 'none';
    }
    if (link && data.device_name) {
        link.href = data.device_url;
        link.textContent = 'Open ' + data.device_name + ' Web UI (:' + data.web_port + ')';
    }

    // Buttons
    const isRunning = data.state === 'running' || data.state === 'starting';
    document.getElementById('btn-start').disabled = isRunning;
    document.getElementById('btn-stop').disabled = !isRunning;
    document.getElementById('btn-restart').disabled = !isRunning;

    // Flash save button — only enabled when running
    const saveBtn = document.getElementById('btn-flash-save');
    if (saveBtn) {
        saveBtn.disabled = data.state !== 'running';
    }

    // Update reference panel from live device state
    updateRefStatus();

    // Auto-update log if visible
    if (logVisible && data.log_lines > 0) {
        fetchLog();
    }
}

// --- Firmware ---

document.getElementById('upload-form').addEventListener('submit', function(e) {
    e.preventDefault();
    const fileInput = document.getElementById('firmware-file');
    if (!fileInput.files.length) return;

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    const status = document.getElementById('upload-status');
    status.textContent = 'Processing firmware... (may take a few seconds)';
    status.className = '';

    fetch('/api/firmware/upload', { method: 'POST', body: formData })
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                status.textContent = 'Error: ' + data.error;
                status.className = 'error-text';
            } else {
                const deviceInfo = data.device_type ? ' (' + data.device_type + ')' : '';
                status.textContent = 'Firmware processed: ' + data.firmware + deviceInfo;
                status.className = 'success';
                loadFirmwareList();
                // Auto-start emulator if it's not already running
                if (currentState === 'stopped' || currentState === 'error') {
                    startEmulator();
                }
            }
        })
        .catch(err => {
            status.textContent = 'Upload failed: ' + err;
            status.className = 'error-text';
        });
});

function loadFirmwareList() {
    fetch('/api/firmware/list')
        .then(r => r.json())
        .then(data => {
            const list = document.getElementById('firmware-list');
            if (!data.firmware.length) {
                list.innerHTML = '<div style="color:#666;font-size:13px">No firmware uploaded yet</div>';
                return;
            }
            list.innerHTML = data.firmware.map(fw => {
                const selected = fw.name === data.selected;
                return '<div class="fw-item' + (selected ? ' selected' : '') + '">' +
                    '<span>' + fw.name + ' (' + fw.size_mb + ' MB)</span>' +
                    (selected ? ' <span>[active]</span>' : ' <button class="btn btn-small" onclick="selectFirmware(\'' + fw.name + '\')">Select</button>') +
                    ' <button class="btn btn-small btn-red" onclick="deleteFirmware(\'' + fw.name + '\')">Delete</button>' +
                    '</div>';
            }).join('');
        });
}

function deleteFirmware(name) {
    if (!confirm('Delete ' + name + '?')) return;
    fetch('/api/firmware/delete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: name})
    })
    .then(r => r.json())
    .then(data => {
        if (data.error) {
            alert('Error: ' + data.error);
        } else {
            loadFirmwareList();
        }
    });
}

function selectFirmware(name) {
    fetch('/api/firmware/select', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: name})
    })
    .then(r => r.json())
    .then(data => {
        if (data.error) {
            alert('Error: ' + data.error);
        } else {
            loadFirmwareList();
        }
    });
}

// --- Emulator Controls ---

function startEmulator() {
    const webPort = parseInt(document.getElementById('web-port').value);

    fetch('/api/emulator/start', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({web_port: webPort})
    })
    .then(r => r.json())
    .then(data => {
        if (data.error) alert('Error: ' + data.error);
    });
}

function stopEmulator() {
    fetch('/api/emulator/stop', { method: 'POST' })
        .then(r => r.json());
}

function restartEmulator() {
    const webPort = parseInt(document.getElementById('web-port').value);

    fetch('/api/emulator/restart', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({web_port: webPort})
    })
    .then(r => r.json())
    .then(data => {
        if (data.error) alert('Error: ' + data.error);
    });
}

function saveConfig() {
    const webPort = parseInt(document.getElementById('web-port').value);

    fetch('/api/config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({web_port: webPort})
    })
    .then(r => r.json())
    .then(data => {
        if (data.error) {
            alert('Error: ' + data.error);
        }
    });
}

// --- SDI Controls ---

function setAllSdi() {
    const val = document.getElementById('sdi-all').value;
    if (!val) return;

    // Set all dropdowns to the same value
    for (let i = 1; i <= inputCount; i++) {
        const el = document.getElementById('sdi-' + i);
        if (el) el.value = val;
    }

    if (currentState !== 'running') {
        document.getElementById('sdi-status').textContent = 'Emulator not running';
        document.getElementById('sdi-status').className = 'error-text';
        return;
    }

    const status = document.getElementById('sdi-status');
    status.textContent = 'Applying...';
    status.className = '';

    fetch('/api/sdi/set', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({all: parseInt(val)})
    })
    .then(r => r.json())
    .then(data => {
        if (data.error) {
            status.textContent = 'Error: ' + data.error;
            status.className = 'error-text';
        } else {
            status.textContent = 'Applied';
            status.className = 'success';
        }
    })
    .catch(err => {
        status.textContent = 'Failed: ' + err;
        status.className = 'error-text';
    });
}

function applySdi() {
    if (currentState !== 'running') {
        document.getElementById('sdi-status').textContent = 'Emulator not running';
        document.getElementById('sdi-status').className = 'error-text';
        return;
    }

    const channels = {};
    for (let i = 1; i <= inputCount; i++) {
        const el = document.getElementById('sdi-' + i);
        if (el) channels[i] = parseInt(el.value);
    }

    const status = document.getElementById('sdi-status');
    status.textContent = 'Applying...';
    status.className = '';

    fetch('/api/sdi/set', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({channels: channels})
    })
    .then(r => r.json())
    .then(data => {
        if (data.error) {
            status.textContent = 'Error: ' + data.error;
            status.className = 'error-text';
        } else {
            status.textContent = 'Applied';
            status.className = 'success';
        }
    })
    .catch(err => {
        status.textContent = 'Failed: ' + err;
        status.className = 'error-text';
    });
}

// --- Reference Controls ---

function updateRefStatus() {
    if (currentState !== 'running') {
        document.getElementById('ref-source-text').textContent = '-';
        document.getElementById('ref-bnc-controls').style.display = 'none';
        document.getElementById('ref-no-bnc-msg').style.display = 'none';
        return;
    }
    fetch('/api/reference/status')
        .then(r => r.json())
        .then(data => {
            document.getElementById('ref-source-text').textContent =
                data.source_name || '-';
            document.getElementById('ref-bnc-controls').style.display =
                data.is_bnc ? '' : 'none';
            document.getElementById('ref-no-bnc-msg').style.display =
                data.is_bnc ? 'none' : '';
        })
        .catch(() => {});
}

function applyRef() {
    if (currentState !== 'running') return;

    const format = parseInt(document.getElementById('ref-format').value);
    const status = document.getElementById('ref-status');
    status.textContent = 'Applying...';
    status.className = '';

    fetch('/api/reference/set', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({format: format})
    })
    .then(r => r.json())
    .then(data => {
        if (data.error) {
            status.textContent = 'Error: ' + data.error;
            status.className = 'error-text';
        } else {
            status.textContent = 'Applied';
            status.className = 'success';
        }
    })
    .catch(err => {
        status.textContent = 'Failed: ' + err;
        status.className = 'error-text';
    });
}

// --- Boot Log ---

function toggleLog() {
    const el = document.getElementById('boot-log');
    logVisible = !logVisible;
    el.style.display = logVisible ? 'block' : 'none';
    if (logVisible) fetchLog();
}

function fetchLog() {
    fetch('/api/log?last=200')
        .then(r => r.json())
        .then(data => {
            const el = document.getElementById('boot-log');
            el.textContent = data.lines.join('\n');
            el.scrollTop = el.scrollHeight;
        });
}

// --- Flash Persistence ---

function loadFlashStatus() {
    fetch('/api/flash/status')
        .then(r => r.json())
        .then(data => {
            const el = document.getElementById('flash-status-text');
            if (data.saved) {
                const mb = (data.total_size / 1024 / 1024).toFixed(1);
                el.textContent = 'Saved (' + mb + ' MB)';
                el.className = 'success';
            } else {
                el.textContent = 'No saved state (factory defaults on boot)';
                el.className = '';
            }
        })
        .catch(() => {
            const el = document.getElementById('flash-status-text');
            el.textContent = 'Unable to check';
            el.className = 'error-text';
        });
}

function saveFlash() {
    if (currentState !== 'running') return;

    const status = document.getElementById('flash-action-status');
    const btn = document.getElementById('btn-flash-save');
    status.textContent = 'Saving flash images...';
    status.className = '';
    btn.disabled = true;

    fetch('/api/flash/save', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                status.textContent = 'Error: ' + data.error;
                status.className = 'error-text';
            } else {
                status.textContent = data.message;
                status.className = 'success';
                loadFlashStatus();
            }
            btn.disabled = currentState !== 'running';
        })
        .catch(err => {
            status.textContent = 'Failed: ' + err;
            status.className = 'error-text';
            btn.disabled = currentState !== 'running';
        });
}

function resetFlash() {
    if (!confirm('Delete saved configuration? Next boot will start with factory defaults.')) {
        return;
    }

    const status = document.getElementById('flash-action-status');
    fetch('/api/flash/reset', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            status.textContent = data.message;
            status.className = 'success';
            loadFlashStatus();
        })
        .catch(err => {
            status.textContent = 'Failed: ' + err;
            status.className = 'error-text';
        });
}

// --- Init ---

document.addEventListener('DOMContentLoaded', function() {
    loadFirmwareList();
    loadFlashStatus();
    pollStatus();
});
