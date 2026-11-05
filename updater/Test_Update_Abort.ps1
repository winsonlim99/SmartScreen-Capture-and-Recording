# Run on Windows: powershell -NoProfile -File updater/Test_Update_Abort.ps1
# Uses only disposable directories; never starts the real capture application.
$ErrorActionPreference = 'Stop'
$engine = (Get-Process -Id $PID).Path
$temp = Join-Path ([IO.Path]::GetTempPath()) ('SmartScreenAbortTest_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp | Out-Null
try {
    foreach ($scenario in @('existing-backup', 'invalid-schema', 'bad-hash')) {
        $root = Join-Path $temp $scenario
        $stage = Join-Path $root 'stage'
        $backup = Join-Path $root '.update_backup'
        New-Item -ItemType Directory -Path $stage -Force | Out-Null
        $installed = Join-Path $root 'SmartScreen_Capture.exe'
        Set-Content -LiteralPath $installed -Value 'installed-original'
        if ($scenario -eq 'existing-backup') {
            New-Item -ItemType Directory -Path $backup | Out-Null
            Set-Content -LiteralPath (Join-Path $backup 'recovery.txt') -Value 'previous recovery'
        }
        $schema = 1
        if ($scenario -eq 'invalid-schema') { $schema = 2 }
        $manifest = @{schema=$schema; version='1.0.2'; files=@(@{path='SmartScreen_Capture.exe'; sha256=('0' * 64); size=1})}
        $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $stage 'version.json') -Encoding UTF8
        Set-Content -LiteralPath (Join-Path $stage 'SmartScreen_Capture.exe') -Value 'bad staged content'
        $log = Join-Path $root 'update.log'
        # PID 0 is not used: find a definitely absent process ID for the wait step.
        $absentPid = 2147483647
        if (Get-Process -Id $absentPid -ErrorAction SilentlyContinue) { throw 'Test PID is in use' }
        & $engine -NoProfile -NonInteractive -File (Join-Path $PSScriptRoot 'Apply_Update.ps1') -AppDir $root -StageDir $stage -ParentPid $absentPid -LogFile $log -ReadyFile (Join-Path $root 'ready')
        if ($LASTEXITCODE -ne 1) { throw "Expected aborted update: $scenario" }
        if ((Get-Content -LiteralPath $installed -Raw).Trim() -ne 'installed-original') { throw 'Installed file changed' }
        if ($scenario -eq 'existing-backup') {
            if ((Get-Content -LiteralPath (Join-Path $backup 'recovery.txt') -Raw).Trim() -ne 'previous recovery') { throw 'Previous backup damaged' }
        } elseif (Test-Path -LiteralPath $backup) { throw 'Owned incomplete backup not cleaned' }
        if ((Get-Content -LiteralPath $log -Raw) -notmatch 'Installation did not begin') { throw 'Unexpected rollback path' }
        Write-Host "PASS: $scenario"
    }
} finally {
    Remove-Item -LiteralPath $temp -Recurse -Force
}
