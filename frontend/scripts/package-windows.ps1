#requires -Version 7.0

[CmdletBinding()]
param(
    [switch]$SkipAppBuild,
    [switch]$OfflineRelease
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "The EduAgentX Windows installer must be built on Windows."
}

$FrontendDir = Split-Path -Parent $PSScriptRoot
$TauriDir = Join-Path $FrontendDir "src-tauri"
$TargetTriple = "x86_64-pc-windows-msvc"
$AppExe = Join-Path $TauriDir "target\$TargetTriple\release\EduAgentX.exe"
$InstallerScript = Join-Path $TauriDir "windows\installer.nsi"
$PackageConfig = Join-Path $TauriDir "tauri.package.conf.json"
$IconPath = Join-Path $TauriDir "icons\icon.ico"
$ReleaseDir = Split-Path -Parent $FrontendDir

# Read version dynamically from package.json to avoid hardcoding.
$PackageJson = Get-Content -Raw (Join-Path $FrontendDir "package.json") | ConvertFrom-Json
$AppVersion = $PackageJson.version
$OutputFile = Join-Path $ReleaseDir "EduAgentX_${AppVersion}_x64-setup.exe"
$HashFile = "$OutputFile.sha256"
$CacheDir = Join-Path $FrontendDir ".packaging"
$NsisVersion = "3.11"
$NsisDir = Join-Path $CacheDir "nsis-$NsisVersion"
$NsisZip = Join-Path $CacheDir "nsis-$NsisVersion.zip"
$NsisDownloadUrl = "https://sourceforge.net/projects/nsis/files/NSIS%203/$NsisVersion/nsis-$NsisVersion.zip/download"
# NSIS 3.11 SHA-256 hash — must be pinned for reproducible builds.
# Verified hash from official SourceForge release (nsis-3.11.zip).
# To re-verify: Invoke-WebRequest -Uri $NsisDownloadUrl -OutFile nsis-3.11.zip; Get-FileHash nsis-3.11.zip -Algorithm SHA256
$NsisExpectedHash = "c7d27f780ddb6cffb4730138cd1591e841f4b7edb155856901cdf5f214394fa1"
$WebView2Bootstrapper = Join-Path $CacheDir "MicrosoftEdgeWebview2Setup.exe"
$WebView2DownloadUrl = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
# WebView2 Standalone Offline Installer (optional — for truly offline installation)
# Download from: https://developer.microsoft.com/en-us/microsoft-edge/webview2/
# Select "Evergreen Standalone Installer" (x64)
$WebView2Standalone = Join-Path $CacheDir "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
$WebView2StandaloneUrl = "https://go.microsoft.com/fwlink/?linkid=2124701"

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Get-MakeNsis {
    $CachedMakeNsis = Join-Path $NsisDir "makensis.exe"
    if (Test-Path -LiteralPath $CachedMakeNsis -PathType Leaf) {
        return $CachedMakeNsis
    }

    $TauriToolsDir = Join-Path $TauriDir "target\.tauri\nsis-$NsisVersion"
    $TauriMakeNsis = Join-Path $TauriToolsDir "makensis.exe"
    if (Test-Path -LiteralPath $TauriMakeNsis -PathType Leaf) {
        Write-Host "Reusing the NSIS $NsisVersion tools cached by Tauri."
        Copy-Item -LiteralPath $TauriToolsDir -Destination $NsisDir -Recurse -Force
        return $CachedMakeNsis
    }

    Write-Host "Downloading NSIS $NsisVersion..."
    Invoke-WebRequest -Uri $NsisDownloadUrl -OutFile $NsisZip -UseBasicParsing

    # Verify download hash
    if ($NsisExpectedHash) {
        $ActualHash = (Get-FileHash -LiteralPath $NsisZip -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ActualHash -ne $NsisExpectedHash) {
            throw "NSIS ZIP hash mismatch! Expected: $NsisExpectedHash, Got: $ActualHash"
        }
        Write-Host "NSIS ZIP hash verified."
    } elseif ($OfflineRelease) {
        throw "NSIS hash is not pinned. In -OfflineRelease mode, \$NsisExpectedHash must be set to a verified SHA-256 hash. Download nsis-$NsisVersion.zip, run Get-FileHash, and update the variable."
    } else {
        Write-Host "WARNING: NSIS hash not pinned — skipping verification. Pin \$NsisExpectedHash for reproducible builds, or use -OfflineRelease to enforce." -ForegroundColor Yellow
    }

    Expand-Archive -LiteralPath $NsisZip -DestinationPath $CacheDir -Force

    if (-not (Test-Path -LiteralPath $CachedMakeNsis -PathType Leaf)) {
        throw "makensis.exe was not found after extracting NSIS: $CachedMakeNsis"
    }
    return $CachedMakeNsis
}

function Get-WebView2Bootstrapper {
    if (-not (Test-Path -LiteralPath $WebView2Bootstrapper -PathType Leaf)) {
        Write-Host "Downloading the Microsoft Edge WebView2 Evergreen Bootstrapper..."
        Invoke-WebRequest -Uri $WebView2DownloadUrl -OutFile $WebView2Bootstrapper -UseBasicParsing
    }

    # Always verify signature, even for cached files
    $Signature = Get-AuthenticodeSignature -LiteralPath $WebView2Bootstrapper
    if ($Signature.Status -ne "Valid" -or $Signature.SignerCertificate.Subject -notmatch "Microsoft Corporation") {
        throw "The WebView2 Bootstrapper Microsoft signature is invalid: $($Signature.Status). Delete $WebView2Bootstrapper and retry."
    }
}

