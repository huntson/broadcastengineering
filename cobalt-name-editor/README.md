# Cobalt Name Editor - Windows Version

A web-based tool for managing device names on Cobalt hardware units. This version is configured to run on Windows using Docker Desktop.

## Prerequisites

- **Docker Desktop for Windows** (with WSL2 backend recommended)
  - Download from: https://www.docker.com/products/docker-desktop/
  - Ensure Docker Desktop is running before proceeding

## Installation & Setup

1. **Clone this repository** (if not already done):
   ```bash
   git clone https://github.com/huntson/broadcastengineering
   cd broadcastengineering/cobalt-name-editor
   ```

2. **Build and start the container**:
   ```bash
   docker-compose up -d --build
   ```

3. **Access the web interface**:
   - Open your browser and navigate to: `http://localhost:5050`

## Usage

### Step 1: Download Config
1. Enter one or more device IP addresses (comma-separated)
   - Example: `10.96.50.166, 10.96.50.167`
2. Click **Download** to fetch the current configuration from your Cobalt devices

### Step 2: Edit Names
- Edit device names directly in the table
- Click **Default Names** to auto-generate standardized names (CCFS 01, CCFS 02, etc.)
- **Optional**: Sync with Google Sheets (feature requires additional setup)

### Step 3: Upload
1. Click **Upload** to push the updated configuration back to your devices
2. View upload results for each device in the log

## Windows-Specific Notes

### Port Configuration
- The service runs on port **5050** (mapped from container port 5000)
- If port 5050 is already in use, edit `docker-compose.yml` and change:
  ```yaml
  ports:
    - "5050:5000"  # Change 5050 to another available port
  ```

### Accessing Devices on Your Network
- Ensure your Windows firewall allows Docker to communicate with devices on your local network
- If using WSL2, Docker Desktop handles network bridging automatically
- Test connectivity: `ping <device-ip>` from PowerShell/CMD

### File Paths
- Windows paths work seamlessly with Docker Desktop
- Temporary files are stored in the container's temp directory

## Management Commands

### View logs:
```bash
docker-compose logs -f
```

### Stop the service:
```bash
docker-compose down
```

### Restart the service:
```bash
docker-compose restart
```

### Rebuild after code changes:
```bash
docker-compose up -d --build
```

## Troubleshooting

### Container won't start
- Ensure Docker Desktop is running
- Check if port 5050 is available: `netstat -ano | findstr :5050`

### Can't reach devices
- Verify device IP addresses are correct
- Check Windows Firewall settings
- Ensure devices are on the same network or accessible via routing

### Permission errors
- Run PowerShell/CMD as Administrator if needed
- Check Docker Desktop's WSL integration settings

## Architecture

- **Backend**: Flask (Python 3.12)
- **Frontend**: Bootstrap 5 with vanilla JavaScript
- **Container**: Docker with Linux base image (runs via WSL2 on Windows)

## Support

For issues specific to this Windows deployment, check:
1. Docker Desktop logs
2. Container logs: `docker-compose logs`
3. Windows Event Viewer for system-level errors
