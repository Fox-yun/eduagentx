#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Initialize production secrets and optionally self-signed TLS certificates.
.DESCRIPTION
    Generates random secrets for APP_SECRET_KEY, POSTGRES_PASSWORD, REDIS_PASSWORD,
    MINIO_ACCESS_KEY, MINIO_SECRET_KEY, EMAIL_OUTBOX_ENCRYPTION_KEY, and writes
    them into .env.docker with correctly URL-encoded connection strings.
    Optionally generates a self-signed TLS certificate for local testing.
.PARAMETER GenerateCert
    Generate a self-signed TLS certificate in nginx/certs/ (for testing only).
.PARAMETER Force
    Overwrite existing .env.docker if it already contains generated values.
#>
#requires -Version 7.0

[CmdletBinding()]
param(
    [switch]$GenerateCert,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$EnvFile = ".env.docker"
$ExampleFile = ".env.docker.example"

# ── Check if already initialized ──
if ((Test-Path $EnvFile) -and -not $Force) {
    $content = Get-Content $EnvFile -Raw
    if ($content -notmatch "CHANGE_ME_") {
        Write-Host ".env.docker already contains non-placeholder values." -ForegroundColor Yellow
        Write-Host "Use -Force to overwrite." -ForegroundColor Yellow
        exit 0
    }
}

if (-not (Test-Path $ExampleFile)) {
    Write-Host "ERROR: $ExampleFile not found." -ForegroundColor Red
    exit 1
}

# ── Generate secrets ──
Write-Host "Generating random secrets..."

# Use Python for cross-platform secret generation
$GenerateSecret = @'
import secrets, string, sys

def gen_url_safe(n=64):
    return secrets.token_urlsafe(n)

def gen_alnum(n=32, charset=None):
    if charset is None:
        charset = string.ascii_letters + string.digits
    return "".join(secrets.choice(charset) for _ in range(n))

def url_encode(s):
    from urllib.parse import quote
    return quote(s, safe="")

app_secret = gen_url_safe(64)
pg_password = gen_alnum(32)
redis_password = gen_alnum(32)
minio_access = gen_alnum(20, string.ascii_lowercase + string.digits)
minio_secret = gen_alnum(40)
outbox_key = gen_url_safe(32)

# URL-encode passwords for connection strings
pg_password_enc = url_encode(pg_password)
redis_password_enc = url_encode(redis_password)

# Output as key=value lines
lines = [
    f"__APP_SECRET_KEY__={app_secret}",
    f"__POSTGRES_PASSWORD__={pg_password}",
    f"__POSTGRES_PASSWORD_ENC__={pg_password_enc}",
    f"__REDIS_PASSWORD__={redis_password}",
    f"__REDIS_PASSWORD_ENC__={redis_password_enc}",
    f"__MINIO_ACCESS_KEY__={minio_access}",
    f"__MINIO_SECRET_KEY__={minio_secret}",
    f"__OUTBOX_KEY__={outbox_key}",
]
print("\n".join(lines))
'@

# Check if Python is available before attempting to use it.
# When $ErrorActionPreference is "Stop", calling a non-existent command
# may terminate the script before reaching the fallback branch.
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCmd) {
    $secretsOutput = & $pythonCmd.Source -c $GenerateSecret
}

