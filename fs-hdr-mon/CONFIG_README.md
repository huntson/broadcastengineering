# Configuration Guide

## config.json Structure

The application uses a single `config.json` file located in the `app/` directory to store all configuration, FS units, and presets.

### File Location
```
fs-hdr-mon/app/config.json
```

### Configuration Structure

```json
{
  "settings": {
    "host": "0.0.0.0",
    "port": 5070,
    "poll_interval": 1
  },
  "fs_units": [
    {
      "ip": "192.168.1.100",
      "model": "FS4/HDR"
    }
  ],
  "presets": {
    "1": {
      "name": "Preset 1",
      "fs_value": 1
    }
  }
}
```

## Settings Section

### `settings`
Application-level configuration.

**Parameters:**
- `host` (string): IP address to bind the web server to
  - `"0.0.0.0"` - Listen on all network interfaces (accessible from other devices)
  - `"127.0.0.1"` - Listen only on localhost (local access only)
  - Default: `"0.0.0.0"`

- `port` (number): TCP port for the web interface
  - Default: `5070`
  - Note: You'll be prompted to confirm or change this port when the application starts
  - Access the app at: `http://<host>:<port>`

- `poll_interval` (number): Seconds between polling FS units for status updates
  - Default: `1`
  - Range: `0.5` to `10` (recommended)

## FS Units Section

### `fs_units`
Array of AJA FS framestore units to monitor.

**Format:**
```json
{
  "ip": "192.168.1.100",
  "model": "FS4/HDR"
}
```

**Parameters:**
- `ip` (string): IP address of the FS unit
- `model` (string): Model type
  - `"FS4/HDR"` - FS4 or FS-HDR (4 channels)
  - `"FS2"` - FS2 (2 channels)

**Example:**
```json
"fs_units": [
  {"ip": "192.168.1.100", "model": "FS4/HDR"},
  {"ip": "192.168.1.101", "model": "FS2"},
  {"ip": "10.96.50.10", "model": "FS4/HDR"}
]
```

## Presets Section

### `presets`
Preset configurations for recalling saved settings on FS units.

**Format:**
```json
"1": {
  "name": "Preset 1",
  "fs_value": 1
}
```

**Parameters:**
- `name` (string): Display name for the preset
- `fs_value` (number): Register number to recall on FS units (1-4)

**Example:**
```json
"presets": {
  "1": {"name": "Game 1080p59", "fs_value": 1},
  "2": {"name": "Show 720p59", "fs_value": 2},
  "3": {"name": "Network Feed", "fs_value": 3},
  "4": {"name": "Backup Config", "fs_value": 4}
}
```

## First Time Setup

1. Copy `config-example.json` to `config.json`
2. Edit `config.json` and add your FS unit IP addresses
3. Customize presets if needed
4. Start the application

## Notes

- The application will automatically create a default `config.json` if none exists
- Changes made via the web UI are saved automatically to `config.json`
- You can edit `config.json` while the app is running, but restart to apply settings changes
- Backup `config.json` before making manual edits
