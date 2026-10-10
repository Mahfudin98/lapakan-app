<#
.SYNOPSIS
  Uji instalasi nyata installer di folder terisolasi (path BER-SPASI), tanpa menyentuh data pengguna yang sebenarnya.

.DESCRIPTION
  1. Pasang senyap ke <Work>\Peta Toko  (data di <Work>\Data Saya)
  2. Periksa hasil setup database (berkas, database mati setelah setup)
  3. Jalankan peluncur (--background), tunggu /health, periksa API + antarmuka
  4. Hentikan lewat --stop, pastikan tidak ada proses tersisa
  5. Jalankan lagi (data lama dipakai), hentikan
  6. Pasang ulang di atas instalasi lama (pembaruan): data harus utuh
  7. Uninstall tanpa hapus data (data tetap), lalu pasang+uninstall dengan /DELETEDATA
  Keluar dengan kode != 0 bila ada pemeriksaan yang gagal.
#>
param(
  [Parameter(Mandatory)] [string]$Installer,
  [string]$Work = '',
  [int]$HealthTimeoutSec = 180,
  [switch]$UnicodeData   # folder data berhuruf Sirilik (menguji path di luar codepage ANSI)
)
$ErrorActionPreference = 'Stop'
if (-not $Work) { $Work = Join-Path $PSScriptRoot '..\build\install test' }  # $PSScriptRoot kosong di nilai bawaan parameter (PS 5.1)
$Work = [System.IO.Path]::GetFullPath($Work)
$AppDir = Join-Path $Work 'Peta Toko'
$dataName = 'Data Saya'
if ($UnicodeData) { $dataName = [string]::Join('', [char[]](0x414,0x430,0x43D,0x43D,0x44B,0x435)) + ' Saya' }  # nama folder berhuruf Sirilik + " Saya"
$DataDir = Join-Path $Work $dataName
$Py = Join-Path $AppDir 'runtime\python.exe'
$Launcher = Join-Path $AppDir 'runtime\PetaToko.exe'
$failures = New-Object System.Collections.Generic.List[string]

function Check($name, [bool]$ok, $detail = '') {
  if ($ok) { Write-Host "  [OK]    $name" -ForegroundColor Green }
  else { Write-Host "  [GAGAL] $name $detail" -ForegroundColor Red; $failures.Add($name) | Out-Null }
}
function Step($m) { Write-Host "`n== $m" -ForegroundColor Cyan }

function Install-App([string[]]$extra = @()) {
  $log = Join-Path $Work 'install.log'
  $iargs = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', "/LOG=`"$log`"", "/DIR=`"$AppDir`"", "/DATADIR=`"$DataDir`"", '/TASKS=') + $extra
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $p = Start-Process -FilePath $Installer -ArgumentList $iargs -Wait -PassThru
  Write-Host ("  installer selesai dalam {0:n0} dtk, kode {1}" -f $sw.Elapsed.TotalSeconds, $p.ExitCode)
  return $p.ExitCode
}
function Uninstall-App([string[]]$extra = @()) {
  $unins = Get-ChildItem $AppDir -Filter 'unins*.exe' | Select-Object -First 1
  if (-not $unins) { throw 'uninstaller tidak ditemukan' }
  $p = Start-Process -FilePath $unins.FullName -ArgumentList (@('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') + $extra) -Wait -PassThru
  return $p.ExitCode
}
function Get-Cfg { Get-Content (Join-Path $DataDir 'config.json') -Raw | ConvertFrom-Json }
function Start-App {
  $cfgBefore = $null
  $proc = Start-Process -FilePath $Launcher -ArgumentList @('-m', 'app.desktop.launcher', '--background') -WorkingDirectory (Join-Path $AppDir 'backend') -PassThru
  $deadline = (Get-Date).AddSeconds($HealthTimeoutSec)
  $health = $null
  while ((Get-Date) -lt $deadline -and -not $health) {
    Start-Sleep -Seconds 2
    if (Test-Path (Join-Path $DataDir 'config.json')) {
      $port = (Get-Cfg).app_port
      try { $health = Invoke-RestMethod "http://127.0.0.1:$port/health" -TimeoutSec 3 } catch { }
    }
  }
  return @{ Proc = $proc; Health = $health }
}
function Stop-App {
  $p = Start-Process -FilePath $Py -ArgumentList @('-m', 'app.desktop.launcher', '--stop') -WorkingDirectory (Join-Path $AppDir 'backend') -Wait -PassThru -WindowStyle Hidden
  return $p.ExitCode
}
function Count-Proc([string]$pattern) {
  @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.ToLower().StartsWith($Work.ToLower()) -and $_.CommandLine -match $pattern }).Count
}
function Leftover-Processes {
  $root = $Work.ToLower()
  Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.ToLower().StartsWith($root) } | Select-Object ProcessId, Name
}

