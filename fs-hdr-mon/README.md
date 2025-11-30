# FS-HDR Monitor

Web-based monitoring and control dashboard for AJA FS-HDR, FS4, and FS2 framestore units.

[![Build FS-HDR Monitor](https://github.com/huntson/broadcastengineering/actions/workflows/build-fs-hdr-monitor.yml/badge.svg)](https://github.com/huntson/broadcastengineering/actions/workflows/build-fs-hdr-monitor.yml)

## Download

**Latest Release:** [Download FS-HDR-Monitor.exe](https://github.com/huntson/broadcastengineering/releases/latest)

Pre-built Windows executable available - no Python installation required!

## Features

- **Real-time Monitoring**: Live status updates for all video paths
- **Multi-Unit Support**: Monitor multiple FS units simultaneously (FS-HDR, FS4, FS2)
- **Format Control**: Change output formats via dropdown menus
- **Audio/Frame Delay**: Right-click channels to adjust audio delay and frame delay
- **Preset Recall**: Save and recall presets across multiple units
- **Error Detection**: Automatic highlighting of input/output mismatches and errors
- **Two Views**: Full dashboard and compact view

## Quick Start (Running from Source)

### Prerequisites
- Python 3.7 or higher
- Network access to AJA FS units

### Installation

1. **Install Python dependencies:**
   ```bash
   cd fs-hdr-mon
   pip install -r requirements.txt
   ```

2. **Configure your FS units:**
   - Edit `app/config.json` (or copy from `app/config-example.json`)
   - Add your FS unit IP addresses and models
   - See [CONFIG_README.md](CONFIG_README.md) for details

3. **Run the application:**
   ```bash
   cd app
   python fs_mon.py
   ```

4. **Access the web interface:**
   - Open browser to: `http://localhost:5000`
   - From another PC: `http://<server-ip>:5000`

## Building Standalone .EXE

### Automated Builds (GitHub Actions)

**Every push to main automatically builds and releases a new .exe!**

When you push code to GitHub:
1. GitHub Actions automatically builds `FS-HDR-Monitor.exe`
2. Creates a new release (v1.0.X)
3. Uploads the .exe to GitHub Releases
4. Users can download from [Releases page](https://github.com/huntson/broadcastengineering/releases)

No manual building required - just push your code!

### Manual Build (Local)

If you want to build locally instead of using GitHub Actions:

#### Using PyInstaller (Recommended)

1. **Install PyInstaller:**
   ```bash
   pip install pyinstaller
   ```

2. **Build the executable:**
   ```bash
   cd fs-hdr-mon
   pyinstaller fs-hdr-monitor.spec
   ```

   **Or use the automated build script:**
   ```bash
   # Windows
   build_exe.bat

   # Mac/Linux
   ./build_exe.sh
   ```

3. **Locate the .exe:**
   - The executable will be in: `dist/FS-HDR-Monitor.exe`

4. **Deploy:**
   - Copy `FS-HDR-Monitor.exe` to your target machine
   - Create `config.json` in the same directory as the .exe
   - Run `FS-HDR-Monitor.exe`

### PyInstaller Options Explained

- `--onefile` - Single executable file (no external dependencies)
- `--windowed` - No console window (clean GUI experience)
- `--name` - Name of the output executable
- `--icon` - (Optional) Custom icon for the .exe

### Advanced Build: Hidden Console, Custom Options

```bash
pyinstaller --onefile ^
            --windowed ^
            --name "FS-HDR-Monitor" ^
            --add-data "config-example.json;." ^
            --noconsole ^
            fs_mon.py
```

## Deployment

### Folder Structure After Building

```
deployment/
├── FS-HDR-Monitor.exe
├── config.json           (create this - see config-example.json)
└── config-example.json   (optional - for reference)
```

### First-Time Setup on Target Machine

1. Copy `FS-HDR-Monitor.exe` to desired location
2. Create `config.json` in the same folder (use `config-example.json` as template)
3. Edit `config.json` with your FS unit IP addresses
4. Double-click `FS-HDR-Monitor.exe` to start
5. Open browser to `http://localhost:5000`

### Running as a Windows Service (Optional)

For production environments, you can run the .exe as a Windows service using tools like:
- **NSSM** (Non-Sucking Service Manager) - https://nssm.cc/
- **Windows Task Scheduler** - Set to run at startup

**Example with NSSM:**
```cmd
nssm install "FS-HDR Monitor" "C:\path\to\FS-HDR-Monitor.exe"
nssm start "FS-HDR Monitor"
```

## Configuration

See [CONFIG_README.md](CONFIG_README.md) for detailed configuration documentation.

### Quick Config Example

```json
{
  "settings": {
    "host": "0.0.0.0",
    "port": 5000,
    "poll_interval": 1
  },
  "fs_units": [
    {"ip": "192.168.1.100", "model": "FS4/HDR"},
    {"ip": "192.168.1.101", "model": "FS2"}
  ],
  "presets": {
    "1": {"name": "Game Feed", "fs_value": 1},
    "2": {"name": "Network Feed", "fs_value": 2},
    "3": {"name": "Backup", "fs_value": 3},
    "4": {"name": "Test", "fs_value": 4}
  }
}
```

## Usage

### Main Dashboard
- **View Status**: Real-time display of all video paths
- **Change Format**: Click dropdown on any path to select output format
- **Adjust Delays**: Right-click any channel to open audio/frame delay controls
- **Recall Presets**: Click preset buttons to recall saved configurations

### Compact View
- Access at: `http://localhost:5000/compact`
- Simplified bullet-point status view
- Useful for monitoring at-a-glance

### Adding/Removing Units
- Edit `config.json` while app is running
- Restart the application to load changes
- Or use the web UI import/export feature (if available)

## Troubleshooting

### Application Won't Start
- **Check port availability**: Port 5000 might be in use
  - Change `port` in `config.json` to another value (e.g., 5001)
- **Check config.json syntax**: Must be valid JSON
  - Use a JSON validator online or in your editor
- **Firewall**: Ensure Python/exe is allowed through Windows Firewall

### Can't Access from Another PC
- **Host setting**: Change `"host": "127.0.0.1"` to `"host": "0.0.0.0"` in config.json
- **Firewall**: Allow the port (5000) through Windows Firewall
- **Network**: Ensure both PCs are on same network/VLAN

### FS Units Not Responding
- **Network connectivity**: Verify you can ping the FS unit IP addresses
- **Credentials**: Ensure no authentication is required on the FS units
- **API enabled**: Verify the FS units have HTTP API enabled

### Browser Shows "Connection Refused"
- **Application running**: Verify the .exe is actually running
  - Check Task Manager for "FS-HDR-Monitor.exe"
- **Correct URL**: Ensure using `http://` not `https://`
- **Port number**: Verify you're using the correct port from config.json

## Development

### Project Structure
```
fs-hdr-mon/
├── app/
│   ├── fs_mon.py              # Main application
│   ├── config.json            # Configuration
│   └── config-example.json    # Template
├── CONFIG_README.md           # Configuration guide
├── README.md                  # This file
└── requirements.txt           # Python dependencies
```

### Making Changes
1. Edit `app/fs_mon.py`
2. Test with: `python fs_mon.py`
3. Rebuild exe when ready: `pyinstaller --onefile --windowed --name "FS-HDR-Monitor" fs_mon.py`

## Supported AJA Models

- **FS-HDR** - 4 channel HDR framestore
- **FS4** - 4 channel framestore
- **FS2** - 2 channel framestore

## Requirements

- **Python** (for source): 3.7+
- **Dependencies**: Flask, requests
- **Network**: Access to FS units via HTTP
- **Browser**: Modern web browser (Chrome, Firefox, Edge)

## License

Internal use / Proprietary

## Support

For issues or questions, contact the development team.

---

**Version**: 2.0
**Last Updated**: 2025-01-19
**Platform**: Windows (cross-platform compatible via Python)
