# Local-only MongoDB, no administrator rights or Windows service required.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$localRoot = Join-Path $env:LOCALAPPDATA 'FloodWatch'
$toolsDir = Join-Path $localRoot 'tools'
$dbDir = Join-Path $localRoot 'mongodb/data'
$logPath = Join-Path $localRoot 'mongodb/mongod.log'
New-Item -ItemType Directory -Path $toolsDir, $dbDir -Force | Out-Null
$mongod = Get-ChildItem -LiteralPath $toolsDir -Filter mongod.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $mongod) {
    Write-Host 'Downloading MongoDB Community from the official distribution...'
    $manifest = Invoke-RestMethod -Uri 'https://downloads.mongodb.org/current.json' -TimeoutSec 30
    $release = $manifest.versions | Where-Object { $_.version -match '^8\.0\.\d+$' } | Select-Object -First 1
    $download = $release.downloads | Where-Object { $_.target -eq 'windows' -and $_.arch -eq 'x86_64' -and $_.edition -eq 'base' } | Select-Object -First 1
    if (-not $download.archive.url -or -not $download.archive.sha256) { throw 'Official MongoDB Windows archive metadata unavailable' }
    $archivePath = Join-Path $toolsDir 'mongodb.zip'
    $archiveValid = (Test-Path -LiteralPath $archivePath) -and ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant() -eq $download.archive.sha256.ToLowerInvariant())
    if (-not $archiveValid) {
        & curl.exe --fail --location --silent --show-error --retry 3 --connect-timeout 20 --max-time 600 --continue-at - --output $archivePath $download.archive.url
        if ($LASTEXITCODE -ne 0) { throw 'MongoDB download failed; rerun this script to resume the download' }
    }
    if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $download.archive.sha256.ToLowerInvariant()) { throw 'MongoDB archive checksum mismatch' }
    # Windows PowerShell Expand-Archive fails on this official archive on some
    # systems. Native tar also lets us avoid unpacking the large debug symbols.
    $archiveRoot = 'mongodb-win32-x86_64-windows-' + $release.version
    & tar.exe -xf $archivePath -C $toolsDir "$archiveRoot/bin/mongod.exe" "$archiveRoot/LICENSE-Community.txt" "$archiveRoot/MPL-2" "$archiveRoot/THIRD-PARTY-NOTICES"
    if ($LASTEXITCODE -ne 0) { throw 'MongoDB archive extraction failed' }
    $mongod = Get-ChildItem -LiteralPath $toolsDir -Filter mongod.exe -Recurse | Select-Object -First 1
    if (-not $mongod) { throw 'MongoDB executable not found after extraction' }
}
$listener = Get-NetTCPConnection -LocalPort 27017 -State Listen -ErrorAction SilentlyContinue
if (-not $listener) {
    $mongoArgs = @('--bind_ip', '127.0.0.1', '--port', '27017', '--replSet', 'floodwatch', '--oplogSize', '128', '--wiredTigerCacheSizeGB', '0.25', '--dbpath', ('"' + $dbDir + '"'), '--logpath', ('"' + $logPath + '"'), '--logappend')
    Start-Process -FilePath $mongod.FullName -ArgumentList $mongoArgs -WindowStyle Hidden | Out-Null
}
$pythonPath = Join-Path $repoRoot 'backend/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run python -m uv sync --python 3.12 in backend first' }
& $pythonPath (Join-Path $PSScriptRoot 'init-mongodb.py')
if ($LASTEXITCODE -ne 0) { throw 'MongoDB initialization failed. Check the local MongoDB log or configure MONGODB_URI.' }
Write-Host "Database files: $dbDir"
Write-Host "MongoDB log: $logPath"