function Get-WebView2Standalone {
    # Try to download the standalone installer for offline installation
    if (-not (Test-Path -LiteralPath $WebView2Standalone -PathType Leaf)) {
        Write-Host "Downloading the Microsoft Edge WebView2 Standalone Installer (for offline installation)..."
        try {
            Invoke-WebRequest -Uri $WebView2StandaloneUrl -OutFile $WebView2Standalone -UseBasicParsing -TimeoutSec 120
        } catch {
            Write-Host "WARNING: Could not download WebView2 Standalone Installer — will use online bootstrapper. $_" -ForegroundColor Yellow
            return $null
        }
    }

    # Always verify signature, even for cached/pre-placed files
    $Signature = Get-AuthenticodeSignature -LiteralPath $WebView2Standalone
    if ($Signature.Status -ne "Valid" -or $Signature.SignerCertificate.Subject -notmatch "Microsoft Corporation") {
        Write-Host "WARNING: WebView2 Standalone Installer signature invalid — falling back to online bootstrapper." -ForegroundColor Yellow
        Remove-Item -LiteralPath $WebView2Standalone -Force -ErrorAction SilentlyContinue
        return $null
    }
    Write-Host "WebView2 Standalone Installer verified (signature OK)."
    return $WebView2Standalone
}

New-Item -ItemType Directory -Path $CacheDir -Force | Out-Null
New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null

Push-Location $FrontendDir
try {
    if (-not $SkipAppBuild) {
        Write-Host "Building the EduAgentX web frontend..."
        Invoke-CheckedCommand -FilePath "npm.cmd" -Arguments @("run", "build")

        Write-Host "Building the EduAgentX Tauri Windows x64 application..."
        Invoke-CheckedCommand -FilePath "npx.cmd" -Arguments @(
            "tauri", "build",
            "--target", $TargetTriple,
            "--no-bundle",
            "--config", $PackageConfig
        )
    }

    if (-not (Test-Path -LiteralPath $AppExe -PathType Leaf)) {
        throw "The compiled application was not found: $AppExe"
    }
    if (-not (Test-Path -LiteralPath $InstallerScript -PathType Leaf)) {
        throw "The NSIS installer script was not found: $InstallerScript"
    }
    if (-not (Test-Path -LiteralPath $PackageConfig -PathType Leaf)) {
        throw "The Tauri packaging config was not found: $PackageConfig"
    }
    if (-not (Test-Path -LiteralPath $IconPath -PathType Leaf)) {
        throw "The application icon was not found: $IconPath"
    }

    $MakeNsis = Get-MakeNsis
    Get-WebView2Bootstrapper
    $StandaloneInstaller = Get-WebView2Standalone

    if ($OfflineRelease -and -not $StandaloneInstaller) {
        throw "-OfflineRelease mode requires the WebView2 Standalone Installer. Download it from https://developer.microsoft.com/en-us/microsoft-edge/webview2/ and place it at: $WebView2Standalone"
    }

    if (Test-Path -LiteralPath $OutputFile) {
        Remove-Item -LiteralPath $OutputFile -Force
    }
    if (Test-Path -LiteralPath $HashFile) {
        Remove-Item -LiteralPath $HashFile -Force
    }

    # Build a VIProductVersion string (x.y.z.w) from the semver version.
    $ViVersion = $AppVersion
    $versionParts = $AppVersion -split '\.'
    if ($versionParts.Count -eq 3) {
        $ViVersion = "$($versionParts[0]).$($versionParts[1]).$($versionParts[2]).0"
    } elseif ($versionParts.Count -lt 4) {
        $ViVersion = "$AppVersion.0"
    }

    $NsisArgs = @(
        "/V3",
        "/INPUTCHARSET", "UTF8",
        "/DAPP_EXE=$AppExe",
        "/DAPP_ICON=$IconPath",
        "/DWEBVIEW2_BOOTSTRAPPER=$WebView2Bootstrapper",
        "/DOUTPUT_FILE=$OutputFile",
        "/DPRODUCT_VERSION=$AppVersion",
        "/DVIPRODUCT_VERSION=$ViVersion"
    )
    if ($StandaloneInstaller) {
        $NsisArgs += "/DWEBVIEW2_STANDALONE=$StandaloneInstaller"
    }
    $NsisArgs += $InstallerScript

    Write-Host "Creating the EduAgentX Windows installer..."
    Invoke-CheckedCommand -FilePath $MakeNsis -Arguments $NsisArgs

    if (-not (Test-Path -LiteralPath $OutputFile -PathType Leaf)) {
        throw "The installer was not created at the expected path: $OutputFile"
    }

    $Hash = Get-FileHash -LiteralPath $OutputFile -Algorithm SHA256
    "$($Hash.Hash.ToLowerInvariant())  $([IO.Path]::GetFileName($OutputFile))" |
        Set-Content -LiteralPath $HashFile -Encoding ascii

    $InstallerInfo = Get-Item -LiteralPath $OutputFile
    Write-Host "Build complete: $OutputFile"
    Write-Host "File size: $($InstallerInfo.Length) bytes"
    Write-Host "SHA-256: $($Hash.Hash)"
    Write-Host "WebView2 runtime mode: $(if ($StandaloneInstaller) { 'offline' } else { 'online' })"
}
finally {
    Pop-Location
}
