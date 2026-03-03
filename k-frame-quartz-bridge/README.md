# K-Frame Quartz Control

Bridge application that integrates Grass Valley K-Frame systems with Quartz Designer automation.

[![Build K-Frame Quartz Bridge](https://github.com/huntson/broadcastengineering/actions/workflows/build-k-frame-quartz-bridge.yml/badge.svg)](https://github.com/huntson/broadcastengineering/actions/workflows/build-k-frame-quartz-bridge.yml)

## Download

**Latest Release:** [Download k-frame-quartz-bridge.exe](https://github.com/huntson/broadcastengineering/releases/download/k-frame-quartz-bridge-latest/k-frame-quartz-bridge.exe)

Direct download link (always latest):
```
https://github.com/huntson/broadcastengineering/releases/download/k-frame-quartz-bridge-latest/k-frame-quartz-bridge.exe
```

Or browse all releases: https://github.com/huntson/broadcastengineering/releases?q=k-frame-quartz-bridge&expanded=true

Pre-built Windows executable available - no Python installation required!

## Features

- **Real-time K-Frame Monitoring**: Live status display of K-Frame panel data
- **Quartz Designer Integration**: Automatic synchronization of resources with Quartz Designer
- **Web Status UI**: Access comprehensive status at `http://localhost:4001`
- **Cascade Tally Highlighting**: Visual indicators for active cascaded sources
- **Data Completeness Tracking**: Monitor connection health and data validity
- **Yellow Flash Alerts**: Content change highlighting for immediate visibility

## Quick Start

1. **Download** `k-frame-quartz-bridge.exe` from Releases
2. **Configure** `config.ini` with your GV host and suite information
3. **Run** the executable
4. **Access** the web UI at `http://localhost:4001`

## Configuration

Create a `config.ini` file in the same directory as the executable:

```ini
[GV]
host = your-kframe-host
suite = 1

[Quartz]
host = your-quartz-host
port = 32400
```

See `config.ini.example` for a complete configuration template.

## Usage

### Web Interface
- Navigate to `http://localhost:4001` after starting the application
- View real-time K-Frame status and tally information
- Monitor cascade tally highlighting
- Track data completeness and connection health

### Running from Source

If you prefer to run from source instead of using the pre-built executable:

```bash
cd k-frame-quartz-bridge
pip install -r requirements.txt
python main.py
```

## Building from Source

The application is automatically built by GitHub Actions on every push to main. To build manually:

```bash
cd k-frame-quartz-bridge
pip install pyinstaller
pyinstaller k-frame-quartz-bridge.spec
```

The executable will be in `dist/k-frame-quartz-bridge.exe`

## Troubleshooting

### Application Won't Start
- Verify `config.ini` exists and has valid GV host/suite settings
- Check that port 4001 is not in use
- Ensure network connectivity to K-Frame and Quartz hosts

### Can't Access Web UI
- Verify application is running
- Navigate to `http://localhost:4001` in your browser
- Check console output for any error messages

### No Data Showing
- Confirm K-Frame host and suite are correct in config.ini
- Verify network connectivity to the K-Frame system
- Check Quartz Designer host and port settings

## License

**K-Frame Quartz Control** - Licensed software

This application requires a valid license key to operate. On first run, you will be prompted to enter your license information.

For licensing information, contact the development team.

## Support

For issues or questions, contact the development team.

---

**Platform**: Windows
**Status UI Port**: 4001
