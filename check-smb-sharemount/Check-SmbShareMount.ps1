<#
.SYNOPSIS
  Check-SmbShareMount.ps1 - explain, in plain language, why a Windows PC can or cannot mount an SMB file share.
.DESCRIPTION
  Uses ONLY built-in, Microsoft-signed Windows commands (net use, WMI, TcpClient, nbtstat, and
  Test-NetConnection / Get-SmbConnection where present). No hand-crafted network packets, so endpoint
  security (CrowdStrike, Defender, Bitdefender) does not flag it. Run it on the PC that has the problem.
  UNIVERSAL: Windows 7 / 8 / 10 / 11 and Server 2008 R2+ (PowerShell 2.0 and up). On Windows 7 the
  modern cmdlets are absent, so it falls back to a raw TCP port check and does not print the negotiated
  SMB dialect - the diagnosis and fix are otherwise identical.

  Sections:
    CLIENT  - this PC's Windows version and whether its SMB1 / SMB2 client is on
    TARGET  - does the server name resolve, and does it answer on the SMB ports (445 / 139)
    MOUNT   - actually connect with net use, read the real error code, list shares, negotiated SMB version,
              volume label / free space, optional write test
    VERDICT - one plain-language reason and the exact fix commands
.PARAMETER Target   server IP, name, or \\server\share
.PARAMETER Share    share name (optional if included in Target)
.PARAMETER User / Password  credentials for the connection test
.PARAMETER WriteTest  create, read back and delete a tiny file to prove write access
.PARAMETER Fix      apply the recommended client-side fix (needs Run as administrator)
.PARAMETER Gui      show the window (default when no Target is given)
.PARAMETER Settings open the SMB settings panel (registry / Group Policy knobs); alone, dumps them as text
.PARAMETER Network  meter the target: throughput MB/s, ping, path MTU / jumbo, traceroute (informational)
.PARAMETER ThroughputMB  size of the throughput test file in MB (default 256)
.PARAMETER NoElevate  do not auto-relaunch through UAC as administrator
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File Check-SmbShareMount.ps1 -Target \\SERVER\Share -WriteTest
.NOTES
  v1.2 2026-09-20. Universal Windows 7 through 11 / Server 2008 R2+. No packet crafting, so it is safe on
  CrowdStrike/Defender/Bitdefender boxes. Replaces the older Test-SmbCompat.ps1.
#>
param(
  [string]$Target,
  [string]$Share,
  [string]$User,
  [string]$Password,
  [int]$TimeoutSec = 5,
  [switch]$WriteTest,
  [switch]$Fix,
  [switch]$Force,
  [switch]$Gui,
  [switch]$Settings,
  [switch]$NoElevate,
  [switch]$Network,
  [int]$ThroughputMB = 256
)
$ErrorActionPreference = 'Continue'
$ScriptVersion = '0.2.1'   # keep in sync with check-smb-sharemount/VERSION + CHANGELOG

# ---- self-elevate: relaunch through UAC as administrator (pattern matches evs-xfile-xsquare) ----
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if(-not $NoElevate -and -not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
  $selfPath = $PSCommandPath; if(-not $selfPath){ $selfPath = $MyInvocation.MyCommand.Definition }   # $PSCommandPath is $null on PowerShell 2.0 (Windows 7)
  try {
    $argList = @('-NoProfile','-ExecutionPolicy','Bypass','-STA','-File',"`"$selfPath`"")
    foreach($kv in $PSBoundParameters.GetEnumerator()){
      if($kv.Key -eq 'NoElevate'){ continue }
      if($kv.Value -is [switch]){ if($kv.Value.IsPresent){ $argList += "-$($kv.Key)" } }
      else { $argList += "-$($kv.Key)"; $argList += "`"$($kv.Value)`"" }
    }
    Write-Host 'Re-launching elevated...' -ForegroundColor Yellow
    Start-Process powershell.exe -Verb RunAs -ArgumentList $argList
    exit
  } catch {
    Write-Host 'Running WITHOUT administrator rights (you declined the prompt) - diagnosis works; applying fixes and changing settings is disabled.' -ForegroundColor Yellow
  }
}

# ---------------- output (console + optional GUI) ----------------
$script:GuiState = $null
$script:Report = New-Object System.Text.StringBuilder
$script:Findings = @()
$script:FixAction = $null
$script:FixDeps = @()
$script:LastWhy = $null
$script:LastIp = $null
function Emit([string]$text,[string]$color){
  [void]$script:Report.AppendLine($text)
  if($color){ Write-Host $text -ForegroundColor $color } else { Write-Host $text }
  if($script:GuiState){
    $rtb=$script:GuiState.Rtb
    $c=[System.Drawing.Color]::WhiteSmoke
    switch($color){ 'Cyan'{$c=[System.Drawing.Color]::Cyan} 'Green'{$c=[System.Drawing.Color]::LightGreen} 'Yellow'{$c=[System.Drawing.Color]::Gold} 'Red'{$c=[System.Drawing.Color]::OrangeRed} 'Gray'{$c=[System.Drawing.Color]::Silver} 'White'{$c=[System.Drawing.Color]::White} }
    $rtb.SelectionStart=$rtb.TextLength; $rtb.SelectionLength=0; $rtb.SelectionColor=$c
    $rtb.AppendText($text + "`r`n"); $rtb.SelectionStart=$rtb.TextLength; $rtb.ScrollToCaret()
    [System.Windows.Forms.Application]::DoEvents()
  }
}
function Sect($t){ Emit '' ; Emit ('== ' + $t + ' ' + ('=' * [Math]::Max(1, 74 - $t.Length))) 'Cyan' }
function Row($k,$v){ Emit ('  {0,-26} {1}' -f $k, $v) }
function Ok($t){ Emit ('  [OK]   ' + $t) 'Green' }
function Warn($t){ Emit ('  [WARN] ' + $t) 'Yellow' }
function Fail($t){ Emit ('  [FAIL] ' + $t) 'Red' }
function Note($t){ Emit ('  [info] ' + $t) 'Gray' }
function Pump(){ if($script:GuiState){ try { [System.Windows.Forms.Application]::DoEvents() } catch {} } }

# ---------------- helpers (all built-in) ----------------
function Reg-Val($path,$name){ try { $p = Get-ItemProperty -Path $path -ErrorAction Stop; if($p.PSObject.Properties[$name]){ return $p.$name } } catch {} ; return $null }
function Get-DriverInfo($name){ $d = Get-WmiObject Win32_SystemDriver -Filter "Name='$name'" -ErrorAction SilentlyContinue; if(-not $d){ return $null }; return (New-Object PSObject -Property @{Name=$name;State=$d.State;StartMode=$d.StartMode}) }
function Fmt-Drv($d){ if(-not $d){ return 'not installed' }; return ('{0}, start type {1}' -f $d.State, $d.StartMode) }
function Run-Cmd([string]$cmdline){ $o = & cmd.exe /c ($cmdline + ' 2>&1'); return (($o | ForEach-Object { "$_" }) -join "`n").Trim() }

$script:NetErrors = @{
  5    = 'Access denied - the login worked but this account has no rights on the share or its folders (or the server demands SMB3 encryption this PC cannot do)'
  53   = 'Network path not found - the name did not resolve, or nothing is answering file sharing at that address'
  64   = 'The specified network name is no longer available - the PC reached the server but they could not agree on an SMB version (usually this PC has SMB2 turned off and the server refuses the old SMB1), or a signing/encryption mismatch'
  67   = 'Network name cannot be found - that share name does not exist on the server (see the share list)'
  85   = 'That drive letter is already in use'
  86   = 'The network password is not correct'
  1219 = 'This PC already has a connection to that server under a different account - disconnect it first, then retry'
  1272 = 'Guest access is blocked by THIS PC''s security policy: the server allowed guest, Windows 10/11 refused it. Use a real user name and password, or allow guest access on this PC'
  1326 = 'Logon failure: wrong user name or password (or a blank password the server will not accept, or guest access is turned off on the server)'
  1327 = 'Account restriction - often a blank password is not allowed for network logon'
  1330 = 'The password has expired'
  1331 = 'The account is disabled'
  1385 = 'This account is not allowed to log on over the network to that server'
  1909 = 'The account is locked out'
}
function Explain-NetError([int]$code){ if($script:NetErrors.ContainsKey($code)){ return $script:NetErrors[$code] }; return ('Windows error ' + $code) }
function Net-Use($unc,$user,$pass){
  if($user){ $p = $pass; if(-not $p){ $p='""' } else { $p='"' + $pass + '"' }; $txt = Run-Cmd ('net use "' + $unc + '" ' + $p + ' /user:"' + $user + '"') }
  else { $txt = Run-Cmd ('net use "' + $unc + '"') }
  $code = 0; if($txt -match 'System error (\d+)'){ $code=[int]$matches[1] } elseif($txt -notmatch 'completed successfully'){ $code=-1 }
  return @{Code=$code;Text=$txt}
}
function Net-Del($unc){ [void](Run-Cmd ('net use "' + $unc + '" /delete /y')) }
function Get-MappedDrives(){
  # every network drive this PC is configured for, INCLUDING disconnected / Unavailable ones
  $status=@{}
  foreach($l in ((Run-Cmd 'net use') -split "`n")){ if($l -match '^\s*(OK|Disconnected|Unavailable)\s+([A-Za-z]:)\s'){ $status[$matches[2].ToUpper()]=$matches[1] } }
  $list=@()
  try { Get-ChildItem 'HKCU:\Network' -ErrorAction SilentlyContinue | ForEach-Object {
      $d=($_.PSChildName + ':').ToUpper(); $rp=(Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue).RemotePath
      if($rp){ $st=$status[$d]; if(-not $st){ $st='not connected' }; $list += (New-Object PSObject -Property @{Drive=$d;Unc=$rp;Status=$st}) } } } catch {}
  foreach($l in ((Run-Cmd 'net use') -split "`n")){ if($l -match '^\s*(OK|Disconnected|Unavailable)\s+([A-Za-z]:)\s+(\\\\[^\s]+)'){
      $d=$matches[2].ToUpper(); if(-not ($list | Where-Object { $_.Drive -eq $d })){ $list += (New-Object PSObject -Property @{Drive=$d;Unc=$matches[3].Trim();Status=$matches[1]}) } } }
  return ,$list
}

