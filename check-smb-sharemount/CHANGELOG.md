# Changelog — check-smb-sharemount

All notable changes to the Check-SmbShareMount SMB share-mount diagnostic.
Versions follow [semver](https://semver.org); see `../VERSIONING.md`.

## 0.1.0 — 2026-09-20

Initial tracked release.

### Added
- `Check-SmbShareMount.ps1` — plain-language "why can't this PC open that shared folder?"
  diagnostic for Windows 7-11. Built-in Windows commands only (no packet crafting), so
  endpoint security (CrowdStrike / Defender / Bitdefender) does not flag it.
- Diagnoses name resolution, SMB ports, SMB1/SMB2 client dialect mismatch, credentials,
  guest policy, share existence and access; one plain-language verdict plus the exact fix.
- Apply-fix: re-enables the SMB2/3 client or allows guest shares. Self-elevates through UAC
  when not already administrator (pattern matches evs-xfile-xsquare); PowerShell 2.0-safe
  script-path fallback for Windows 7; `-NoElevate` to skip.
- SMB Settings panel: every hidden registry / Group Policy SMB knob (client, server, policy,
  per-adapter NetBIOS) in one window; insecure values flagged.
- Never disconnects a share already mapped to a drive letter.
