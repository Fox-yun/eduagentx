$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

Write-Host "Starting PostgreSQL and Redis..."
docker compose up -d postgres redis

if ($LASTEXITCODE -ne 0) {
    throw "Failed to start PostgreSQL or Redis."
}

Write-Host "Building application images..."
docker compose build `
    migrate `
    backend `
    celery-worker `
    celery-beat `
    outbox-publisher `
    frontend

if ($LASTEXITCODE -ne 0) {
    throw "Docker image build failed."
}

Write-Host "Running database migrations..."
docker compose up migrate

if ($LASTEXITCODE -ne 0) {
    throw "Database migration failed."
}

Write-Host "Starting runtime services..."
docker compose up -d `
    backend `
    celery-worker `
    celery-beat `
    outbox-publisher `
    frontend

if ($LASTEXITCODE -ne 0) {
    throw "Failed to start runtime services."
}

Write-Host "Waiting for backend readiness..."

$ready = $false

for ($attempt = 1; $attempt -le 30; $attempt++) {
    try {
        $response = Invoke-RestMethod `
            -Uri "http://127.0.0.1:8000/health/ready" `
            -TimeoutSec 3

        $ready = $true
        break
    }
    catch {
        Start-Sleep -Seconds 2
    }
}

if (-not $ready) {
    docker compose logs --tail=200 backend
    throw "Backend did not become ready."
}

Write-Host "Waiting for frontend health..."

$frontendReady = $false

for ($attempt = 1; $attempt -le 15; $attempt++) {
    try {
        Invoke-WebRequest `
            -Uri "http://127.0.0.1:8081/health" `
            -TimeoutSec 3 `
            -UseBasicParsing |
            Out-Null

        $frontendReady = $true
        break
    }
    catch {
        Start-Sleep -Seconds 2
    }
}

if (-not $frontendReady) {
    docker compose logs --tail=200 frontend
    throw "Frontend did not become healthy."
}

Write-Host ""
Write-Host "Full stack started successfully."
Write-Host "Frontend: http://127.0.0.1:8081"
Write-Host "Backend:  http://127.0.0.1:8000"