if (Test-Path $Work) {
  # sisa uji sebelumnya: hentikan proses bila ada, lalu bersihkan
  Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.ToLower().StartsWith($Work.ToLower()) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Start-Sleep 2
  Remove-Item $Work -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force $Work | Out-Null

Step '1. Pemasangan senyap (path berspasi)'
$code = Install-App
Check 'installer keluar dengan kode 0' ($code -eq 0) "kode=$code"
Check 'file aplikasi terpasang' ((Test-Path $Py) -and (Test-Path $Launcher) -and (Test-Path (Join-Path $AppDir 'pgsql\bin\postgres.exe')) -and (Test-Path (Join-Path $AppDir 'frontend\dist\index.html')))
Check 'data-location.txt menunjuk folder data' ((Get-Content (Join-Path $AppDir 'data-location.txt') -Raw).Trim() -eq $DataDir)

Step '2. Hasil setup database saat instalasi'
Check 'setup.json (selesai)' ((Test-Path (Join-Path $DataDir 'setup.json')) -and ((Get-Content (Join-Path $DataDir 'setup.json') -Raw | ConvertFrom-Json).completed -eq $true))
Check 'config.json ada' (Test-Path (Join-Path $DataDir 'config.json'))
Check 'folder pgdata ada' (Test-Path (Join-Path $DataDir 'pgdata\PG_VERSION'))
$log = Get-Content (Join-Path $DataDir 'logs\setup.log') -Raw -ErrorAction SilentlyContinue
Check 'log setup berakhir DONE' ($log -match 'DONE')
Check 'tidak ada ERROR di log setup' ($log -notmatch 'ERROR\|')
Check 'database dimatikan setelah setup' (-not (Test-Path (Join-Path $DataDir 'pgdata\postmaster.pid')))
Check 'tidak ada proses tersisa' (@(Leftover-Processes).Count -eq 0) ((Leftover-Processes | Out-String))

Step '3. Menjalankan aplikasi'
$app = Start-App
Check 'server sehat (/health)' ($null -ne $app.Health -and $app.Health.status -eq 'ok')
if ($app.Health) { Write-Host "      PostGIS: $($app.Health.postgis)" }
$cfg = Get-Cfg
$base = "http://127.0.0.1:$($cfg.app_port)"
try {
  $prov = Invoke-RestMethod "$base/regions?level=1&limit=100"
  Check 'wilayah: 34 provinsi' ($prov.Count -eq 34) "dapat $($prov.Count)"
  $desa = Invoke-RestMethod "$base/regions?level=4&parent=3273180"
  Check 'wilayah: desa Andir tersedia (data lengkap sampai desa)' ($desa.Count -eq 6) "dapat $($desa.Count)"
  $cats = Invoke-RestMethod "$base/categories"
  Check 'kategori preset terisi' ($cats.Count -ge 20) "dapat $($cats.Count)"
  $html = Invoke-WebRequest "$base/" -UseBasicParsing
  Check 'antarmuka dilayani dari alamat yang sama' ($html.StatusCode -eq 200 -and $html.Content -match '<div id="root">')
  $places = Invoke-RestMethod "$base/places?page_size=1"
  Check '/places berjalan di database baru (kosong)' ($places.total -eq 0)
} catch { Check 'pemeriksaan API' $false $_.Exception.Message }
Check 'proses launcher berjalan' (-not $app.Proc.HasExited)
$procs = (Leftover-Processes | Select-Object -ExpandProperty Name | Sort-Object -Unique) -join ', '
Write-Host "      proses: $procs"
Check 'worker berjalan' (@(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'app.workers.runner' -and $_.ExecutablePath -and $_.ExecutablePath.ToLower().StartsWith($Work.ToLower()) }).Count -ge 1)
Check 'hanya mendengarkan 127.0.0.1 (bukan seluruh jaringan)' (@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in @($cfg.pg_port, $cfg.app_port) -and $_.LocalAddress -ne '127.0.0.1' }).Count -eq 0)

Step '4. Menghentikan aplikasi (--stop)'
$sw = [Diagnostics.Stopwatch]::StartNew()
$stopCode = Stop-App
Start-Sleep 2
Write-Host ("      berhenti dalam {0:n0} dtk" -f $sw.Elapsed.TotalSeconds)
Check '--stop berhasil' ($stopCode -eq 0)
Check 'tidak ada proses tersisa setelah --stop' (@(Leftover-Processes).Count -eq 0) ((Leftover-Processes | Out-String))
Check 'port database & server bebas' (-not (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in @($cfg.pg_port, $cfg.app_port) }))

