<#
.SYNOPSIS
  Menandatangani berkas .exe dengan Authenticode memakai sertifikat code-signing (.pfx) dari variabel lingkungan.

.DESCRIPTION
  Dipanggil oleh Inno Setup (SignTool) untuk installer dan uninstaller-nya, dan oleh build.ps1.
  Variabel lingkungan:
    PETATOKO_SIGN_PFX        path berkas .pfx            (tanpa ini: dilewati, kode keluar 0)
    PETATOKO_SIGN_PASSWORD   kata sandi .pfx
    PETATOKO_SIGN_TIMESTAMP  server timestamp RFC 3161   (bawaan: http://timestamp.digicert.com)

  Timestamp penting: tanda tangan tetap sah setelah sertifikat kedaluwarsa.
  Hanya Windows PowerShell bawaan yang dibutuhkan (tanpa Windows SDK / signtool.exe).
#>
param([Parameter(Mandatory)][string]$File)

$ErrorActionPreference = 'Stop'
$pfx = $env:PETATOKO_SIGN_PFX
if ([string]::IsNullOrEmpty($pfx)) { Write-Host "[sign] sertifikat tidak dikonfigurasi; dilewati: $File"; exit 0 }
if (-not (Test-Path -LiteralPath $pfx)) { Write-Error "[sign] berkas sertifikat tidak ada: $pfx"; exit 1 }

$secure = if ($env:PETATOKO_SIGN_PASSWORD) { ConvertTo-SecureString $env:PETATOKO_SIGN_PASSWORD -AsPlainText -Force } else { New-Object System.Security.SecureString }
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($pfx, $secure)
if (-not $cert.HasPrivateKey) { Write-Error '[sign] sertifikat tidak memuat kunci privat'; exit 1 }
$stamp = if ($env:PETATOKO_SIGN_TIMESTAMP) { $env:PETATOKO_SIGN_TIMESTAMP } else { 'http://timestamp.digicert.com' }

$last = $null
foreach ($attempt in 1..4) {   # server timestamp kadang sibuk
  try {
    $r = Set-AuthenticodeSignature -FilePath $File -Certificate $cert -HashAlgorithm SHA256 -TimestampServer $stamp
    # Valid = rantai tepercaya. UnknownError dapat berarti akar tidak tepercaya (mis. sertifikat uji) - tanda tangan tetap terpasang.
    if ($r.SignerCertificate -and $r.Status -notin @('NotSigned', 'HashMismatch')) {
      if (-not $r.TimeStamperCertificate) { throw 'timestamp tidak terpasang' }
      Write-Host "[sign] OK ($($r.Status)): $File  <- $($cert.Subject)"
      exit 0
    }
    $last = "status $($r.Status): $($r.StatusMessage)"
  } catch { $last = $_.Exception.Message }
  Start-Sleep -Seconds (2 * $attempt)
}
Write-Error "[sign] GAGAL menandatangani $File : $last"
exit 1
