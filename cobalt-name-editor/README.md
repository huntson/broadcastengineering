# Cobalt Name Editor - Windows Standalone

A web-based tool for managing device names on Cobalt hardware units. This is a standalone Windows executable - no installation or dependencies required.

## Download

Download the latest `cobalt-name-editor.exe` from the [Releases page](https://github.com/huntson/broadcastengineering/releases).

## Quick Start

1. **Download** `cobalt-name-editor.exe` from Releases
2. **Double-click** the executable to run
3. **Open your browser** to `http://localhost:5050`
4. **Start editing** your Cobalt device names

That's it! No installation, no Docker, no Python needed.

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

### Running the Application
- The executable opens a console window showing the Flask server logs
- **Keep this console window open** while using the application
- The web interface runs at `http://localhost:5050`
- Close the console window to stop the server

### Port Configuration
- Default port: **5050**
- If port 5050 is in use, edit `main.py` and change the port number in the last line:
  ```python
  app.run(debug=True, host="0.0.0.0", port=5050)  # Change 5050 to another port
  ```
- Then rebuild with PyInstaller (see Developer section)

### Firewall & Network Access
- Windows Firewall may prompt you to allow the application
- Click **Allow access** to enable communication with Cobalt devices
- Ensure devices are on the same network or accessible via routing

### Accessing Devices
- Test device connectivity: `ping <device-ip>` from Command Prompt
- Verify devices are powered on and network-accessible
- Check that device IPs are correct

## Troubleshooting

### Application won't start
- Check if port 5050 is already in use
- Run as Administrator if you encounter permission errors
- Check Windows Event Viewer for error details

### Can't reach devices
- Verify device IP addresses are correct
- Check Windows Firewall settings
- Ensure devices are on the same network

### Web interface doesn't open
- Manually navigate to `http://localhost:5050` in your browser
- Try `http://127.0.0.1:5050` if localhost doesn't work
- Check the console window for error messages

## For Developers

### Building from Source

1. **Install Python 3.12+**
2. **Clone the repository**:
   ```bash
   git clone https://github.com/huntson/broadcastengineering
   cd broadcastengineering/cobalt-name-editor
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Build the executable**:
   ```bash
   pyinstaller cobalt-name-editor.spec
   ```

5. **Find the executable**:
   ```
   dist/cobalt-name-editor.exe
   ```

### Running in Development Mode
```bash
python main.py
```
Then open `http://localhost:5000`

## Architecture

- **Backend**: Flask (Python 3.12)
- **Frontend**: Bootstrap 5 with vanilla JavaScript
- **Packaging**: PyInstaller for standalone Windows executable
- **Auto-builds**: GitHub Actions creates releases automatically

## Support

For issues or feature requests, please [open an issue](https://github.com/huntson/broadcastengineering/issues).
