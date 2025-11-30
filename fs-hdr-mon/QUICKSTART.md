# Quick Start Guide

## For Users (Running the .EXE)

### First Time Setup

1. **Get the files:**
   - `FS-HDR-Monitor.exe`
   - `config-example.json`

2. **Create your config:**
   - Copy `config-example.json` to `config.json`
   - Edit `config.json` with your FS unit IP addresses

3. **Run it:**
   - Double-click `FS-HDR-Monitor.exe`
   - Wait for console message: "Starting FS-HDR Monitor on 0.0.0.0:5000"

4. **Access dashboard:**
   - Open browser to: `http://localhost:5000`

### Configuration Tips

**Minimal config.json:**
```json
{
  "settings": {
    "host": "0.0.0.0",
    "port": 5000,
    "poll_interval": 1
  },
  "fs_units": [
    {"ip": "192.168.1.100", "model": "FS4/HDR"}
  ],
  "presets": {
    "1": {"name": "Preset 1", "fs_value": 1},
    "2": {"name": "Preset 2", "fs_value": 2},
    "3": {"name": "Preset 3", "fs_value": 3},
    "4": {"name": "Preset 4", "fs_value": 4}
  }
}
```

**Change port:**
- Edit `"port": 5000` to another value (e.g., 8080)
- Access at: `http://localhost:8080`

**Local only (secure):**
- Change `"host": "0.0.0.0"` to `"host": "127.0.0.1"`
- Only accessible from local machine

---

## For Developers (Building the .EXE)

### Prerequisites
- Python 3.7+
- Git

### Build Steps

1. **Clone/Get source:**
   ```bash
   cd fs-hdr-mon
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install pyinstaller
   ```

3. **Build the .exe:**

   **Windows:**
   ```cmd
   build_exe.bat
   ```

   **Mac/Linux:**
   ```bash
   ./build_exe.sh
   ```

   **Or manually:**
   ```bash
   cd app
   pyinstaller --onefile --windowed --name "FS-HDR-Monitor" fs_mon.py
   ```

4. **Locate .exe:**
   - Windows: `app\dist\FS-HDR-Monitor.exe`
   - Mac/Linux: `app/dist/FS-HDR-Monitor`

5. **Deploy:**
   - Copy .exe to target location
   - Copy `app/config-example.json` alongside it
   - User creates `config.json` from example

### Testing Before Building

```bash
cd app
python fs_mon.py
```

Open browser to: `http://localhost:5000`

---

## Troubleshooting

**Port already in use:**
- Change port in `config.json`
- Restart the application

**Can't connect from another PC:**
- Check `"host"` is `"0.0.0.0"` (not `"127.0.0.1"`)
- Check Windows Firewall allows the port

**FS units not showing:**
- Verify IP addresses in `config.json`
- Ping the FS units to verify network connectivity
- Check FS units have HTTP API enabled

**Application crashes on startup:**
- Check `config.json` syntax (use JSON validator)
- Check application has write permission to its folder
- Check Python version (3.7+ required for building)

---

## Next Steps

- See [README.md](README.md) for full documentation
- See [CONFIG_README.md](CONFIG_README.md) for configuration details
