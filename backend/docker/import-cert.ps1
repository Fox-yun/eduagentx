#requires -Version 7.0
<#
.SYNOPSIS
    Import or remove the EduAgentX self-signed TLS certificate from the Windows Trusted Root store.
.DESCRIPTION
    The Release desktop client does not skip certificate validation.
    For single-machine demo with self-signed certs, this script imports the
    generated certificate into the CurrentUser\Root store so that the desktop
    client can connect to https://127.0.0.1 without certificate errors.
.PARAMETER Remove
    Remove the previously imported certificate from the Trusted Root store.
.EXAMPLE
    .\import-cert.ps1              # Import certificate
    .\import-cert.ps1 -Remove      # Remove certificate
#>

[CmdletBinding()]
param(
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$CertPath = Join-Path $PSScriptRoot "nginx\certs\fullchain.pem"
$CertThumbprintFile = Join-Path $PSScriptRoot "nginx\certs\.imported-thumbprint"

# ── Remove mode ──
if ($Remove) {
    if (Test-Path -LiteralPath $CertThumbprintFile) {
        $thumbprint = Get-Content -LiteralPath $CertThumbprintFile -Raw
        $thumbprint = $thumbprint.Trim()

        $cert = Get-Item -LiteralPath "Cert:\CurrentUser\Root\$thumbprint" -ErrorAction SilentlyContinue
        if ($cert) {
            Remove-Item -LiteralPath "Cert:\CurrentUser\Root\$thumbprint" -Force
            Write-Host "Removed certificate ($thumbprint) from Trusted Root store." -ForegroundColor Green
        } else {
            Write-Host "Certificate ($thumbprint) not found in Trusted Root store — already removed." -ForegroundColor Yellow
        }
        Remove-Item -LiteralPath $CertThumbprintFile -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "No imported certificate record found. Nothing to remove." -ForegroundColor Yellow

        # Try to find and remove by subject as a fallback
        $certs = Get-ChildItem -Path "Cert:\CurrentUser\Root" | Where-Object {
            $_.Subject -match "eduagentx" -or $_.Subject -match "EduAgentX"
        }
        foreach ($cert in $certs) {
            Remove-Item -LiteralPath "Cert:\CurrentUser\Root\$($cert.Thumbprint)" -Force
            Write-Host "Removed certificate by subject match: $($cert.Thumbprint)" -ForegroundColor Green
        }
    }
    exit 0
}

# ── Import mode ──
if (-not (Test-Path -LiteralPath $CertPath -PathType Leaf)) {
    Write-Host "ERROR: Certificate not found at $CertPath" -ForegroundColor Red
    Write-Host "Run init-production.ps1 -GenerateCert first to generate the self-signed certificate." -ForegroundColor Red
    exit 1
}

# Load the certificate
$certBytes = [System.IO.File]::ReadAllBytes($CertPath)
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($certBytes)

# Check if already trusted
$existing = Get-ChildItem -Path "Cert:\CurrentUser\Root" | Where-Object {
    $_.Thumbprint -eq $cert.Thumbprint
}

if ($existing) {
    Write-Host "Certificate is already in the Trusted Root store (thumbprint: $($cert.Thumbprint))." -ForegroundColor Yellow
    exit 0
}

# Import into CurrentUser\Root (does not require admin)
$store = New-Object System.Security.Cryptography.X509Certificates.X509Store(
    [System.Security.Cryptography.X509Certificates.StoreName]::Root,
    [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
)
$store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
$store.Add($cert)
$store.Close()

# Save thumbprint for later removal
$cert.Thumbprint | Set-Content -LiteralPath $CertThumbprintFile -Encoding ASCII

Write-Host "Certificate imported into Trusted Root store." -ForegroundColor Green
Write-Host "  Subject: $($cert.Subject)" -ForegroundColor Cyan
Write-Host "  Thumbprint: $($cert.Thumbprint)" -ForegroundColor Cyan
Write-Host ""
Write-Host "The EduAgentX desktop client can now connect to https://127.0.0.1 without certificate errors." -ForegroundColor Green
Write-Host "To remove later: .\import-cert.ps1 -Remove" -ForegroundColor DarkGray
