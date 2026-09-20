# Changelog — check-smb-sharemount

All notable changes to the Check-SmbShareMount SMB share-mount diagnostic.
Versions follow [semver](https://semver.org); see `../VERSIONING.md`.

## 0.2.1 — 2026-09-20

### Fixed
- Throughput test now authenticates to the server (via `-User`/`-Password`) before writing, so it works on
  shares that require credentials; no longer warns about a leftover file that was never created.
- The window no longer freezes during a network test: ping, MTU search, traceroute and the throughput
  read/write pump the UI so it stays responsive on slow or lossy links.

### Docs
- README documents the network metering; in-script help lists `-Settings`, `-Network`, `-ThroughputMB`, `-NoElevate`.

## 0.2.0 — 2026-09-20

### Added
- Network metering (informational, no pass/fail): a **Network...** button and `-Network` switch measure
  share throughput (write and read MB/s), ping latency and loss, the path MTU (whether jumbo frames pass
  end to end), and a traceroute. Uses the .NET `Ping` API and `FileStream` — built-in, no packet crafting.

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