if (-not $pythonCmd -or $LASTEXITCODE -ne 0) {
    # Fallback: use .NET RNG
    Write-Host "Python not available or failed, using .NET fallback..."
    $secrets = @{}
    $bytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()

    $rng.GetBytes($bytes)
    $secrets["APP_SECRET_KEY"] = [Convert]::ToBase64String($bytes)

    $rng.GetBytes($bytes)
    $secrets["POSTGRES_PASSWORD"] = [Convert]::ToBase64String($bytes).TrimEnd('=') -replace '[+/]', ''
    $secrets["POSTGRES_PASSWORD_ENC"] = [uri]::EscapeDataString($secrets["POSTGRES_PASSWORD"])

    $rng.GetBytes($bytes)
    $secrets["REDIS_PASSWORD"] = [Convert]::ToBase64String($bytes).TrimEnd('=') -replace '[+/]', ''
    $secrets["REDIS_PASSWORD_ENC"] = [uri]::EscapeDataString($secrets["REDIS_PASSWORD"])

    $rng.GetBytes($bytes)
    $secrets["MINIO_ACCESS_KEY"] = ([Convert]::ToBase64String($bytes).TrimEnd('=') -replace '[+/]', '').ToLower().Substring(0, 20)

    $rng.GetBytes($bytes)
    $secrets["MINIO_SECRET_KEY"] = [Convert]::ToBase64String($bytes).TrimEnd('=')

    $rng.GetBytes($bytes)
    $secrets["OUTBOX_KEY"] = [Convert]::ToBase64String($bytes)

    $secretsOutput = $secrets.GetEnumerator() | ForEach-Object { "__$($_.Key)__=$($_.Value)" }
}

# Parse secrets
$secretMap = @{}
foreach ($line in $secretsOutput -split "`n") {
    $line = $line.Trim()
    if ($line -match "^__(.+?)__=(.*)$") {
        $secretMap[$matches[1]] = $matches[2]
    }
}

# ── Generate .env.docker from template ──
Write-Host "Writing $EnvFile..."

$template = Get-Content $ExampleFile -Raw

# Replace placeholders
$template = $template -replace "CHANGE_ME_TO_64_PLUS_RANDOM_CHARACTERS", $secretMap["APP_SECRET_KEY"]
$template = $template -replace "CHANGE_ME_TO_STRONG_PASSWORD", $secretMap["POSTGRES_PASSWORD"]
$template = $template -replace "CHANGE_ME_TO_REDIS_PASSWORD", $secretMap["REDIS_PASSWORD"]
$template = $template -replace "CHANGE_ME_TO_STRONG_ACCESS_KEY", $secretMap["MINIO_ACCESS_KEY"]
$template = $template -replace "CHANGE_ME_TO_STRONG_SECRET_KEY", $secretMap["MINIO_SECRET_KEY"]
$template = $template -replace "CHANGE_ME_TO_32_PLUS_RANDOM_CHARACTERS", $secretMap["OUTBOX_KEY"]

# Update connection URLs with URL-encoded passwords
$pgPasswordEnc = $secretMap["POSTGRES_PASSWORD_ENC"]
$redisPasswordEnc = $secretMap["REDIS_PASSWORD_ENC"]
$postgresUser = "eduagentx"
$template = $template -replace "postgresql\+asyncpg://eduagentx:CHANGE_ME_TO_STRONG_PASSWORD@", "postgresql+asyncpg://${postgresUser}:${pgPasswordEnc}@"
$template = $template -replace "redis://:CHANGE_ME_TO_REDIS_PASSWORD@", "redis://:${redisPasswordEnc}@"

# Set production environment
$template = $template -replace "APP_ENV=development", "APP_ENV=production"
$template = $template -replace "COOKIE_SECURE=false", "COOKIE_SECURE=true"

Set-Content -Path $EnvFile -Value $template -Encoding UTF8

# Restrict file permissions (best effort on Windows)
try {
    icacls $EnvFile /inheritance:r /grant:r "$env:USERNAME:(R,W)" 2>$null | Out-Null
} catch {
    Write-Host "Warning: Could not restrict file permissions." -ForegroundColor Yellow
}

Write-Host "Secrets written to $EnvFile" -ForegroundColor Green

