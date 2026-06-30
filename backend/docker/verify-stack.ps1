$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

Write-Host "Checking container status..."
docker compose ps --all

Write-Host "Checking migration status..."
$migrateId = docker compose ps -a -q migrate

if (-not $migrateId) {
    throw "Migrate container does not exist."
}

$exitCode = docker inspect `
    $migrateId `
    --format "{{.State.ExitCode}}"

if ($exitCode -ne "0") {
    docker compose logs --tail=200 migrate
    throw "Migration exit code is $exitCode."
}

Write-Host "Checking backend live..."
Invoke-RestMethod `
    -Uri "http://127.0.0.1:8000/health/live" |
    Out-Null

Write-Host "Checking backend ready..."
Invoke-RestMethod `
    -Uri "http://127.0.0.1:8000/health/ready" |
    Out-Null

Write-Host "Checking frontend health..."
Invoke-WebRequest `
    -Uri "http://127.0.0.1:8081/health" `
    -UseBasicParsing |
    Out-Null

Write-Host "Checking SPA fallback..."
Invoke-WebRequest `
    -Uri "http://127.0.0.1:8081/auth/login" `
    -UseBasicParsing |
    Out-Null

Write-Host "Checking API proxy..."
Invoke-RestMethod `
    -Uri "http://127.0.0.1:8081/api/auth/csrf" |
    Out-Null

Write-Host "Checking Celery worker..."
docker compose exec `
    -T `
    celery-worker `
    celery `
    -A app.workers.celery_app `
    inspect ping `
    --timeout=10

if ($LASTEXITCODE -ne 0) {
    throw "Celery worker did not respond."
}

Write-Host "Checking runtime logs..."
docker compose logs --tail=50 outbox-publisher
docker compose logs --tail=50 celery-beat

Write-Host ""
Write-Host "STACK VERIFICATION PASSED"
