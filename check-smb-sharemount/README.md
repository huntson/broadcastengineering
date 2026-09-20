# Check-SmbShareMount

Plain-language diagnostic for "why can't this PC open that shared folder?" (SMB / network drives), plus one-click fixes for the common causes.

Runs on the PC that has the problem, Windows 7 through 11 (PowerShell 2.0 and up). Uses only built-in, Microsoft-signed Windows commands — no hand-crafted network packets — so endpoint security (CrowdStrike, Defender, Bitdefender) does not flag it.

## What it checks

- CLIENT: this PC's SMB1 / SMB2 client state, signing and guest policy.
- TARGET: name resolution and whether the server answers on the SMB ports (445 / 139).
- MOUNT: a real `net use` connection with the decoded error, the share list, the negotiated SMB version, and an optional write test.
- VERDICT: one plain sentence saying why it fails, and the exact fix.

## Run it

Right-click `Check-SmbShareMount.ps1` and choose **Run with PowerShell** (opens the window), or:

```
powershell -ExecutionPolicy Bypass -File Check-SmbShareMount.ps1                          # window
powershell -ExecutionPolicy Bypass -File Check-SmbShareMount.ps1 -Target \\SERVER\Share -WriteTest   # text
powershell -ExecutionPolicy Bypass -File Check-SmbShareMount.ps1 -Settings                # dump every SMB setting
```

It auto-elevates through UAC when it is not already administrator. Pass `-NoElevate` to skip that. Decline the prompt and it still runs, read-only.

## Fixes and settings

- **Apply fix** turns the SMB2/3 client back on, or allows guest shares, when that is the cause. On Windows 10/11 re-enabling the SMB2 client needs a reboot to take effect; the tool says so.
- **SMB Settings** opens every hidden registry / Group Policy SMB knob (client, server, policy, per-adapter NetBIOS) in one window — change them without regedit or gpedit. Insecure values are flagged.

## Notes

- Windows 8+ shows the negotiated SMB dialect; Windows 7 (no `Get-SmbConnection`) omits it — the diagnosis and fix are otherwise identical.
- It never disconnects a share you already have mapped to a drive letter.