# =====================================================================
# main analysis
# =====================================================================
function Invoke-Check([string]$Target,[string]$Share,[string]$User,[string]$Password,[int]$TimeoutSec,[bool]$WriteTest,[bool]$Fix,[bool]$Force){
  $script:Findings=@(); $script:FixAction=$null; $script:FixDeps=@(); $script:Report=New-Object System.Text.StringBuilder; $script:LastWhy=$null; $script:LastIp=$null
  if($TimeoutSec -le 0){ $TimeoutSec=5 }
  # ---- parse target
  $t=$Target.Trim()
  if($t -match '^\\\\([^\\]+)\\([^\\]+)'){ $HostName=$matches[1]; if(-not $Share){ $Share=$matches[2] } }
  elseif($t -match '^\\\\([^\\]+)\\?$'){ $HostName=$matches[1] }
  else { $HostName=$t }
  $HostName=$HostName.Trim('\').Trim(); if($Share){ $Share=$Share.Trim('\').Trim() }
  Emit ('Check-SmbShareMount v' + $ScriptVersion + '   ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '   server=' + $HostName + '  share=' + $Share + '  user=' + $User) 'White'

  # ---- CLIENT
  Sect 'CLIENT (this PC)'
  $os=Get-WmiObject Win32_OperatingSystem; $cs=Get-WmiObject Win32_ComputerSystem; $osVer=[version]$os.Version
  $isAdmin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  Row 'This PC' ('{0}  ({1})' -f $env:COMPUTERNAME, $cs.Domain)
  Row 'Windows' ('{0}  build {1}  {2}' -f $os.Caption.Trim(), $os.BuildNumber, $os.OSArchitecture)
  Row 'PowerShell / admin' ('{0} / {1}' -f $PSVersionTable.PSVersion, $(if($isAdmin){'yes'}else{'no (needed only for -Fix)'}))
  $smb1=Get-DriverInfo 'mrxsmb10'; $smb2=Get-DriverInfo 'mrxsmb20'
  $wsDeps=@(); $tmp=Reg-Val 'HKLM:\SYSTEM\CurrentControlSet\Services\LanmanWorkstation' 'DependOnService'; if($tmp){ $wsDeps=@($tmp) }
  Row 'SMB1 client (old)' (Fmt-Drv $smb1)
  Row 'SMB2/3 client (modern)' (Fmt-Drv $smb2)
  $clientSmb2=($smb2 -ne $null) -and ($smb2.StartMode -ne 'Disabled') -and (($smb2.State -eq 'Running') -or ($wsDeps -contains 'mrxsmb20'))
  $clientSmb1=($smb1 -ne $null) -and ($smb1.StartMode -ne 'Disabled')
  $scc=$null; if(Get-Command Get-SmbClientConfiguration -ErrorAction SilentlyContinue){ try { $scc=Get-SmbClientConfiguration -ErrorAction Stop } catch {} }
  if($scc){ Row 'Insecure guest logons' $(if($scc.EnableInsecureGuestLogons){'allowed'}else{'blocked (default) - guest/anonymous shares will be refused by THIS PC'}); Row 'Require SMB signing' $scc.RequireSecuritySignature }
  if($clientSmb2){ Ok 'this PC can speak modern SMB2/SMB3' } else { if($smb2 -and $smb2.StartMode -eq 'Disabled'){ Fail 'the SMB2/3 client is TURNED OFF on this PC - it can only use the old SMB1, which most servers now refuse' } else { Warn 'the SMB2/3 client does not look active' } }
  if(-not $clientSmb1){ Note 'the old SMB1 client is off or not installed (normal and safe on Windows 10/11); SMB1-only servers cannot be reached from here' }

  # ---- TARGET
  Sect ('TARGET  ' + $HostName)
  $ip=$null; $isIp=$false; $tmpAddr=$null; $nameResolved=$true
  if([System.Net.IPAddress]::TryParse($HostName,[ref]$tmpAddr)){ $isIp=$true; $ip=$HostName }
  if($isIp){ try { Row 'Reverse name' ([System.Net.Dns]::GetHostEntry($ip)).HostName } catch { Row 'Reverse name' 'none' } }
  else {
    try { $addrs=@([System.Net.Dns]::GetHostAddresses($HostName) | Where-Object { $_.AddressFamily -eq 'InterNetwork' }); if($addrs.Count -eq 0){ throw 'no IPv4 address' }
      $ip=$addrs[0].IPAddressToString; Row 'Name resolves to' (@($addrs | ForEach-Object { $_.IPAddressToString }) -join ', '); Ok 'the server name resolves to an address' }
    catch { $nameResolved=$false; Fail ('the name "' + $HostName + '" does not resolve to an address on this PC (' + $_.Exception.Message + ')') }
  }
  $smbPort=$null; $nbName=$null
  if($ip){
    $nbOut=@(& nbtstat.exe -A $ip 2>&1 | ForEach-Object { "$_" })
    foreach($l in $nbOut){ if($l -match '^\s+(\S.*?)\s+<00>\s+UNIQUE' -and -not $nbName){ $nbName=$matches[1].Trim() } }
    if($nbName){ Row 'Server short name' $nbName }
    $p445=$null; $p139=$null
    if(Get-Command Test-NetConnection -ErrorAction SilentlyContinue){
      try { $p445=(Test-NetConnection -ComputerName $ip -Port 445 -WarningAction SilentlyContinue -ErrorAction Stop).TcpTestSucceeded } catch { $p445=$false }
      try { $p139=(Test-NetConnection -ComputerName $ip -Port 139 -WarningAction SilentlyContinue -ErrorAction Stop).TcpTestSucceeded } catch { $p139=$false }
    } else {
      foreach($pr in @(445,139)){ $c=New-Object System.Net.Sockets.TcpClient; try { $ar=$c.BeginConnect($ip,$pr,$null,$null); $okc=$ar.AsyncWaitHandle.WaitOne($TimeoutSec*1000,$false); if($okc){ $c.EndConnect($ar) }; if($pr -eq 445){ $p445=$okc } else { $p139=$okc } } catch { if($pr -eq 445){ $p445=$false } else { $p139=$false } } finally { $c.Close() } }
    }
    Row 'File sharing port 445' $(if($p445){'open'}else{'closed / blocked'})
    Row 'Old NetBIOS port 139' $(if($p139){'open'}else{'closed'})
    if($p445){ $smbPort=445 } elseif($p139){ $smbPort=139 } else { Fail 'nothing is answering file sharing at that address (both 445 and 139 are closed)' }
  }
  $script:LastIp=$ip

  # ---- MOUNT (real connection through Windows)
  $mountCode=$null; $shareCode=$null; $shares=@(); $volLabel=$null; $freeBytes=$null; $writeOk=$null; $dialect=$null; $mountHost=$HostName; $credUser=$User; $credPass=$Password
  if($ip -and $smbPort){
    Sect ('MOUNT  \\' + $HostName + '   (real connection through Windows)')
    $preConns=@(); foreach($pl in ((Run-Cmd 'net use') -split "`n")){ if($pl -match '(\\\\[^\s]+)'){ $preConns += $matches[1].TrimEnd('\').ToLower() } }
    try { Get-ChildItem 'HKCU:\Network' -ErrorAction SilentlyContinue | ForEach-Object { $rp=(Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue).RemotePath; if($rp){ $preConns += $rp.TrimEnd('\').ToLower() } } } catch {}
    $existing=@((Run-Cmd 'net use') -split "`n" | Where-Object { $_ -match ('\\\\' + [regex]::Escape($HostName) + '\\') -or ($ip -and $_ -match ('\\\\' + [regex]::Escape($ip) + '\\')) })
    if($existing.Count){ Warn 'this PC already has connections to that server in this session:'; foreach($e in $existing){ Emit ('        ' + $e.Trim()) 'Gray' } }
    if($User -and -not $Password){ Warn 'a user name was given with an empty password - most servers reject that for network logon' }
    $ipcUnc='\\' + $HostName + '\IPC$'
    $m=Net-Use $ipcUnc $User $Password; $mountCode=$m.Code
    if($m.Code -eq 1219){ $m3=Net-Use $ipcUnc $null $null; if($m3.Code -eq 0){ Warn 'the login you gave was refused because this PC already has a connection to that server; using the existing one'; $mountCode=0; $credUser=$null; $credPass=$null } }
    if($mountCode -eq 0){ Ok ('connected to the server (' + $(if($credUser){'as ' + $credUser}else{'as the logged-in user or existing session'}) + ')') }
    else { Fail ('could not connect to the server: error ' + $m.Code + ' - ' + (Explain-NetError $m.Code)); Emit ('        ' + ($m.Text -replace "`n",' | ')) 'Gray' }
    if($mountCode -ne 0 -and -not $isIp -and $ip -and $nameResolved){ $m2=Net-Use ('\\' + $ip + '\IPC$') $User $Password; if($m2.Code -eq 0){ Warn ('but connecting by ADDRESS (' + $ip + ') works - the problem is the name, not the server; use the address'); $mountHost=$ip; $ipcUnc='\\' + $ip + '\IPC$'; $mountCode=0 } }
    if($mountCode -eq 0){
      # negotiated SMB version + server info, from Windows itself
      if(Get-Command Get-SmbConnection -ErrorAction SilentlyContinue){
        try { $conn=@(Get-SmbConnection -ServerName $mountHost -ErrorAction SilentlyContinue); if(-not $conn -or $conn.Count -eq 0){ $conn=@(Get-SmbConnection -ErrorAction SilentlyContinue | Where-Object { $_.ServerName -eq $mountHost -or $_.ServerName -eq $ip -or $_.ServerName -eq $HostName }) }
          if($conn.Count){ $dialect=($conn[0].Dialect); Row 'SMB version in use' $dialect } } catch {}
      }
      $nv=Run-Cmd ('net view "\\' + $mountHost + '"')
      if($nv -notmatch 'System error'){ $inList=$false; foreach($l in ($nv -split "`n")){ if($l -match '^-{10,}'){ $inList=$true; continue }; if(-not $inList){ continue }; if($l -match '^(.+?)\s{2,}(Disk|Print|IPC)\b'){ $shares += $matches[1].Trim() } }; Row 'Shares on server' ($(if($shares.Count){ $shares -join ', ' }else{'none visible'})) }
      if($Share){
        $shareUnc='\\' + $mountHost + '\' + $Share
        $sm=Net-Use $shareUnc $credUser $credPass; $shareCode=$sm.Code
        if($sm.Code -eq 0){
          Ok ('the share ' + $shareUnc + ' opened')
          $dr=Run-Cmd ('dir "' + $shareUnc + '"')
          if($dr -match 'Volume in drive .* is (.+)'){ $volLabel=$matches[1].Trim(); Row 'Volume label' $volLabel }
          if($dr -match '([\d,]+) bytes free'){ $freeBytes=[int64]($matches[1] -replace ',',''); Row 'Free space' ('{0:N1} GB' -f ($freeBytes/1GB)) }
          if($dr -match 'Access is denied'){ Warn 'opened the share but the folder listing is denied (share lets you connect, file permissions block reading)' }
          if($WriteTest){
            $tf=$shareUnc + '\_sharecheck_' + $env:COMPUTERNAME + '_' + (Get-Date -Format 'yyyyMMddHHmmss') + '.txt'
            $wrote=$false
            try { [System.IO.File]::WriteAllText($tf,'share write test'); $wrote=$true; $back=[System.IO.File]::ReadAllText($tf); if($back -match 'write test'){ $writeOk=$true; Ok 'WRITE test passed (created and read back a file)' } else { $writeOk=$false; Fail 'write test: the file did not read back' } }
            catch { $writeOk=$false; Fail ('WRITE test failed: ' + $_.Exception.Message) }
            if($wrote){ try { [System.IO.File]::Delete($tf) } catch { Warn ('could not delete the test file - please remove it by hand: ' + $tf) } }
          }
          if($preConns -contains $shareUnc.TrimEnd('\').ToLower()){ Note 'left your existing connection to this share in place (it was already mapped, e.g. a drive letter)' } else { Net-Del $shareUnc }
        } else { Fail ('the share ' + $shareUnc + ' would not open: error ' + $sm.Code + ' - ' + (Explain-NetError $sm.Code)); Emit ('        ' + ($sm.Text -replace "`n",' | ')) 'Gray' }
      }
      if($preConns -contains $ipcUnc.TrimEnd('\').ToLower()){ } else { Net-Del $ipcUnc }
    }
  }

  # ---- VERDICT
  Sect 'VERDICT'
  $why=$null; $fixText=$null
  if(-not $nameResolved){ $why='The name "' + $HostName + '" does not resolve to an address on this PC, so every attempt to reach it by name fails.'; $fixText='Use the numeric address instead, or add the name to this PC (an entry in C:\Windows\System32\drivers\etc\hosts), or point it at a DNS/WINS server that knows the name.' }
  elseif(-not $smbPort){ $why='This PC reached the network but nothing is answering file sharing at ' + $ip + ' (ports 445 and 139 are closed).'; $fixText='Check that this is the right address, that the server has file sharing turned on, and that no firewall between them blocks port 445.' }
  elseif($mountCode -eq 0 -and (-not $Share -or $shareCode -eq 0) -and -not ($WriteTest -and $writeOk -eq $false)){
    $why='WORKS.' + $(if($dialect){' Connected using SMB ' + $dialect + '.'}else{''}) + $(if($Share){' The share \\' + $mountHost + '\' + $Share + ' opened' + $(if($volLabel){' (volume ' + $volLabel + ')'}else{''}) + $(if($writeOk){' and the write test passed'}else{''}) + '.'}else{' The server login works.'})
    $fixText=$null
  }
  elseif($mountCode -ne 0){
    $why='This PC reached the server but the connection failed with error ' + $mountCode + ': ' + (Explain-NetError $mountCode)
    if(-not $clientSmb2){
      $why='This PC''s modern SMB2/SMB3 client is turned OFF, so it cannot open a modern share (the connection failed with error ' + $mountCode + '). ' + $(if(-not $clientSmb1){'It has no SMB1 client either, so right now it has no working SMB version at all.'}else{'It can only fall back to the old SMB1, which most servers refuse.'})
      $fixText='Turn the modern SMB2/3 client back on. Run these lines in an Administrator Command Prompt on THIS PC (a reboot may be needed to fully load it):' + "`n" + '      sc config mrxsmb20 start= auto' + "`n" + '      sc config lanmanworkstation depend= ' + (@(@($wsDeps | Where-Object { $_ -and $_ -ne 'mrxsmb20' }) + 'mrxsmb20') -join '/') + "`n" + '      sc start mrxsmb20' + "`n" + '   or click "Apply fix" in this tool.'
      $script:FixAction='EnableSmb2Client'; $script:FixDeps=@(@($wsDeps | Where-Object { $_ -and $_ -ne 'mrxsmb20' }) + 'mrxsmb20')
    }
    elseif($mountCode -eq 64){
      $fixText='The two agreed on nothing at the SMB level. Usually the server requires encrypted/signed SMB3 this PC or network cannot provide, or the server has a signing requirement. Check the server''s SMB signing/encryption settings.'
    }
    elseif($mountCode -eq 1272){ $why='This PC reached the server but Windows on THIS PC blocked the connection because the share uses guest (unauthenticated) access, which Windows 10/11 refuses by default.'
      $fixText='Either type a real user name and password for that server above, or allow guest access on this PC (a security trade-off). Click "Apply fix" to allow guest, or run as administrator:' + "`n" + '      reg add "HKLM\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters" /v AllowInsecureGuestAuth /t REG_DWORD /d 1 /f'
      $script:FixAction='AllowGuest' }
    elseif($mountCode -eq 1326){
      if(-not $credUser -and $scc -and -not $scc.EnableInsecureGuestLogons){ $why='The login was refused. No user name was given, and this PC blocks guest (unauthenticated) shares, so if this is a guest share the connection is stopped by THIS PC.'; $fixText='Best: type a real user name and password above and check again. If the share is meant to be open to everyone (guest), click "Apply fix" to allow guest access on this PC (a security trade-off).'; $script:FixAction='AllowGuest' }
      else { $fixText='Check the user name and password. If the account has no password, either give it one or allow blank-password network logon on the server. If you gave no credentials and this is not a guest share, supply a user and password.' } }
    elseif($mountCode -eq 86){ $fixText='The password is wrong.' }
    elseif($mountCode -eq 5){ $fixText='Give this account permission on the share and on the folder (at least Change / Modify).' }
    elseif($mountCode -eq 1219){ $fixText='Disconnect the existing connection to that server first: run  net use  to see it, then  net use \\' + $HostName + '\<share> /delete  and retry.' }
    elseif($mountCode -eq 53){ $fixText='Try the address form instead: \\' + $ip + '\' + $Share }
    else { $fixText='See the plain-language error above.' }
  }
  elseif($Share -and $shareCode -ne 0){
    $inList=@($shares | Where-Object { $_.ToLower() -eq $Share.ToLower() })
    if($shares.Count -and $inList.Count -eq 0){ $why='The server login works, but there is no share called "' + $Share + '" on it.'; $fixText='Use one of the shares the server actually offers: ' + ($shares -join ', ') }
    elseif($shareCode -eq 5){ $why='The server login works and the share exists, but this account is denied access to it (error 5).'; $fixText='Give this account at least Read/Change permission on the share and on the folder.' }
    else { $why='The server login works, but the share "' + $Share + '" would not open: error ' + $shareCode + ' - ' + (Explain-NetError $shareCode); $fixText=$(if($shares.Count){ 'Check the share name. The server offers: ' + ($shares -join ', ') } else { 'See the error above.' }) } }
  elseif($WriteTest -and $writeOk -eq $false){ $why='You can open the share but not write to it.'; $fixText='The account needs Change / Modify permission on the share and the folder; also check free space and quotas.' }
  else { $why='Reached the server; nothing else tested.'; $fixText=$null }
  $idLine='Server: ' + $(if($nbName){$nbName + ' at '}else{''}) + $(if($ip){$ip}else{$HostName}) + $(if($dialect){' - answering SMB ' + $dialect}elseif($smbPort){' - file sharing reachable'}else{''}) + $(if($shares.Count){'; shares: ' + ($shares -join ', ')}else{''})
  Emit ('  ' + $idLine) 'White'
  Emit ('  ' + $why) $(if($why -like 'WORKS*'){'Green'}else{'Red'})
  if($fixText){ Emit ('  FIX: ' + $fixText) 'Yellow' }
  $script:LastWhy=$why

  if($Fix){ Apply-Fix $Force $credUser $credPass }
  Emit ''; Emit ('Done ' + (Get-Date -Format 'HH:mm:ss')) 'Gray'
}

# =====================================================================
# FIX
# =====================================================================
function Apply-Fix([bool]$force,[string]$user,[string]$pass){
  Sect 'FIX'
  if($script:FixAction -ne 'EnableSmb2Client' -and $script:FixAction -ne 'AllowGuest'){ Note 'no automatic fix applies here - follow the FIX line above by hand'; return $false }
  $isAdmin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  if(-not $isAdmin){ Fail 'this needs administrator rights - right-click, Run as administrator, and try Apply fix again'; return $false }
  if($script:FixAction -eq 'AllowGuest'){
    Emit '  will run:  reg add HKLM\...\LanmanWorkstation\Parameters /v AllowInsecureGuestAuth /d 1   (lets this PC use guest/unauthenticated shares - a security trade-off)' 'White'
    if(-not $force){ if($script:GuiState){ $a=[System.Windows.Forms.MessageBox]::Show('Allow guest (unauthenticated) file shares on ' + $env:COMPUTERNAME + '?' + [Environment]::NewLine + 'This is a security trade-off - only do it for a trusted network.','Apply fix',[System.Windows.Forms.MessageBoxButtons]::YesNo,[System.Windows.Forms.MessageBoxIcon]::Warning); if($a -ne [System.Windows.Forms.DialogResult]::Yes){ Note 'cancelled'; return $false } } else { $a=Read-Host '  allow guest access on this PC? [y/N]'; if($a -notmatch '^[yY]'){ Note 'cancelled'; return $false } } }
    [void](& reg.exe add 'HKLM\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters' /v AllowInsecureGuestAuth /t REG_DWORD /d 1 /f 2>&1)
    $v=Reg-Val 'HKLM:\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters' 'AllowInsecureGuestAuth'
    if($v -eq 1){ Ok 'guest access is now allowed on this PC - click Check now again' } else { Warn 'the setting did not take - try again as administrator' }
    $script:FixAction=$null; return ($v -eq 1)
  }
  $depStr=($script:FixDeps -join '/')
  Emit ('  will run:  sc config mrxsmb20 start= auto ;  sc config lanmanworkstation depend= ' + $depStr + ' ;  sc start mrxsmb20') 'White'
  if(-not $force){
    if($script:GuiState){ $a=[System.Windows.Forms.MessageBox]::Show(('Turn the SMB2/3 client back on for ' + $env:COMPUTERNAME + '?'),'Apply fix',[System.Windows.Forms.MessageBoxButtons]::YesNo,[System.Windows.Forms.MessageBoxIcon]::Question); if($a -ne [System.Windows.Forms.DialogResult]::Yes){ Note 'cancelled'; return $false } }
    else { $a=Read-Host '  apply now? [y/N]'; if($a -notmatch '^[yY]'){ Note 'cancelled'; return $false } }
  }
  [void](& sc.exe config mrxsmb20 start= auto 2>&1)
  [void](& sc.exe config lanmanworkstation depend= $depStr 2>&1)
  $o3 = & sc.exe start mrxsmb20 2>&1
  $d=Get-DriverInfo 'mrxsmb20'; Row 'SMB2/3 client now' (Fmt-Drv $d)
  $reOk=$false
  if($script:LastIp){ $m=Net-Use ('\\' + $script:LastIp + '\IPC$') $user $pass; if($m.Code -eq 0){ $reOk=$true; Net-Del ('\\' + $script:LastIp + '\IPC$') } }
  if($reOk){ Ok 'FIXED - the SMB2/3 client is back on and the server is reachable now (start type auto).' }
  elseif($d -and $d.State -eq 'Running'){ Warn 'Settings applied and the driver is loaded, but Windows started the file-sharing client without it at last boot, so it will not be used until you REBOOT this PC. Reboot, then the share will work.' }
  else { Warn 'Settings applied; REBOOT this PC to load the SMB2/3 client.' }
  $script:FixAction=$null; return $true
}

# =====================================================================
# SMB SETTINGS  (every hidden reg / Group Policy knob, read + change)
# =====================================================================
function DwordOr($psPath,$name,$def){ $v=Reg-Val $psPath $name; if($v -eq $null){ return $def }; try { return [int]$v } catch { return $def } }
function RegSetDword($regPath,$name,$val){ [void](& reg.exe add $regPath /v $name /t REG_DWORD /d $val /f 2>&1) }
$LWP='HKLM:\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters'
$LWPr='HKLM\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters'
$LSP='HKLM:\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters'
$LSPr='HKLM\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters'
$LSA='HKLM:\SYSTEM\CurrentControlSet\Control\Lsa'
$LSAr='HKLM\SYSTEM\CurrentControlSet\Control\Lsa'

function Set-Smb2Client([bool]$on){
  $cur=@($null); $d=(Reg-Val 'HKLM:\SYSTEM\CurrentControlSet\Services\LanmanWorkstation' 'DependOnService'); if($d){ $cur=@($d) }
  if($on){ [void](& sc.exe config mrxsmb20 start= auto 2>&1); $dep=@(@($cur | Where-Object { $_ -and $_ -ne 'mrxsmb20' }) + 'mrxsmb20'); [void](& sc.exe config lanmanworkstation depend= ($dep -join '/') 2>&1); [void](& sc.exe start mrxsmb20 2>&1) }
  else { [void](& sc.exe config mrxsmb20 start= disabled 2>&1); $dep=@($cur | Where-Object { $_ -and $_ -ne 'mrxsmb20' }); if($dep.Count -eq 0){ $dep=@('bowser','mrxsmb10','nsi') }; [void](& sc.exe config lanmanworkstation depend= ($dep -join '/') 2>&1) }
}
function Set-Smb1Client([bool]$on){ if($on){ [void](& sc.exe config mrxsmb10 start= auto 2>&1); [void](& sc.exe start mrxsmb10 2>&1) } else { [void](& sc.exe config mrxsmb10 start= disabled 2>&1) } }
function Set-SrvCfg($name,$val){ if(Get-Command Set-SmbServerConfiguration -ErrorAction SilentlyContinue){ try { $h=@{}; $h[$name]=$val; Set-SmbServerConfiguration @h -Force -ErrorAction Stop; return $true } catch {} } ; return $false }

function Knob($id,$group,$label,$kind,$get,$set,$where,$opts,$secureNote){ return (New-Object PSObject -Property @{Id=$id;Group=$group;Label=$label;Kind=$kind;Get=$get;Set=$set;Where=$where;Opts=$opts;Secure=$secureNote;Ctrl=$null}) }

function Get-SmbKnobs(){
  $k=@()
  # ---- CLIENT ----
  $k += Knob 'smb2client' 'Client (this PC connecting out)' 'SMB2/SMB3 client engine' 'bool' `
    { $d=Get-DriverInfo 'mrxsmb20'; $on=($d -ne $null -and $d.StartMode -ne 'Disabled'); @{Cur=$on;Display=$(if($on){'ON'}else{'OFF - can only use old SMB1'});Secure=$on} } `
    { param($v) Set-Smb2Client([bool]$v) } `
    'Service mrxsmb20 Start + LanmanWorkstation DependOnService (regedit / sc). No GUI.' $null 'ON is correct; OFF breaks most modern shares.'
  $k += Knob 'smb1client' 'Client (this PC connecting out)' 'SMB1 client engine (legacy, insecure)' 'bool' `
    { $d=Get-DriverInfo 'mrxsmb10'; $on=($d -ne $null -and $d.StartMode -ne 'Disabled'); @{Cur=$on;Display=$(if($on){'ON (insecure)'}else{'OFF (good)'});Secure=(-not $on)} } `
    { param($v) Set-Smb1Client([bool]$v) } `
    'Service mrxsmb10 Start / Windows feature SMB1Protocol-Client. gpedit: none.' $null 'Keep OFF unless a very old NAS needs it.'
  $k += Knob 'guest' 'Client (this PC connecting out)' 'Allow insecure guest logons' 'bool' `
    { $v=DwordOr $LWP 'AllowInsecureGuestAuth' 0; @{Cur=($v -eq 1);Display=$(if($v){'ALLOWED (insecure)'}else{'blocked (default)'});Secure=($v -ne 1)} } `
    { param($v) RegSetDword $LWPr 'AllowInsecureGuestAuth' $(if($v){1}else{0}) } `
    'LanmanWorkstation\Parameters\AllowInsecureGuestAuth. gpedit: Computer\Admin Templates\Network\Lanman Workstation\Enable insecure guest logons.' $null 'ON lets you reach passwordless NAS shares but is a security trade-off.'
  $k += Knob 'clsignreq' 'Client (this PC connecting out)' 'Client requires SMB signing' 'bool' `
    { $v=DwordOr $LWP 'RequireSecuritySignature' 0; @{Cur=($v -eq 1);Display=$(if($v){'required'}else{'not required (default)'});Secure=$true} } `
    { param($v) RegSetDword $LWPr 'RequireSecuritySignature' $(if($v){1}else{0}) } `
    'LanmanWorkstation\Parameters\RequireSecuritySignature. gpedit: Microsoft network client: Digitally sign communications (always).' $null 'ON is more secure but a server that cannot sign will then fail.'
  $k += Knob 'lmcompat' 'Client (this PC connecting out)' 'NTLM / LM authentication level' 'enum' `
    { $v=DwordOr $LSA 'LmCompatibilityLevel' 3; @{Cur=$v;Display=('level ' + $v + $(if($v -lt 3){' (weak - sends LM/NTLMv1)'}else{' (NTLMv2)'}));Secure=($v -ge 3)} } `
    { param($v) RegSetDword $LSAr 'LmCompatibilityLevel' ([int]$v) } `
    'Lsa\LmCompatibilityLevel. gpedit: Network security: LAN Manager authentication level.' `
    (@((New-Object PSObject -Property @{Text='0 - LM & NTLM';Value=0}),(New-Object PSObject -Property @{Text='1 - LM & NTLM, NTLMv2 if negotiated';Value=1}),(New-Object PSObject -Property @{Text='2 - NTLM only';Value=2}),(New-Object PSObject -Property @{Text='3 - NTLMv2 only (default, recommended)';Value=3}),(New-Object PSObject -Property @{Text='4 - NTLMv2, refuse LM';Value=4}),(New-Object PSObject -Property @{Text='5 - NTLMv2, refuse LM & NTLM';Value=5}))) `
    'Below 3 can cause logon failures against hardened servers/Samba.'
  $k += Knob 'plaintext' 'Client (this PC connecting out)' 'Send plaintext passwords to SMB servers' 'bool' `
    { $v=DwordOr $LWP 'EnablePlainTextPassword' 0; @{Cur=($v -eq 1);Display=$(if($v){'ON (dangerous)'}else{'off (default)'});Secure=($v -ne 1)} } `
    { param($v) RegSetDword $LWPr 'EnablePlainTextPassword' $(if($v){1}else{0}) } `
    'LanmanWorkstation\Parameters\EnablePlainTextPassword. gpedit: Send unencrypted password to third-party SMB servers.' $null 'Almost never turn ON.'
  # ---- SERVER ----
  $k += Knob 'smb1srv' 'Server (this PC sharing out)' 'SMB1 server (accept old clients)' 'bool' `
    { $v=DwordOr $LSP 'SMB1' 1; @{Cur=($v -eq 1);Display=$(if($v){'ON (insecure)'}else{'OFF (good)'});Secure=($v -ne 1)} } `
    { param($v) if(-not (Set-SrvCfg 'EnableSMB1Protocol' ([bool]$v))){ RegSetDword $LSPr 'SMB1' $(if($v){1}else{0}) } } `
    'LanmanServer\Parameters\SMB1 / Set-SmbServerConfiguration -EnableSMB1Protocol.' $null 'Keep OFF; SMB1 is the WannaCry vector.'
  $k += Knob 'smb2srv' 'Server (this PC sharing out)' 'SMB2/SMB3 server' 'bool' `
    { $v=DwordOr $LSP 'SMB2' 1; @{Cur=($v -eq 1);Display=$(if($v){'ON (default)'}else{'OFF'});Secure=($v -eq 1)} } `
    { param($v) if(-not (Set-SrvCfg 'EnableSMB2Protocol' ([bool]$v))){ RegSetDword $LSPr 'SMB2' $(if($v){1}else{0}) } } `
    'LanmanServer\Parameters\SMB2 / Set-SmbServerConfiguration -EnableSMB2Protocol.' $null 'Leave ON.'
  $k += Knob 'srvsignreq' 'Server (this PC sharing out)' 'Server requires SMB signing' 'bool' `
    { $v=DwordOr $LSP 'RequireSecuritySignature' 0; @{Cur=($v -eq 1);Display=$(if($v){'required'}else{'not required'});Secure=$true} } `
    { param($v) if(-not (Set-SrvCfg 'RequireSecuritySignature' ([bool]$v))){ RegSetDword $LSPr 'RequireSecuritySignature' $(if($v){1}else{0}) } } `
    'LanmanServer\Parameters\RequireSecuritySignature. gpedit: Microsoft network server: Digitally sign (always).' $null 'ON is more secure; old clients that cannot sign then fail.'
  $k += Knob 'encrypt' 'Server (this PC sharing out)' 'Require SMB3 encryption (reject unencrypted)' 'bool' `
    { $v=DwordOr $LSP 'RejectUnencryptedAccess' 0; $e=DwordOr $LSP 'EncryptData' 0; @{Cur=($e -eq 1 -or $v -eq 1);Display=$(if($e -eq 1){'encryption ON'}else{'off (default)'});Secure=$true} } `
    { param($v) if(-not (Set-SrvCfg 'EncryptData' ([bool]$v))){ RegSetDword $LSPr 'EncryptData' $(if($v){1}else{0}) } } `
    'Set-SmbServerConfiguration -EncryptData (Win8+) / LanmanServer\Parameters\EncryptData. No gpedit.' $null 'ON blocks Windows 7 clients (they cannot do SMB3 encryption).'
  $k += Knob 'nullsess' 'Server (this PC sharing out)' 'Restrict null-session (anonymous) access' 'bool' `
    { $v=DwordOr $LSP 'RestrictNullSessAccess' 1; @{Cur=($v -eq 1);Display=$(if($v){'restricted (default)'}else{'ALLOWED (insecure)'});Secure=($v -eq 1)} } `
    { param($v) RegSetDword $LSPr 'RestrictNullSessAccess' $(if($v){1}else{0}) } `
    'LanmanServer\Parameters\RestrictNullSessAccess.' $null 'Keep restricted.'
  $k += Knob 'adminshares' 'Server (this PC sharing out)' 'Automatic admin shares (C$, ADMIN$)' 'bool' `
    { $n=$(if((Get-WmiObject Win32_OperatingSystem).ProductType -eq 1){'AutoShareWks'}else{'AutoShareServer'}); $v=DwordOr $LSP $n 1; @{Cur=($v -eq 1);Display=$(if($v){'ON (default)'}else{'OFF'});Secure=$true} } `
    { param($v) $n=$(if((Get-WmiObject Win32_OperatingSystem).ProductType -eq 1){'AutoShareWks'}else{'AutoShareServer'}); RegSetDword $LSPr $n $(if($v){1}else{0}) } `
    'LanmanServer\Parameters\AutoShareWks / AutoShareServer.' $null 'OFF hides C$/ADMIN$ (some tools rely on them).'
  # ---- POLICY / NTLM ----
  $k += Knob 'restrictanon' 'Windows security policy' 'Restrict anonymous access' 'enum' `
    { $v=DwordOr $LSA 'RestrictAnonymous' 0; @{Cur=$v;Display=('level ' + $v);Secure=($v -ge 1)} } `
    { param($v) RegSetDword $LSAr 'RestrictAnonymous' ([int]$v) } `
    'Lsa\RestrictAnonymous. gpedit: Network access: Do not allow anonymous enumeration...' `
    (@((New-Object PSObject -Property @{Text='0 - none (default)';Value=0}),(New-Object PSObject -Property @{Text='1 - no enumeration';Value=1}),(New-Object PSObject -Property @{Text='2 - full restriction';Value=2}))) `
    'Higher = tighter, can break browsing/older apps.'
  $k += Knob 'nolmhash' 'Windows security policy' 'Do not store LM hash of passwords' 'bool' `
    { $v=DwordOr $LSA 'NoLmHash' 1; @{Cur=($v -eq 1);Display=$(if($v){'on (default, good)'}else{'OFF (stores weak LM hash)'});Secure=($v -eq 1)} } `
    { param($v) RegSetDword $LSAr 'NoLmHash' $(if($v){1}else{0}) } `
    'Lsa\NoLmHash. gpedit: Network security: Do not store LAN Manager hash value on next password change.' $null 'Keep ON.'
  # ---- NETWORK ----
  $k += Knob 'netbios' 'Network adapters' 'NetBIOS over TCP/IP (all adapters)' 'enum' `
    { $vals=@(); Get-WmiObject Win32_NetworkAdapterConfiguration -Filter 'IPEnabled=true' | ForEach-Object { $vals += [int]$_.TcpipNetbiosOptions }; $u=@($vals | Sort-Object -Unique); $cur=$(if($u.Count -eq 1){$u[0]}else{-1}); @{Cur=$cur;Display=$(if($cur -eq 0){'default (DHCP)'}elseif($cur -eq 1){'enabled on all'}elseif($cur -eq 2){'DISABLED on all'}else{'mixed per adapter'});Secure=$true} } `
    { param($v) Get-WmiObject Win32_NetworkAdapterConfiguration -Filter 'IPEnabled=true' | ForEach-Object { [void]$_.SetTcpipNetbios([int]$v) } } `
    'Per-NIC Tcpip\Parameters\Interfaces\{..}\NetbiosOptions. GUI: NIC > IPv4 > Advanced > WINS.' `
    (@((New-Object PSObject -Property @{Text='0 - default (from DHCP)';Value=0}),(New-Object PSObject -Property @{Text='1 - enable NetBIOS';Value=1}),(New-Object PSObject -Property @{Text='2 - disable NetBIOS';Value=2}))) `
    'Disabling stops \\NAME browsing but not \\IP or DNS.'
  return ,$k
}

function Show-SmbSettings($owner){
  $isAdmin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  $sf=New-Object System.Windows.Forms.Form
  $sf.Text='SMB settings - the hidden registry / Group Policy knobs, all in one place'
  $sf.Size=New-Object System.Drawing.Size(940,720); $sf.StartPosition='CenterParent'; $sf.MinimumSize=New-Object System.Drawing.Size(760,520)
  $sf.Font=New-Object System.Drawing.Font('Segoe UI',9)
  $hdr=New-Object System.Windows.Forms.Label; $hdr.Location=New-Object System.Drawing.Point(12,10); $hdr.Size=New-Object System.Drawing.Size(900,34); $hdr.Anchor='Top,Left,Right'
  $hdr.Text=('Every setting here normally lives in regedit or gpedit.msc. Change it, then Apply.' + $(if($isAdmin){''}else{'   NOT admin - reopen as administrator to apply changes.'}))
  if(-not $isAdmin){ $hdr.ForeColor=[System.Drawing.Color]::Firebrick }
  $sf.Controls.Add($hdr)
  $panel=New-Object System.Windows.Forms.Panel; $panel.Location=New-Object System.Drawing.Point(12,48); $panel.Size=New-Object System.Drawing.Size(900,600); $panel.Anchor='Top,Bottom,Left,Right'; $panel.AutoScroll=$true; $panel.BorderStyle='FixedSingle'; $sf.Controls.Add($panel)
  $knobs=Get-SmbKnobs
  $tip=New-Object System.Windows.Forms.ToolTip; $tip.AutoPopDelay=20000; $tip.IsBalloon=$true
  $y=8; $lastGroup=''
  foreach($kn in $knobs){
    if($kn.Group -ne $lastGroup){ $gl=New-Object System.Windows.Forms.Label; $gl.Location=New-Object System.Drawing.Point(8,$y); $gl.Size=New-Object System.Drawing.Size(860,20); $gl.Text=$kn.Group; $gl.Font=New-Object System.Drawing.Font('Segoe UI',9,[System.Drawing.FontStyle]::Bold); $panel.Controls.Add($gl); $y+=24; $lastGroup=$kn.Group }
    $cur=& $kn.Get
    $lbl=New-Object System.Windows.Forms.Label; $lbl.Location=New-Object System.Drawing.Point(16,($y+4)); $lbl.Size=New-Object System.Drawing.Size(300,20); $lbl.Text=$kn.Label; $panel.Controls.Add($lbl)
    $val=New-Object System.Windows.Forms.Label; $val.Location=New-Object System.Drawing.Point(320,($y+4)); $val.Size=New-Object System.Drawing.Size(210,20); $val.Text=$cur.Display; if(-not $cur.Secure){ $val.ForeColor=[System.Drawing.Color]::DarkOrange }; $panel.Controls.Add($val)
    if($kn.Kind -eq 'bool'){ $c=New-Object System.Windows.Forms.CheckBox; $c.Location=New-Object System.Drawing.Point(540,($y+2)); $c.Size=New-Object System.Drawing.Size(120,22); $c.Text='enabled'; $c.Checked=[bool]$cur.Cur }
    else { $c=New-Object System.Windows.Forms.ComboBox; $c.Location=New-Object System.Drawing.Point(540,($y+2)); $c.Size=New-Object System.Drawing.Size(300,24); $c.DropDownStyle='DropDownList'; $c.DisplayMember='Text'; foreach($o in $kn.Opts){ [void]$c.Items.Add($o) }; for($i=0;$i -lt $c.Items.Count;$i++){ if([int]$c.Items[$i].Value -eq [int]$cur.Cur){ $c.SelectedIndex=$i } } }
    $c.Enabled=$isAdmin; $panel.Controls.Add($c); $kn.Ctrl=$c
    $inf=New-Object System.Windows.Forms.Label; $inf.Location=New-Object System.Drawing.Point(852,($y+4)); $inf.Size=New-Object System.Drawing.Size(20,18); $inf.Text='(?)'; $inf.ForeColor=[System.Drawing.Color]::SteelBlue; $tip.SetToolTip($inf, ($kn.Label + "`r`n`r`nWhere it lives: " + $kn.Where + "`r`n`r`n" + $kn.Secure)); $panel.Controls.Add($inf)
    $y+=30
  }
  $status=New-Object System.Windows.Forms.Label; $status.Location=New-Object System.Drawing.Point(12,656); $status.Size=New-Object System.Drawing.Size(500,22); $status.Anchor='Bottom,Left'; $status.Text=($knobs.Count.ToString() + ' settings loaded'); $sf.Controls.Add($status)
  $bApply=New-Object System.Windows.Forms.Button; $bApply.Text='Apply changes'; $bApply.Location=New-Object System.Drawing.Point(600,652); $bApply.Size=New-Object System.Drawing.Size(120,28); $bApply.Anchor='Bottom,Right'; $bApply.Enabled=$isAdmin; $sf.Controls.Add($bApply)
  $bRef=New-Object System.Windows.Forms.Button; $bRef.Text='Refresh'; $bRef.Location=New-Object System.Drawing.Point(726,652); $bRef.Size=New-Object System.Drawing.Size(90,28); $bRef.Anchor='Bottom,Right'; $sf.Controls.Add($bRef)
  $bClose=New-Object System.Windows.Forms.Button; $bClose.Text='Close'; $bClose.Location=New-Object System.Drawing.Point(822,652); $bClose.Size=New-Object System.Drawing.Size(90,28); $bClose.Anchor='Bottom,Right'; $sf.Controls.Add($bClose)
  $bClose.Add_Click({ $sf.Close() })
  $bRef.Add_Click({ $sf.Close(); Show-SmbSettings $owner })
  $bApply.Add_Click({
    $changed=0; $errs=0; $names=@()
    foreach($kn in $knobs){
      $cur=& $kn.Get; $want=$null
      if($kn.Kind -eq 'bool'){ $want=[bool]$kn.Ctrl.Checked; $same=([bool]$cur.Cur -eq $want) }
      else { if($kn.Ctrl.SelectedItem){ $want=[int]$kn.Ctrl.SelectedItem.Value } else { $want=[int]$cur.Cur }; $same=([int]$cur.Cur -eq $want) }
      if(-not $same){ try { & $kn.Set $want; $changed++; $names += $kn.Label } catch { $errs++ } }
    }
    $msg=('Applied ' + $changed + ' change(s)' + $(if($errs){', ' + $errs + ' failed'}else{''}) + '. Some (SMB1/SMB2 engine, signing) need a reboot to fully take effect.')
    [void][System.Windows.Forms.MessageBox]::Show($msg,'SMB settings')
    $sf.Close(); Show-SmbSettings $owner
  })
  if($owner){ [void]$sf.ShowDialog($owner) } else { [void]$sf.ShowDialog() }
}
function Dump-SmbSettings(){
  Sect 'SMB SETTINGS (hidden registry / Group Policy knobs)'
  $lastG=''
  foreach($kn in (Get-SmbKnobs)){
    if($kn.Group -ne $lastG){ Emit ('  -- ' + $kn.Group + ' --') 'White'; $lastG=$kn.Group }
    $cur=& $kn.Get
    Emit ('  {0,-42} {1}' -f $kn.Label, $cur.Display) $(if($cur.Secure){'Gray'}else{'Yellow'})
  }
  Note 'change any of these from the GUI: run with -Gui and click "SMB Settings...". Needs admin.'
}

# =====================================================================
# NETWORK METERING  (informational only - ping / MTU / traceroute / throughput)
# Uses System.Net.NetworkInformation.Ping (OS ICMP, not raw sockets) + FileStream.
# PowerShell 2.0 / .NET 2.0 safe; no packet crafting, so endpoint security is fine.
# =====================================================================
function Meter-Ping($ip,$count){
  $p=New-Object System.Net.NetworkInformation.Ping; $rtts=@(); $recv=0
  for($i=0;$i -lt $count;$i++){ try { $r=$p.Send($ip,1500); if($r.Status -eq 'Success'){ $recv++; $rtts+=[int]$r.RoundtripTime } } catch {}; Pump }
  $res=@{Sent=$count;Recv=$recv;LossPct=[int]((($count-$recv)/$count)*100);Min=$null;Avg=$null;Max=$null}
  if($rtts.Count){ $res.Min=($rtts|Measure-Object -Minimum).Minimum; $res.Max=($rtts|Measure-Object -Maximum).Maximum; $res.Avg=[Math]::Round((($rtts|Measure-Object -Average).Average),1) }
  return $res
}
function Meter-Mtu($ip){
  $p=New-Object System.Net.NetworkInformation.Ping
  $opt=New-Object System.Net.NetworkInformation.PingOptions(64,$true)   # Ttl=64, DontFragment=true
  $probe=New-Object byte[] 32
  try { if(($p.Send($ip,1500,$probe,$opt)).Status -ne 'Success'){ return @{Reachable=$false} } } catch { return @{Reachable=$false} }
  $lo=0; $hi=8972; $best=0
  while($lo -le $hi){
    $mid=[int](($lo+$hi)/2); $buf=New-Object byte[] $mid; $ok=$false
    try { if(($p.Send($ip,1500,$buf,$opt)).Status -eq 'Success'){ $ok=$true } } catch {}
    if($ok){ $best=$mid; $lo=$mid+1 } else { $hi=$mid-1 }; Pump
  }
  return @{Reachable=$true;Payload=$best;Mtu=($best+28);Jumbo=(($best+28) -gt 1500)}
}
function Meter-Trace($ip,$maxHops){
  $hops=@(); $p=New-Object System.Net.NetworkInformation.Ping; $buf=New-Object byte[] 32
  for($ttl=1;$ttl -le $maxHops;$ttl++){
    $opt=New-Object System.Net.NetworkInformation.PingOptions($ttl,$false)
    $addr='*'; $ms=$null; $done=$false
    try { $r=$p.Send($ip,1500,$buf,$opt); if($r.Address){ $addr=$r.Address.ToString() }; if($r.RoundtripTime){ $ms=[int]$r.RoundtripTime }
          if($r.Status -eq 'Success'){ $done=$true } elseif($r.Status -ne 'TtlExpired' -and $r.Status -ne 'TimedOut'){ $addr=('(' + $r.Status + ')') } } catch {}
    $hops += (New-Object PSObject -Property @{Ttl=$ttl;Addr=$addr;Ms=$ms}); Pump
    if($done){ break }
  }
  return ,$hops
}
function Meter-Throughput($shareUnc,$mb){
  $res=@{Ok=$false}
  $chunk=New-Object byte[] (8*1024*1024); (New-Object Random).NextBytes($chunk)
  $tf=$shareUnc + '\_nettest_' + $env:COMPUTERNAME + '_' + (Get-Date -Format 'HHmmss') + '.tmp'
  $iters=[int][Math]::Ceiling($mb/8.0); if($iters -lt 1){ $iters=1 }
  $bytes=[int64]$iters * $chunk.Length
  $created=$false
  try {
    $sw=[System.Diagnostics.Stopwatch]::StartNew(); $fs=[System.IO.File]::Create($tf); $created=$true
    for($i=0;$i -lt $iters;$i++){ $fs.Write($chunk,0,$chunk.Length); Pump }
    $fs.Close(); $sw.Stop()
    $res.WriteSec=$sw.Elapsed.TotalSeconds; if($res.WriteSec -gt 0){ $res.WriteMBs=(($bytes/1MB)/$res.WriteSec) }
    $sw2=[System.Diagnostics.Stopwatch]::StartNew(); $fr=[System.IO.File]::OpenRead($tf); $rbuf=New-Object byte[] (8*1024*1024); $tot=[int64]0
    do { $n=$fr.Read($rbuf,0,$rbuf.Length); $tot+=$n; Pump } while($n -gt 0)
    $fr.Close(); $sw2.Stop()
    $res.ReadSec=$sw2.Elapsed.TotalSeconds; if($res.ReadSec -gt 0){ $res.ReadMBs=(($tot/1MB)/$res.ReadSec) }
    $res.Bytes=$bytes; $res.Ok=$true
  } catch { $res.Err=$_.Exception.Message }
  if($created){ try { [System.IO.File]::Delete($tf) } catch { $res.Leftover=$tf } }
  return $res
}
function Invoke-Network([string]$Target,[string]$Share,[int]$ThroughputMB,[string]$User,[string]$Password){
  if($ThroughputMB -le 0){ $ThroughputMB=256 }
  $t=$Target.Trim()
  if($t -match '^\\\\([^\\]+)\\([^\\]+)'){ $HostName=$matches[1]; if(-not $Share){ $Share=$matches[2] } }
  elseif($t -match '^\\\\([^\\]+)\\?$'){ $HostName=$matches[1] } else { $HostName=$t }
  $HostName=$HostName.Trim('\').Trim(); if($Share){ $Share=$Share.Trim('\').Trim() }
  $ip=$HostName; $tmpAddr=$null
  if(-not [System.Net.IPAddress]::TryParse($HostName,[ref]$tmpAddr)){
    try { $ip=(@([System.Net.Dns]::GetHostAddresses($HostName) | Where-Object { $_.AddressFamily -eq 'InterNetwork' }))[0].IPAddressToString } catch { $ip=$null }
  }
  Sect ('NETWORK  ' + $HostName + $(if($ip -and $ip -ne $HostName){' (' + $ip + ')'}else{''}) + '   (informational)')
  if(-not $ip){ Fail ('cannot resolve ' + $HostName + ' to an address'); return }
  Emit '  measuring...' 'Gray'
  $pg=Meter-Ping $ip 10
  if($pg.Recv -gt 0){ Row 'Ping' ('{0}/{1} replies, {2}% loss   min {3} / avg {4} / max {5} ms' -f $pg.Recv,$pg.Sent,$pg.LossPct,$pg.Min,$pg.Avg,$pg.Max) }
  else { Row 'Ping' ('no replies (' + $pg.LossPct + '% loss) - host may block ICMP') }
  $mt=Meter-Mtu $ip
  if($mt.Reachable){ Row 'Path MTU (largest un-fragmented)' ('{0} bytes   {1}' -f $mt.Mtu, $(if($mt.Jumbo){'JUMBO frames pass end-to-end (>1500)'}else{'standard frames (jumbo does NOT pass this path)'})) }
  else { Note 'MTU probe: host did not answer don''t-fragment pings (ICMP blocked); cannot measure path MTU' }
  Emit '  route:' 'White'
  foreach($h in (Meter-Trace $ip 20)){ Emit ('    {0,2}  {1,-16} {2}' -f $h.Ttl, $h.Addr, $(if($h.Ms -ne $null){[string]$h.Ms + ' ms'}else{''})) 'Gray' }
  if($Share){
    $unc='\\' + $HostName + '\' + $Share
    $ipc='\\' + $HostName + '\IPC$'; $madeConn=$false
    if($User){ $mc=Net-Use $ipc $User $Password; if($mc.Code -eq 0){ $madeConn=$true } else { Warn ('could not log in to ' + $HostName + ' for the throughput test: error ' + $mc.Code + ' - ' + (Explain-NetError $mc.Code)) } }
    Emit ('  throughput: writing/reading ' + $ThroughputMB + ' MB to ' + $unc + ' ...') 'White'
    $tp=Meter-Throughput $unc $ThroughputMB
    if($tp.Ok){
      Row 'Write speed' ('{0:N1} MB/s  ({1:N1} s for {2} MB)' -f $tp.WriteMBs, $tp.WriteSec, $ThroughputMB)
      Row 'Read speed'  ('{0:N1} MB/s  ({1:N1} s)  - may be served from cache' -f $tp.ReadMBs, $tp.ReadSec)
    } else { Warn ('throughput test could not run: ' + $tp.Err) }
    if($tp.Leftover){ Warn ('could not delete the test file, remove it: ' + $tp.Leftover) }
    if($madeConn){ Net-Del $ipc }
  } else { Note 'no share given, so no throughput test (add \\server\share to measure MB/s)' }
}

# =====================================================================
# GUI
# =====================================================================
function Show-Gui([string]$target,[string]$share,[string]$user,[string]$pass){
  Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing
  [System.Windows.Forms.Application]::EnableVisualStyles()
  $f=New-Object System.Windows.Forms.Form
  $f.Text=('Check SMB Share Mount v' + $ScriptVersion + '  -  why can''t this PC open that shared folder?')
  $f.Size=New-Object System.Drawing.Size(1090,700); $f.MinimumSize=New-Object System.Drawing.Size(740,470); $f.StartPosition='CenterScreen'
  $f.Font=New-Object System.Drawing.Font('Segoe UI',9)
  function L($text,$x,$y,$w){ $l=New-Object System.Windows.Forms.Label; $l.Text=$text; $l.Location=New-Object System.Drawing.Point($x,$y); $l.Size=New-Object System.Drawing.Size($w,20); $f.Controls.Add($l); $l }
  function TB($x,$y,$w,$val){ $b=New-Object System.Windows.Forms.TextBox; $b.Location=New-Object System.Drawing.Point($x,$y); $b.Size=New-Object System.Drawing.Size($w,23); $b.Text=$val; $f.Controls.Add($b); $b }
  [void](L 'Mapped drives on this PC (incl. disconnected)' 12 14 270); $cboDrives=New-Object System.Windows.Forms.ComboBox; $cboDrives.Location=New-Object System.Drawing.Point(285,11); $cboDrives.Size=New-Object System.Drawing.Size(475,24); $cboDrives.DropDownStyle='DropDownList'; $cboDrives.DisplayMember='Display'; $f.Controls.Add($cboDrives)
  function BT($text,$x,$y,$w){ $b=New-Object System.Windows.Forms.Button; $b.Text=$text; $b.Location=New-Object System.Drawing.Point($x,$y); $b.Size=New-Object System.Drawing.Size($w,26); $f.Controls.Add($b); $b }
  $btnRefresh=BT 'Refresh' 768 11 90
  [void](L 'Shared folder  (\\server\share or an address)' 12 46 250); $tbTarget=TB 285 44 475 $target
  [void](L 'User' 12 78 40); $tbUser=TB 285 76 200 $user
  [void](L 'Password' 500 78 60); $tbPass=TB 565 76 150 $pass; $tbPass.UseSystemPasswordChar=$true
  $cbWrite=New-Object System.Windows.Forms.CheckBox; $cbWrite.Text='Also test writing a file'; $cbWrite.Location=New-Object System.Drawing.Point(730,76); $cbWrite.Size=New-Object System.Drawing.Size(190,22); $f.Controls.Add($cbWrite)
  # (BT defined above)
  $btnRun=BT 'Check now' 12 110 130; $btnFix=BT 'Apply fix' 150 110 130; $btnFix.Enabled=$false
  $btnCopy=BT 'Copy result' 288 110 110; $btnSave=BT 'Save result...' 404 110 120; $btnClose=BT 'Close' 858 110 90; $btnClose.Anchor='Top,Right'
  $status=New-Object System.Windows.Forms.Label; $status.Location=New-Object System.Drawing.Point(536,116); $status.Size=New-Object System.Drawing.Size(60,22); $status.Text=''; $status.Anchor='Top,Left'; $f.Controls.Add($status)
  $btnNetwork=BT 'Network...' 606 110 116; $btnNetwork.Anchor='Top,Right'; $btnNetwork.Add_Click({ $btnNetwork.Enabled=$false; $btnRun.Enabled=$false; $status.Text='network metering...'; $tg=$tbTarget.Text.Trim(); if($tg){ try { Invoke-Network $tg '' 256 $tbUser.Text.Trim() $tbPass.Text } catch { Emit ('  network error: ' + $_.Exception.Message) 'Red' } } else { [void][System.Windows.Forms.MessageBox]::Show('Enter a server or \\server\share first','Check SMB Share Mount') }; $btnNetwork.Enabled=$true; $btnRun.Enabled=$true; $status.Text='network test done' })
  $btnSettings=BT 'SMB Settings...' 738 110 118; $btnSettings.Anchor='Top,Right'; $btnSettings.Add_Click({ try { Show-SmbSettings $f } catch { Emit ('  settings error: ' + $_.Exception.Message) 'Red' } })
  $rtb=New-Object System.Windows.Forms.RichTextBox
  $rtb.Location=New-Object System.Drawing.Point(12,146); $rtb.Size=New-Object System.Drawing.Size(1056,506); $rtb.Anchor='Top,Bottom,Left,Right'
  $rtb.ReadOnly=$true; $rtb.BackColor=[System.Drawing.Color]::FromArgb(24,24,24); $rtb.ForeColor=[System.Drawing.Color]::WhiteSmoke
  $rtb.Font=New-Object System.Drawing.Font('Consolas',9); $rtb.WordWrap=$false; $rtb.DetectUrls=$false; $rtb.ScrollBars='Both'; $f.Controls.Add($rtb)
  $script:GuiState=@{Form=$f;Rtb=$rtb;Status=$status;BtnFix=$btnFix}
  $runBlock={
    $rtb.Clear(); $btnRun.Enabled=$false; $btnFix.Enabled=$false; $status.Text='checking...'
    $tg=$tbTarget.Text.Trim(); if(-not $tg){ [void][System.Windows.Forms.MessageBox]::Show('Type the shared folder, like \\SERVER\Share','Check SMB Share Mount'); $btnRun.Enabled=$true; return }
    try { Invoke-Check $tg '' $tbUser.Text.Trim() $tbPass.Text 5 ([bool]$cbWrite.Checked) $false $false } catch { Emit ('  tool error: ' + $_.Exception.Message) 'Red' }
    $btnRun.Enabled=$true; $btnFix.Enabled=($script:FixAction -ne $null); $status.Text=$(if($script:LastWhy){ ($script:LastWhy -split '[.:]')[0] }else{'done'})
  }
  $btnRun.Add_Click($runBlock)
  $btnFix.Add_Click({ $btnFix.Enabled=$false; try { [void](Apply-Fix $false $tbUser.Text.Trim() $tbPass.Text) } catch { Emit ('  fix error: ' + $_.Exception.Message) 'Red' }; $status.Text='fix attempted - click Check now again' })
  $btnCopy.Add_Click({ try { [System.Windows.Forms.Clipboard]::SetText($script:Report.ToString()); $status.Text='result copied' } catch { $status.Text='copy failed' } })
  $btnSave.Add_Click({ $d=New-Object System.Windows.Forms.SaveFileDialog; $d.Filter='Text|*.txt'; $d.FileName=('ShareCheck_' + $env:COMPUTERNAME + '_' + (Get-Date -Format 'yyyyMMdd_HHmm') + '.txt'); if($d.ShowDialog() -eq 'OK'){ [System.IO.File]::WriteAllText($d.FileName,$script:Report.ToString()); $status.Text=('saved ' + $d.FileName) } })
  $btnClose.Add_Click({ $f.Close() })
  $script:cboSilent=$false
  $fillDrives={
    $script:cboSilent=$true
    $cboDrives.Items.Clear()
    [void]$cboDrives.Items.Add((New-Object PSObject -Property @{Display='(type a folder below, or pick a mapped drive here)';Unc=''}))
    try { foreach($d in (Get-MappedDrives)){ [void]$cboDrives.Items.Add((New-Object PSObject -Property @{Display=('{0}   {1}   ({2})' -f $d.Drive,$d.Unc,$d.Status);Unc=$d.Unc})) } } catch {}
    $sel=0; if($tbTarget.Text){ for($k=1;$k -lt $cboDrives.Items.Count;$k++){ if($cboDrives.Items[$k].Unc -eq $tbTarget.Text){ $sel=$k; break } } }
    $cboDrives.SelectedIndex=$sel
    if($cboDrives.Items.Count -gt 1){ $status.Text=('found ' + ($cboDrives.Items.Count-1) + ' mapped drive(s) - pick one to diagnose it, even a disconnected one') }
    $script:cboSilent=$false
  }
  $cboDrives.Add_SelectedIndexChanged({ if($script:cboSilent){ return }; $it=$cboDrives.SelectedItem; if($it -and $it.Unc){ $tbTarget.Text=$it.Unc; & $runBlock } })
  $btnRefresh.Add_Click({ & $fillDrives; $status.Text='mapped drives refreshed' })
  $f.AcceptButton=$btnRun
  $f.Add_Shown({ try { $f.Activate(); & $fillDrives; if($tbTarget.Text){ & $runBlock } } catch {} })
  [void]$f.ShowDialog(); $script:GuiState=$null
}

# =====================================================================
# entry point
# =====================================================================
if($Settings -and $Gui){ Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; [System.Windows.Forms.Application]::EnableVisualStyles(); Show-SmbSettings $null }
elseif($Settings){ $script:Report=New-Object System.Text.StringBuilder; Dump-SmbSettings }
elseif($Network){ $script:Report=New-Object System.Text.StringBuilder; Invoke-Network $Target $Share $ThroughputMB $User $Password }
elseif($Gui -or -not $Target){ Show-Gui $Target $Share $User $Password }
else { Invoke-Check $Target $Share $User $Password $TimeoutSec ([bool]$WriteTest) ([bool]$Fix) ([bool]$Force) }
