#requires -Version 7.0

[CmdletBinding()]
param(
    [ValidateSet("production", "demo")]
    [string]$Mode = "demo"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$EnvFile = ".env.docker"

if (-not (Test-Path $EnvFile)) {
    Write-Host "ERROR: $EnvFile not found. Run init-production.ps1 first to generate secrets." -ForegroundColor Red
    exit 1
}

$ComposeArgs = @("--env-file", $EnvFile, "-f", "docker-compose.yml")

if ($Mode -eq "production") {
    # Verify TLS certs exist
    if (-not (Test-Path "nginx/certs/fullchain.pem") -or -not (Test-Path "nginx/certs/privkey.pem")) {
        Write-Host "ERROR: TLS certificates not found in nginx/certs/." -ForegroundColor Red
        Write-Host "Run init-production.ps1 to generate self-signed certs, or place real certs manually." -ForegroundColor Red
        exit 1
    }
    $ComposeArgs += "-f", "docker-compose.production.yml"
} else {
    $ComposeArgs += "-f", "docker-compose.demo.yml"
    # Enable demo profile to start Mailpit (test email service) in demo mode
    $ComposeArgs += "--profile", "demo"
}

Write-Host "Starting in $Mode mode..."

# ── Start infrastructure ──
if ($Mode -eq "demo") {
    Write-Host "Starting PostgreSQL, Redis, MinIO, and Mailpit..."
    docker compose @ComposeArgs up -d postgres redis minio mailpit
} else {
    Write-Host "Starting PostgreSQL, Redis, and MinIO..."
    docker compose @ComposeArgs up -d postgres redis minio
}

if ($LASTEXITCODE -ne 0) {
    throw "Failed to start infrastructure services."
}

# ── Build images ──
Write-Host "Building application images..."
docker compose @ComposeArgs build `
    migrate `
    backend `
    celery-worker `
    celery-beat `
    outbox-publisher `
    frontend

if ($LASTEXITCODE -ne 0) {
    throw "Docker image build failed."
}

# ── Run migrations ──
Write-Host "Running database migrations..."
docker compose @ComposeArgs up migrate

if ($LASTEXITCODE -ne 0) {
    throw "Database migration failed."
}

# ── Start runtime services ──
Write-Host "Starting runtime services..."
docker compose @ComposeArgs up -d `
    backend `
    celery-worker `
    celery-beat `
    outbox-publisher `
    frontend

if ($LASTEXITCODE -ne 0) {
    throw "Failed to start runtime services."
}

if ($Mode -eq "production") {
    Write-Host "Starting Nginx (HTTPS)..."
    docker compose @ComposeArgs up -d nginx

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to start Nginx."
    }
}

# ── Wait for backend readiness ──
Write-Host "Waiting for backend readiness..."

$ready = $false

for ($attempt = 1; $attempt -le 30; $attempt++) {
    try {
        if ($Mode -eq "production") {
            $response = Invoke-RestMethod `
                -Uri "https://127.0.0.1/health/ready" `
                -TimeoutSec 3 `
                -SkipCertificateCheck
        } else {
            $response = Invoke-RestMethod `
                -Uri "http://127.0.0.1:8000/health/ready" `
                -TimeoutSec 3
        }

        if ($response.status -eq "ready") {
            $ready = $true
            break
        }
    }
    catch {
        Start-Sleep -Seconds 2
    }
}

if (-not $ready) {
    docker compose @ComposeArgs logs --tail=200 backend
    throw "Backend did not become ready."
}

# ── Wait for frontend / nginx health ──
Write-Host "Waiting for frontend health..."

$frontendReady = $false

for ($attempt = 1; $attempt -le 15; $attempt++) {
    try {
        if ($Mode -eq "production") {
            Invoke-WebRequest `
                -Uri "https://127.0.0.1/health" `
                -TimeoutSec 3 `
                -UseBasicParsing `
                -SkipCertificateCheck |
                Out-Null
        } else {
            Invoke-WebRequest `
                -Uri "http://127.0.0.1:8081/health" `
                -TimeoutSec 3 `
                -UseBasicParsing |
                Out-Null
        }

        $frontendReady = $true
        break
    }
    catch {
        Start-Sleep -Seconds 2
    }
}

if (-not $frontendReady) {
    docker compose @ComposeArgs logs --tail=200 frontend
    throw "Frontend did not become healthy."
}

Write-Host ""
Write-Host "Full stack started successfully in $Mode mode."

if ($Mode -eq "production") {
    Write-Host "Frontend: https://127.0.0.1 (or your domain)"
    Write-Host "Backend API: https://127.0.0.1/api/"
    Write-Host "Health: https://127.0.0.1/health/ready"
} else {
    Write-Host "Frontend:  http://127.0.0.1:8081"
    Write-Host "Backend:  http://127.0.0.1:8000"
    Write-Host "Mailpit:  http://127.0.0.1:8025"
    Write-Host "MinIO:    http://127.0.0.1:9001 (console)"
}