Step '5. Menjalankan lagi (data yang sama)'
$app2 = Start-App
Check 'server sehat lagi' ($null -ne $app2.Health -and $app2.Health.status -eq 'ok')
$null = Stop-App
Start-Sleep 2

Step '5b. Peluncur dimatikan paksa (kill), lalu dijalankan lagi'
$app3 = Start-App
$cfgK = Get-Cfg
Stop-Process -Id $app3.Proc.Id -Force
Start-Sleep 3
Check 'kondisi uji: API & worker yatim masih hidup' ((Count-Proc 'uvicorn app.main') -eq 1 -and (Count-Proc 'app.workers.runner') -eq 1)
$app4 = Start-App
Check 'sehat setelah pemulihan' ($null -ne $app4.Health -and $app4.Health.status -eq 'ok')
Check 'tepat 1 API dan 1 worker (yatim dimatikan)' ((Count-Proc 'uvicorn app.main') -eq 1 -and (Count-Proc 'app.workers.runner') -eq 1)
Check 'port tidak bergeser' ((Get-Cfg).app_port -eq $cfgK.app_port -and (Get-Cfg).pg_port -eq $cfgK.pg_port)
$null = Stop-App
Start-Sleep 2

Step '5c. Port bentrok: port milik aplikasi dipakai program lain'
$cfgP = Get-Cfg
$l1 = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, [int]$cfgP.app_port); $l1.Start()
$l2 = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, [int]$cfgP.pg_port); $l2.Start()
try {
  $app5 = Start-App
  $cfgQ = Get-Cfg
  Check 'port pindah otomatis' (($cfgQ.app_port -ne $cfgP.app_port) -and ($cfgQ.pg_port -ne $cfgP.pg_port)) "app $($cfgP.app_port)->$($cfgQ.app_port), pg $($cfgP.pg_port)->$($cfgQ.pg_port)"
  Check 'sehat di port baru' ($null -ne $app5.Health -and $app5.Health.status -eq 'ok')
  $null = Stop-App
} finally { $l1.Stop(); $l2.Stop() }
Start-Sleep 2

Step '5d. Penyembuhan otomatis: setup belum lengkap (database & konfigurasi hilang)'
$null = Stop-App
Start-Sleep 1
Remove-Item -LiteralPath (Join-Path $DataDir 'setup.json') -Force
Remove-Item -LiteralPath (Join-Path $DataDir 'config.json') -Force
Remove-Item -LiteralPath (Join-Path $DataDir 'pgdata') -Recurse -Force
$app6 = Start-App
Check 'aplikasi pulih dan sehat' ($null -ne $app6.Health -and $app6.Health.status -eq 'ok')
Check 'setup.json dibuat ulang' (Test-Path -LiteralPath (Join-Path $DataDir 'setup.json'))
$prov2 = try { Invoke-RestMethod ("http://127.0.0.1:{0}/regions?level=1&limit=100" -f (Get-Cfg).app_port) } catch { $null }
Check 'data wilayah terisi ulang' ($prov2 -and $prov2.Count -eq 34)
$null = Stop-App
Start-Sleep 2

Step '6. Pembaruan: pasang ulang di atas instalasi lama'
# tandai data supaya terlihat apakah selamat
$marker = Join-Path $DataDir 'MARKER-JANGAN-HILANG.txt'
'ada' | Set-Content $marker
$cfgBefore = Get-Content (Join-Path $DataDir 'config.json') -Raw
$code = Install-App
Check 'pemasangan ulang kode 0' ($code -eq 0) "kode=$code"
Check 'data lama utuh' ((Test-Path $marker) -and ((Get-Content (Join-Path $DataDir 'config.json') -Raw) -eq $cfgBefore))
$app3 = Start-App
Check 'sehat setelah pembaruan' ($null -ne $app3.Health -and $app3.Health.status -eq 'ok')
$null = Stop-App
Start-Sleep 2

Step '7. Uninstall'
$code = Uninstall-App
Start-Sleep 2
Check 'uninstall kode 0' ($code -eq 0) "kode=$code"
Check 'file program dihapus' (-not (Test-Path $Py))
Check 'data dipertahankan (secara bawaan)' (Test-Path $marker)
$code = Install-App
$code2 = Uninstall-App @('/DELETEDATA')
Start-Sleep 2
Check 'uninstall /DELETEDATA menghapus data' (-not (Test-Path $DataDir)) "kode=$code2"
Check 'tidak ada proses tersisa di akhir' (@(Leftover-Processes).Count -eq 0)

Write-Host ''
if ($failures.Count -eq 0) { Write-Host 'SEMUA PEMERIKSAAN LULUS' -ForegroundColor Green; exit 0 }
Write-Host ("GAGAL: " + ($failures -join '; ')) -ForegroundColor Red
exit 1