# ── Generate self-signed certificate ──
if ($GenerateCert) {
    $certsDir = "nginx/certs"
    if (-not (Test-Path $certsDir)) {
        New-Item -ItemType Directory -Path $certsDir -Force | Out-Null
    }

    Write-Host "Generating self-signed TLS certificate..."

    $certSubject = "CN=eduagentx.local"
    $certPath = Join-Path $certsDir "fullchain.pem"
    $keyPath = Join-Path $certsDir "privkey.pem"

    # Use openssl if available
    $openssl = Get-Command openssl -ErrorAction SilentlyContinue
    if ($openssl) {
        & openssl req -x509 -nodes -days 365 `
            -newkey rsa:2048 `
            -keyout $keyPath `
            -out $certPath `
            -subj "/C=CN/ST=Beijing/L=Beijing/O=EduAgentX/CN=eduagentx.local" `
            -addext "subjectAltName=DNS:eduagentx.local,DNS:localhost,IP:127.0.0.1" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Self-signed certificate generated (openssl with SAN)." -ForegroundColor Green
        }
    } else {
        # PowerShell .NET certificate generation
        Write-Host "openssl not found, using PowerShell .NET fallback..."
        $rsa = [System.Security.Cryptography.RSA]::Create(2048)
        $req = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
            [System.Security.Cryptography.X500DistinguishedName]::new($certSubject),
            $rsa,
            [System.Security.Cryptography.HashAlgorithmName]::SHA256,
            [System.Security.Cryptography.RSASignaturePadding]::Pkcs1
        )
        $req.CertificateExtensions.Add(
            [System.Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new(
                [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::DigitalSignature -bor
                [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::KeyEncipherment,
                $true
            )
        )
        $req.CertificateExtensions.Add(
            [System.Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new($false, $false, 0, $true)
        )
        $req.CertificateExtensions.Add(
            [System.Security.Cryptography.X509Certificates.X509SubjectKeyIdentifierExtension]::new($req.PublicKey, $false)
        )
        # Add Subject Alternative Name (SAN) for modern TLS clients
        $sanBuilder = [System.Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new()
        $sanBuilder.AddDnsName("eduagentx.local")
        $sanBuilder.AddDnsName("localhost")
        $sanBuilder.AddIpAddress([System.Net.IPAddress]::Loopback)
        $req.CertificateExtensions.Add($sanBuilder.Build())

        $notBefore = [DateTimeOffset]::UtcNow.AddDays(-1)
        $notAfter = [DateTimeOffset]::UtcNow.AddDays(365)
        $cert = $req.CreateSelfSigned($notBefore, $notAfter)

        # Export cert (fullchain)
        $certPem = "-----BEGIN CERTIFICATE-----`n"
        $certPem += [Convert]::ToBase64String($cert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert), [Base64FormattingOptions]::InsertLineBreaks)
        $certPem += "`n-----END CERTIFICATE-----`n"
        Set-Content -Path $certPath -Value $certPem -Encoding ASCII

        # Export private key
        $keyBytes = $rsa.ExportRSAPrivateKey()
        $keyPem = "-----BEGIN RSA PRIVATE KEY-----`n"
        $keyPem += [Convert]::ToBase64String($keyBytes, [Base64FormattingOptions]::InsertLineBreaks)
        $keyPem += "`n-----END RSA PRIVATE KEY-----`n"
        Set-Content -Path $keyPath -Value $keyPem -Encoding ASCII

        Write-Host "Self-signed certificate generated (.NET)." -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "WARNING: Self-signed certificates are for testing only." -ForegroundColor Yellow
    Write-Host "For production, use a trusted CA-signed certificate." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "The Release desktop client does not skip certificate validation." -ForegroundColor Cyan
    Write-Host "To use HTTPS with the desktop client on this machine, import the cert:" -ForegroundColor Cyan
    Write-Host "  .\import-cert.ps1              # Import into Trusted Root" -ForegroundColor White
    Write-Host "  .\import-cert.ps1 -Remove      # Remove from Trusted Root" -ForegroundColor White
}

Write-Host ""
Write-Host "Initialization complete." -ForegroundColor Green
Write-Host "Next steps:"
Write-Host "  .\start-stack.ps1 -Mode production    (with HTTPS)"
Write-Host "  .\start-stack.ps1 -Mode demo          (local HTTP, no certs needed)"
