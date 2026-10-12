<#
.SYNOPSIS
  Membangun installer Windows Peta Toko (PetaToko-Setup-<versi>.exe).

.DESCRIPTION
  Langkah: unduh+verifikasi komponen -> Python embeddable + dependensi -> backend -> frontend ->
  PostgreSQL+PostGIS portabel (diuji) -> uji kelayakan hasil staging -> kompilasi installer (Inno Setup).

  Prasyarat di mesin build: Windows 10/11 x64, Python 3.10+ (alat build saja), Node.js 20+ (npm), akses internet.
  Tidak butuh hak administrator. Inno Setup dipasang otomatis ke desktop\.tools bila belum ada.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File desktop\build.ps1
  powershell -ExecutionPolicy Bypass -File desktop\build.ps1 -Fast        # pakai ulang runtime & pgsql hasil build sebelumnya
#>
[CmdletBinding()]
param(
  [switch]$Fast,
  [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 3
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest jauh lebih cepat tanpa bar progres

$Desktop = $PSScriptRoot
$Repo    = Split-Path $Desktop -Parent
$Cache   = Join-Path $Desktop '.cache'
$Tools   = Join-Path $Desktop '.tools'
$Build   = Join-Path $Desktop 'build'
$Stage   = Join-Path $Build 'stage'
$Dist    = Join-Path $Desktop 'dist'

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Fail($msg) { throw $msg }

function Run($exe, [string[]]$arguments, [string]$cwd = $null) {
  if ($cwd) { Push-Location $cwd }
  try {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { Fail "Perintah gagal (kode $LASTEXITCODE): $exe $($arguments -join ' ')" }
  } finally { if ($cwd) { Pop-Location } }
}

# ---- versi ----
$initPy = Get-Content (Join-Path $Repo 'backend\app\desktop\__init__.py') -Raw
if ($initPy -notmatch 'APP_VERSION\s*=\s*"([^"]+)"') { Fail 'APP_VERSION tidak ditemukan di backend/app/desktop/__init__.py' }
$Version = $Matches[1]
Write-Host "Peta Toko $Version"

# ---- alat build ----
$HostPython = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $HostPython) { Fail 'Python tidak ditemukan di PATH (dibutuhkan sebagai alat build).' }
$Npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
if (-not $Npm) { Fail 'Node.js/npm tidak ditemukan di PATH (dibutuhkan untuk membangun antarmuka).' }

# ---- 1. unduhan terverifikasi ----
Step 'Unduh dan verifikasi komponen'
New-Item -ItemType Directory -Force $Cache, $Build | Out-Null
$sums = Get-Content (Join-Path $Desktop 'checksums.json') -Raw | ConvertFrom-Json
foreach ($prop in $sums.PSObject.Properties) {
  $name = $prop.Name; $url = $prop.Value.url; $want = $prop.Value.sha256
  $file = Join-Path $Cache $name
  if (-not (Test-Path $file)) {
    Write-Host "  mengunduh $name ..."
    Invoke-WebRequest -Uri $url -OutFile "$file.part" -UseBasicParsing
    Move-Item "$file.part" $file
  }
  $got = (Get-FileHash $file -Algorithm SHA256).Hash.ToLower()
  if ($got -ne $want) {
    Remove-Item $file -Force
    Fail "Checksum $name tidak cocok (didapat $got, seharusnya $want). Berkas dihapus; jalankan ulang. Bila hulu memang berganti versi, perbarui desktop\checksums.json."
  }
  Write-Host "  ok  $name"
}

# ---- 2. Inno Setup ----
$Iscc = Join-Path $Tools 'InnoSetup\ISCC.exe'
if (-not $SkipInstaller -and -not (Test-Path $Iscc)) {
  Step 'Memasang Inno Setup (per-pengguna, ke desktop\.tools)'
  $p = Start-Process -FilePath (Join-Path $Cache 'innosetup.exe') -Wait -PassThru -ArgumentList @(
    '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CURRENTUSER', '/SP-', "/DIR=`"$(Join-Path $Tools 'InnoSetup')`"")
  if ($p.ExitCode -ne 0 -or -not (Test-Path $Iscc)) { Fail "Pemasangan Inno Setup gagal (kode $($p.ExitCode))." }
}

# ---- 3. staging ----
Step 'Menyiapkan folder staging'
$keep = @()
if ($Fast -and (Test-Path (Join-Path $Stage 'runtime\python.exe')) -and (Test-Path (Join-Path $Stage 'pgsql\bin\postgres.exe'))) {
  Write-Host '  -Fast: runtime dan pgsql dipakai ulang'
  $keep = @('runtime', 'pgsql')
}
if (Test-Path $Stage) {
  Get-ChildItem $Stage -Force | Where-Object { $keep -notcontains $_.Name } | Remove-Item -Recurse -Force
}
New-Item -ItemType Directory -Force $Stage | Out-Null

# ---- 4. Python embeddable + dependensi ----
$Runtime = Join-Path $Stage 'runtime'
if ($keep -notcontains 'runtime') {
  Step 'Python embeddable + dependensi'
  Expand-Archive (Join-Path $Cache 'python-embed.zip') $Runtime -Force
  $pthFile = Get-ChildItem $Runtime -Filter 'python*._pth' | Select-Object -First 1
  if (-not $pthFile) { Fail 'python*._pth tidak ditemukan di Python embeddable.' }
  $stdlibZip = ($pthFile.BaseName) + '.zip'
  # ._pth: relatif terhadap folder runtime. '..\backend' membuat paket 'app' dapat di-import.
  Set-Content $pthFile.FullName -Encoding ascii -Value @($stdlibZip, '.', '..\backend', 'Lib\site-packages', 'import site')
  $site = Join-Path $Runtime 'Lib\site-packages'
  New-Item -ItemType Directory -Force $site | Out-Null
  # dipasang dari pip mesin build ke folder runtime (wheel cp312 win_amd64 saja; tanpa kompilasi)
  Run $HostPython @('-m', 'pip', 'install', '--disable-pip-version-check', '--no-warn-script-location',
    '--target', $site, '--platform', 'win_amd64', '--python-version', '3.12', '--implementation', 'cp',
    '--only-binary=:all:', '--upgrade', '-r', (Join-Path $Repo 'backend\requirements-desktop.txt'))
  # peluncur tanpa jendela konsol, dengan nama yang rapi di Task Manager
  Copy-Item (Join-Path $Runtime 'pythonw.exe') (Join-Path $Runtime 'PetaToko.exe') -Force
}

# ---- 5. backend ----
Step 'Menyalin backend'
$Backend = Join-Path $Stage 'backend'
New-Item -ItemType Directory -Force $Backend | Out-Null
& robocopy (Join-Path $Repo 'backend\app') (Join-Path $Backend 'app') /E /XD __pycache__ tests /XF '*.pyc' /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) { Fail "robocopy backend/app gagal ($LASTEXITCODE)" }
& robocopy (Join-Path $Repo 'backend\alembic') (Join-Path $Backend 'alembic') /E /XD __pycache__ /XF '*.pyc' /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) { Fail "robocopy backend/alembic gagal ($LASTEXITCODE)" }
Copy-Item (Join-Path $Repo 'backend\alembic.ini') $Backend -Force

# ---- 6. frontend ----
Step 'Membangun antarmuka (frontend)'
$Frontend = Join-Path $Repo 'frontend'
Run $Npm @('ci', '--no-audit', '--no-fund') $Frontend
# build produksi: alamat API relatif (satu asal). Pastikan tidak ada VITE_API_URL warisan yang ikut terpanggang.
Remove-Item Env:\VITE_API_URL -ErrorAction SilentlyContinue
Run $Npm @('run', 'build') $Frontend
$FrontendDist = Join-Path $Frontend 'dist'
if (-not (Test-Path (Join-Path $FrontendDist 'index.html'))) { Fail 'frontend/dist/index.html tidak ada setelah build.' }
if (Select-String -Path (Join-Path $FrontendDist 'assets\*.js') -Pattern 'localhost:8000' -Quiet) {
  Fail 'Bundel frontend masih memuat alamat localhost:8000; build produksi seharusnya memakai alamat relatif.'
}
New-Item -ItemType Directory -Force (Join-Path $Stage 'frontend') | Out-Null
Copy-Item $FrontendDist (Join-Path $Stage 'frontend\dist') -Recurse -Force

# ---- 7. PostgreSQL + PostGIS ----
if ($keep -notcontains 'pgsql') {
  Step 'PostgreSQL + PostGIS portabel'
  Run $HostPython @((Join-Path $Desktop 'tools\prepare_postgres.py'), '--pg-zip', (Join-Path $Cache 'postgresql.zip'),
    '--postgis-zip', (Join-Path $Cache 'postgis-bundle.zip'), '--out', (Join-Path $Stage 'pgsql'))
}
Step 'Uji kelayakan PostgreSQL + PostGIS (initdb, start, CREATE EXTENSION, stop)'
Run $HostPython @((Join-Path $Desktop 'tools\selftest_postgres.py'), '--pgsql', (Join-Path $Stage 'pgsql'),
  '--workdir', (Join-Path $Build 'selftest dir'))

# ---- 8. aset ----
Step 'Aset dan lisensi'
New-Item -ItemType Directory -Force (Join-Path $Stage 'assets') | Out-Null
Copy-Item (Join-Path $Desktop 'assets\petatoko.ico') (Join-Path $Stage 'assets') -Force
Copy-Item (Join-Path $Desktop 'NOTICE.txt') (Join-Path $Stage 'NOTICE.txt') -Force

# ---- 9. kompilasi bytecode + uji kelayakan hasil staging ----
Step 'Kompilasi bytecode dan uji impor'
$py = Join-Path $Runtime 'python.exe'
# pip di mesin build ikut membuat .pyc Python lain; buang agar installer tidak membengkak
Get-ChildItem (Join-Path $Runtime 'Lib\site-packages') -Recurse -File -Filter '*.pyc' |
  Where-Object { $_.Name -match '\.cpython-\d+\.pyc$' -and $_.Name -notmatch '\.cpython-312\.pyc$' } | Remove-Item -Force
Run $py @('-m', 'compileall', '-q', '-j', '0', (Join-Path $Runtime 'Lib\site-packages'), (Join-Path $Stage 'backend\app'))
# catatan: Windows PowerShell 5.1 menghapus tanda kutip ganda di argumen program native; pakai kutip tunggal di dalam Python
$probe = 'import app.main, app.workers.runner, app.desktop.launcher, app.desktop.setup, playwright, psycopg, lxml, PIL, pystray, geoalchemy2, alembic, openpyxl; print(''impor ok'')'
Run $py @('-c', $probe)

# ---- 10. installer ----
if ($SkipInstaller) { Write-Host "`nSelesai (installer dilewati). Staging: $Stage" -ForegroundColor Green; exit 0 }
Step 'Mengompilasi installer (Inno Setup, bisa beberapa menit)'
New-Item -ItemType Directory -Force $Dist | Out-Null
$isccArgs = @("/DAppVersion=$Version", "/DStageDir=$Stage", "/DOutDir=$Dist")
$signing = -not [string]::IsNullOrEmpty($env:PETATOKO_SIGN_PFX)
if ($signing) {
  # tanda tangan digital installer + uninstaller (lihat desktop\tools\sign.ps1). $f diganti Inno dengan path berkas.
  $signScript = Join-Path $Desktop 'tools\sign.ps1'
  $isccArgs += '/DSign=1'
  $isccArgs += ('/Spetasign=powershell -NoProfile -ExecutionPolicy Bypass -File "' + $signScript + '" -File $f')
  Write-Host 'Penandatanganan digital: AKTIF'
} else {
  Write-Host 'Penandatanganan digital: tidak dikonfigurasi (installer tanpa tanda tangan; set PETATOKO_SIGN_PFX untuk mengaktifkan)' -ForegroundColor Yellow
}
$isccArgs += (Join-Path $Desktop 'installer\PetaToko.iss')
Run $Iscc $isccArgs
$setup = Join-Path $Dist "PetaToko-Setup-$Version.exe"
if (-not (Test-Path $setup)) { Fail "Installer tidak terbentuk: $setup" }
if ($signing) {
  $sig = Get-AuthenticodeSignature $setup
  if (-not $sig.SignerCertificate) { Fail "Installer seharusnya ditandatangani tetapi tidak bertanda tangan: $setup" }
  Write-Host "Tanda tangan: $($sig.Status) | $($sig.SignerCertificate.Subject) | timestamp: $([bool]$sig.TimeStamperCertificate)" -ForegroundColor Green
}
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
"$hash  PetaToko-Setup-$Version.exe" | Set-Content "$setup.sha256" -Encoding ascii
$mb = [math]::Round((Get-Item $setup).Length / 1MB)
Write-Host "`nSELESAI: $setup ($mb MB)`nSHA256: $hash" -ForegroundColor Green
