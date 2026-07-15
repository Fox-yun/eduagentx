#requires -Version 7.0

[CmdletBinding()]
param(
    [ValidateSet("production", "demo")]
    [string]$Mode = "demo"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$EnvFile = ".env.docker"
$ComposeArgs = @("--env-file", $EnvFile, "-f", "docker-compose.yml")

if ($Mode -eq "production") {
    $ComposeArgs += "-f", "docker-compose.production.yml"
} else {
    $ComposeArgs += "-f", "docker-compose.demo.yml"
    $ComposeArgs += "--profile", "demo"
}

Write-Host "Checking container status (mode: $Mode)..."
docker compose @ComposeArgs ps --all

Write-Host "Checking migration status..."
$migrateId = docker compose @ComposeArgs ps -a -q migrate

if (-not $migrateId) {
    throw "Migrate container does not exist."
}

$exitCode = docker inspect `
    $migrateId `
    --format "{{.State.ExitCode}}"

if ($exitCode -ne "0") {
    docker compose @ComposeArgs logs --tail=200 migrate
    throw "Migration exit code is $exitCode."
}

# ── Health checks based on mode ──
if ($Mode -eq "production") {
    $BaseUrl = "https://127.0.0.1"
    $SkipCert = @{"SkipCertificateCheck" = $true}
} else {
    $BaseUrl = "http://127.0.0.1:8000"
    $SkipCert = @{}
    $FrontendUrl = "http://127.0.0.1:8081"
}

Write-Host "Checking backend live..."
Invoke-RestMethod `
    -Uri "$BaseUrl/health/live" `
    @SkipCert |
    Out-Null

Write-Host "Checking backend ready..."
$readyResponse = Invoke-RestMethod `
    -Uri "$BaseUrl/health/ready" `
    @SkipCert

if ($readyResponse.status -ne "ready") {
    throw "Backend not ready: $($readyResponse.status)"
}

if ($Mode -eq "production") {
    Write-Host "Checking Nginx health..."
    Invoke-WebRequest `
        -Uri "$BaseUrl/health" `
        -UseBasicParsing `
        @SkipCert |
        Out-Null

    Write-Host "Checking SPA fallback..."
    Invoke-WebRequest `
        -Uri "$BaseUrl/auth/login" `
        -UseBasicParsing `
        @SkipCert |
        Out-Null

    Write-Host "Checking API proxy..."
    Invoke-RestMethod `
        -Uri "$BaseUrl/api/auth/csrf" `
        @SkipCert |
        Out-Null
} else {
    Write-Host "Checking frontend health..."
    Invoke-WebRequest `
        -Uri "$FrontendUrl/health" `
        -UseBasicParsing |
        Out-Null

    Write-Host "Checking SPA fallback..."
    Invoke-WebRequest `
        -Uri "$FrontendUrl/auth/login" `
        -UseBasicParsing |
        Out-Null

    Write-Host "Checking API proxy..."
    Invoke-RestMethod `
        -Uri "$FrontendUrl/api/auth/csrf" |
        Out-Null
}

Write-Host "Checking Celery worker..."
docker compose @ComposeArgs exec `
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
docker compose @ComposeArgs logs --tail=50 outbox-publisher
docker compose @ComposeArgs logs --tail=50 celery-beat

Write-Host ""
Write-Host "STACK VERIFICATION PASSED ($Mode mode)"
