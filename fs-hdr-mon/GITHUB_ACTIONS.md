# GitHub Actions - Automated Build System

## Overview

FS-HDR Monitor is configured with **automated CI/CD** using GitHub Actions. Every time you push code to the `main` branch, GitHub automatically builds a Windows executable and creates a new release.

---

## What Happens Automatically

### On Push to Main:

1. **Build Trigger**
   - GitHub Actions detects changes to:
     - `app/` directory
     - `fs-hdr-monitor.spec`
     - `requirements.txt`
     - Workflow file itself

2. **Build Process**
   - Spins up Windows runner (windows-latest)
   - Installs Python 3.12
   - Installs dependencies from `requirements.txt`
   - Runs PyInstaller with `fs-hdr-monitor.spec`
   - Creates `FS-HDR-Monitor.exe`

3. **Release Creation**
   - Creates new GitHub Release
   - Version: `v1.0.<run_number>` (auto-increments)
   - Uploads `FS-HDR-Monitor.exe` as release asset
   - Adds release notes with download instructions

4. **Artifact Storage**
   - Stores .exe as GitHub artifact (90 days)
   - Available for download from Actions tab

---

## Workflow File

**Location:** `../.github/workflows/build-fs-hdr-monitor.yml` (at repository root)

### Triggers

```yaml
on:
  push:
    branches: [ main ]
    paths:
      - 'app/**'
      - 'fs-hdr-monitor.spec'
      - 'requirements.txt'
  pull_request:
    branches: [ main ]
  workflow_dispatch:  # Manual trigger
```

### Key Features

- ✅ **Automatic versioning** - v1.0.X increments with each build
- ✅ **Multi-trigger** - Push, PR, or manual
- ✅ **Artifact upload** - .exe available for 90 days
- ✅ **Release creation** - Only on main branch pushes
- ✅ **Build verification** - Tests .exe exists before upload

---

## Using the Automated Builds

### For Developers (You)

**Normal workflow:**
```bash
# 1. Make changes to code
vim app/fs_mon.py

# 2. Commit and push
git add .
git commit -m "Add new feature"
git push origin main

# 3. GitHub automatically:
#    - Builds FS-HDR-Monitor.exe
#    - Creates release v1.0.X
#    - Uploads .exe to releases
```

**That's it!** No manual building required.

### For End Users

**Download latest version:**
1. Go to: https://github.com/huntson/broadcastengineering/releases
2. Click latest release
3. Download `FS-HDR-Monitor.exe`
4. Run it!

**Direct download link (always latest):**
```
https://github.com/huntson/broadcastengineering/releases/latest/download/FS-HDR-Monitor.exe
```

---

## Manual Trigger

You can manually trigger a build without pushing code:

1. Go to: https://github.com/huntson/broadcastengineering/actions
2. Click "Build FS-HDR Monitor" workflow
3. Click "Run workflow" dropdown
4. Select branch (usually `main`)
5. Click "Run workflow" button

---

## Monitoring Builds

### Check Build Status

**Badge in README:**
```markdown
[![Build FS-HDR Monitor](https://github.com/huntson/broadcastengineering/actions/workflows/build-fs-hdr-monitor.yml/badge.svg)](https://github.com/huntson/broadcastengineering/actions/workflows/build-fs-hdr-monitor.yml)
```

**Actions Tab:**
- https://github.com/huntson/broadcastengineering/actions
- Shows all workflow runs
- Green checkmark = success
- Red X = failed

### Build Artifacts

If a build succeeds but doesn't create a release (e.g., on PR), you can still download the .exe:

1. Go to Actions tab
2. Click on the workflow run
3. Scroll to "Artifacts" section
4. Download `fs-hdr-monitor-windows`

---

## Build Configuration

### PyInstaller Spec File

**Location:** `fs-hdr-monitor.spec`

```python
# Key settings:
- Main script: app/fs_mon.py
- Output name: FS-HDR-Monitor
- Console: True (shows status messages)
- Included data: config-example.json
- Icon: Commented out (add icon.ico if you have one)
```

### Requirements

**Location:** `requirements.txt`

```
Flask>=2.3.0
requests>=2.31.0
pyinstaller>=5.13.0
```

---

## Troubleshooting

### Build Fails

**Check the logs:**
1. Go to Actions tab
2. Click the failed run
3. Expand "Build executable with PyInstaller"
4. Review error messages

**Common issues:**
- Import errors → Add to `hiddenimports` in .spec file
- Missing files → Add to `datas` in .spec file
- Python version mismatch → Update in workflow file

### No Release Created

**Check:**
- Was it pushed to `main` branch? (PRs don't create releases)
- Did the build succeed?
- Check the "Create Release" step in logs

### Wrong Version Number

The version is `v1.0.<github.run_number>`:
- `github.run_number` auto-increments (can't reset easily)
- To use semantic versioning, edit the workflow file

---

## Customization

### Change Version Format

Edit `../.github/workflows/build-fs-hdr-monitor.yml`:

```yaml
# Current:
tag_name: fs-hdr-monitor-v1.0.${{ github.run_number }}

# Semantic versioning:
tag_name: fs-hdr-monitor-v2.0.0  # Manual version

# Date-based:
tag_name: fs-hdr-monitor-v${{ github.run_number }}-$(date +%Y%m%d)
```

### Add Icon

1. Add `icon.ico` to project root
2. Edit `fs-hdr-monitor.spec`:
   ```python
   # Uncomment:
   icon='icon.ico'
   ```

### Change Python Version

Edit `../.github/workflows/build-fs-hdr-monitor.yml`:

```yaml
- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: '3.11'  # Change here
```

---

## Comparison with Manual Builds

| Feature | Manual Build | GitHub Actions |
|---------|-------------|----------------|
| **Build Speed** | 2-5 minutes | 5-7 minutes |
| **Requires local setup** | Yes (Python, PyInstaller) | No |
| **Consistent environment** | No (varies by machine) | Yes (always windows-latest) |
| **Version tracking** | Manual | Automatic |
| **Distribution** | Manual upload | Auto-uploaded to releases |
| **Best for** | Quick testing | Production releases |

---

## Best Practices

1. **Test locally first**
   - Use `build_exe.bat` for quick testing
   - Push to GitHub when ready for release

2. **Use branches**
   - Develop on feature branches
   - Only merge to `main` when ready to release
   - PRs will build but won't create releases

3. **Version management**
   - Major changes? Update version format in workflow
   - Use git tags for important milestones

4. **Monitor builds**
   - Check Actions tab occasionally
   - Fix failures promptly

---

## Costs

**GitHub Actions is FREE for public repositories!**

- Unlimited builds
- Unlimited artifact storage (90 days retention)
- Windows runners included

For private repos: 2,000 minutes/month free (Windows = 2x multiplier)

---

## Next Steps

1. **Push this project to GitHub**
   ```bash
   git add .
   git commit -m "Add GitHub Actions workflow"
   git push origin main
   ```

2. **Watch the first build**
   - Go to Actions tab
   - See it build automatically
   - Download from Releases when done

3. **Share the download link**
   - Give users: https://github.com/huntson/broadcastengineering/releases/latest

---

**Questions?** See the [GitHub Actions Documentation](https://docs.github.com/en/actions) or check the workflow logs for details.
