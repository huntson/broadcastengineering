# Cobalt Name Editor - Windows Executable

This folder contains the standalone Windows executable for Cobalt Name Editor.

## Quick Start

1. **Double-click** `cobalt-name-editor.exe` to run
2. A console window will open showing the Flask server
3. **Open your browser** to `http://localhost:5050`
4. Start managing your Cobalt device names

## What's Inside

- `cobalt-name-editor.exe` - Standalone Windows application (no installation required)

## System Requirements

- **OS**: Windows 10 or newer (64-bit)
- **No dependencies** - Everything is bundled in the .exe

## First Run

When you first run the application, Windows Defender or your antivirus may show a warning because this is an unsigned executable. This is normal for standalone Python applications. You can safely click "More info" → "Run anyway".

Windows Firewall may also prompt you to allow network access. Click **Allow** so the application can communicate with your Cobalt devices.

## How to Use

### Step 1: Download Device Configurations
- Enter device IP addresses (comma-separated)
- Click **Download** to fetch configurations

### Step 2: Edit Names
- Modify device names in the table
- Use **Default Names** button for standardized naming

### Step 3: Upload Changes
- Click **Upload** to push changes to all devices
- Review the upload log for success/failure status

## Troubleshooting

**Application won't start?**
- Check if port 5050 is in use
- Try running as Administrator

**Can't reach devices?**
- Verify device IP addresses
- Check network connectivity with `ping <device-ip>`
- Ensure Windows Firewall allows the application

**Web interface doesn't load?**
- Manually navigate to `http://localhost:5050`
- Check the console window for errors

## Getting Updates

Download the latest version from the [Releases page](https://github.com/huntson/broadcastengineering/releases).

To download using the helper script:
```bash
cd cobalt-name-editor
./download-latest.sh
```

## Support

For issues or questions, [open an issue on GitHub](https://github.com/huntson/broadcastengineering/issues).
