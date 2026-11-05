param(
    [Parameter(Mandatory=$true)][string]$AppDir,
    [Parameter(Mandatory=$true)][string]$StageDir,
    [Parameter(Mandatory=$true)][int]$ParentPid,
    [Parameter(Mandatory=$true)][string]$LogFile,
    [Parameter(Mandatory=$true)][string]$ReadyFile
)
$ErrorActionPreference = 'Stop'
function Log([string]$Message) {
    $line = "$(Get-Date -Format s) $Message"
    try { Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8 } catch {}
}
function Sha([string]$Name) { return (Get-FileHash -LiteralPath $Name -Algorithm SHA256).Hash.ToLowerInvariant() }
function CopyChecked([string]$Source,[string]$Target,[string]$Expected) {
    $parent = Split-Path -Parent $Target
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    Copy-Item -LiteralPath $Source -Destination $Target -Force
    if ((Sha $Target) -ne $Expected) { throw "SHA-256 mismatch after install: $Target" }
}
$backup = Join-Path $AppDir '.update_backup'
$oldFiles = New-Object 'System.Collections.Generic.List[string]'
$newFiles = New-Object 'System.Collections.Generic.List[string]'
$started = $false
$ownsBackup = $false
$installStarted = $false
$committed = $false
try {
    Log 'Updater started; waiting for SmartScreen to close.'
    Set-Content -LiteralPath $ReadyFile -Value 'ready' -Encoding Ascii
    $deadline = (Get-Date).AddSeconds(60)
    while (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue) {
        if ((Get-Date) -gt $deadline) { throw 'SmartScreen remained running; update cancelled' }
        Start-Sleep -Milliseconds 350
    }
    $manifest = Get-Content -LiteralPath (Join-Path $StageDir 'version.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.schema -ne 1) { throw 'Invalid manifest schema' }
    if (Test-Path -LiteralPath $backup) { throw 'Previous update backup exists; manual review required' }
    New-Item -ItemType Directory -Path $backup | Out-Null
    $ownsBackup = $true
    $files = @($manifest.files)
    $files += [pscustomobject]@{ path='version.json'; sha256=(Sha (Join-Path $StageDir 'version.json')); size=(Get-Item (Join-Path $StageDir 'version.json')).Length }
    foreach ($file in $files) {
        $rel = [string]$file.path
        if ($rel.StartsWith('/') -or $rel.Contains('..') -or $rel.Contains(':') -or $rel.Contains('\') -or $rel -match '(^|/)(config\.json|update_source\.txt)$') { throw "Unsafe update path: $rel" }
        $relative = $rel.Replace('/', [IO.Path]::DirectorySeparatorChar)
        $src = Join-Path $StageDir $relative
        $dst = Join-Path $AppDir $relative
        if (-not (Test-Path -LiteralPath $src -PathType Leaf)) { throw "Missing staged file: $rel" }
        if ((Sha $src) -ne [string]$file.sha256) { throw "Staged file changed: $rel" }
        if (Test-Path -LiteralPath $dst -PathType Leaf) {
            $targetBackup = Join-Path $backup $relative
            $parent = Split-Path -Parent $targetBackup
            if (-not (Test-Path -LiteralPath $parent)) { New-Item -Path $parent -ItemType Directory -Force | Out-Null }
            Copy-Item -LiteralPath $dst -Destination $targetBackup -Force
            $oldFiles.Add($rel)
        } else { $newFiles.Add($rel) }
    }
    $installStarted = $true
    foreach ($file in $files) {
        $relative = ([string]$file.path).Replace('/', [IO.Path]::DirectorySeparatorChar)
        CopyChecked (Join-Path $StageDir $relative) (Join-Path $AppDir $relative) ([string]$file.sha256)
    }
    Log "Copied and verified version $($manifest.version); launching app for health check"
    $ack = Join-Path $StageDir 'startup.ok'
    if (Test-Path $ack) { Remove-Item -LiteralPath $ack -Force }
    $env:SMARTSCREEN_UPDATE_ACK = $ack
    $app = Start-Process -FilePath (Join-Path $AppDir 'SmartScreen_Capture.exe') -WorkingDirectory $AppDir -PassThru
    Remove-Item Env:SMARTSCREEN_UPDATE_ACK -ErrorAction SilentlyContinue
    $started = $true
    $deadline = (Get-Date).AddSeconds(35)
    while (-not (Test-Path -LiteralPath $ack)) {
        if ($app.HasExited) { throw 'Updated application exited before reporting ready' }
        if ((Get-Date) -gt $deadline) { throw 'Updated application did not report ready' }
        Start-Sleep -Milliseconds 350
    }
    $committed = $true
    Log "Update succeeded: $($manifest.version)"
    Remove-Item -LiteralPath $backup -Recurse -Force
    Remove-Item -LiteralPath $StageDir -Recurse -Force
    exit 0
} catch {
    Log "Update failed: $($_.Exception.Message)"
    if ($committed) {
        Log 'Update is healthy; cleanup failed. Preserve remaining files for manual review.'
        exit 1
    }
    if (-not $installStarted) {
        # Never remove a backup belonging to an earlier update or restart an
        # application that may still be running after the parent-exit timeout.
        if ($ownsBackup -and (Test-Path -LiteralPath $backup)) {
            Remove-Item -LiteralPath $backup -Recurse -Force
        }
        Log 'Installation did not begin; installed files and existing backups preserved.'
        exit 1
    }
    Log 'Attempting rollback' 
    try {
        if ($started -and $app -and -not $app.HasExited) {
            Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 600
        }
        foreach ($rel in $newFiles) {
            $dst = Join-Path $AppDir ($rel.Replace('/', [IO.Path]::DirectorySeparatorChar))
            if (Test-Path -LiteralPath $dst -PathType Leaf) { Remove-Item -LiteralPath $dst -Force }
        }
        foreach ($rel in $oldFiles) {
            $relative = $rel.Replace('/', [IO.Path]::DirectorySeparatorChar)
            $src = Join-Path $backup $relative
            $dst = Join-Path $AppDir $relative
            $parent = Split-Path -Parent $dst
            if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
            Copy-Item -LiteralPath $src -Destination $dst -Force
        }
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
        Log 'Rollback completed; restarting previous version'
        Start-Process -FilePath (Join-Path $AppDir 'SmartScreen_Capture.exe') -WorkingDirectory $AppDir | Out-Null
    } catch { Log "ROLLBACK FAILURE: $($_.Exception.Message) - IT/manual intervention required" }
    exit 1
}
