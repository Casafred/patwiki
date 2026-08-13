[CmdletBinding()]
param(
    [switch]$SkipBackend
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$tauriCliVersion = "2.11.4"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $Command $($Arguments -join ' ')"
    }
}

function Require-Command {
    param([Parameter(Mandatory = $true)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Build dependency '$Name' was not found on PATH."
    }
}

function Invoke-DownloadWithRetry {
    # GitHub release downloads from the Windows runner are occasionally interrupted
    # mid-stream ("io: Peer disconnected"). Tauri's own downloader has no retry, so we
    # pre-fetch the toolchain here with retries and let Tauri reuse the cache.
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Destination,
        [int]$MaxAttempts = 5,
        [int]$RetryDelaySec = 15,
        [int]$TimeoutSec = 120
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            Write-Host "  Downloading $Url (attempt $attempt/$MaxAttempts)..."
            Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing -TimeoutSec $TimeoutSec
            return
        }
        catch {
            Write-Warning "  Download attempt $attempt failed: $($_.Exception.Message)"
            if ($attempt -eq $MaxAttempts) {
                throw "Failed to download $Url after $MaxAttempts attempts: $($_.Exception.Message)"
            }
            Start-Sleep -Seconds $RetryDelaySec
        }
    }
}

function Ensure-TauriWindowsTools {
    # Pre-populate %LOCALAPPDATA%\tauri with WiX + NSIS so `tauri build` does not depend
    # on its flaky single-shot downloader. Paths/versions match tauri-bundler (tauri-cli 2.11.x).
    $tauriToolsDir = Join-Path $env:LOCALAPPDATA "tauri"
    New-Item -ItemType Directory -Force -Path $tauriToolsDir | Out-Null

    # --- WiX Toolset (wix314) -> WixTools314 ---
    $wixDir = Join-Path $tauriToolsDir "WixTools314"
    $wixCandle = Join-Path $wixDir "candle.exe"
    if (-not (Test-Path -LiteralPath $wixCandle)) {
        Write-Host "Preparing WiX toolset (wix314)..."
        if (Test-Path -LiteralPath $wixDir) { Remove-Item -Recurse -Force -LiteralPath $wixDir }
        New-Item -ItemType Directory -Force -Path $wixDir | Out-Null
        $wixZip = Join-Path $env:TEMP "wix314-binaries.zip"
        Invoke-DownloadWithRetry -Url "https://github.com/wixtoolset/wix3/releases/download/wix3141rtm/wix314-binaries.zip" -Destination $wixZip
        Expand-Archive -Path $wixZip -DestinationPath $wixDir -Force
        Remove-Item -Force -LiteralPath $wixZip -ErrorAction SilentlyContinue
        if (-not (Test-Path -LiteralPath $wixCandle)) {
            throw "WiX extraction did not produce candle.exe at $wixCandle"
        }
    }
    else {
        Write-Host "WiX toolset already present, skipping download."
    }

    # --- NSIS (nsis-3.11) -> NSIS ---
    $nsisDir = Join-Path $tauriToolsDir "NSIS"
    $nsisMake = Join-Path $nsisDir "makensis.exe"
    if (-not (Test-Path -LiteralPath $nsisMake)) {
        Write-Host "Preparing NSIS toolset (nsis-3.11)..."
        if (Test-Path -LiteralPath $nsisDir) { Remove-Item -Recurse -Force -LiteralPath $nsisDir }
        $nsisZip = Join-Path $env:TEMP "nsis-3.11.zip"
        Invoke-DownloadWithRetry -Url "https://github.com/tauri-apps/binary-releases/releases/download/nsis-3.11/nsis-3.11.zip" -Destination $nsisZip
        # nsis-3.11.zip ships a top-level nsis-3.11/ folder; flatten it into NSIS.
        $extractDir = Join-Path $env:TEMP "nsis-extract"
        if (Test-Path -LiteralPath $extractDir) { Remove-Item -Recurse -Force -LiteralPath $extractDir }
        Expand-Archive -Path $nsisZip -DestinationPath $extractDir -Force
        $nsisSubDir = Get-ChildItem -LiteralPath $extractDir -Directory | Where-Object { $_.Name -like "nsis-3.*" } | Select-Object -First 1
        if ($nsisSubDir) {
            Move-Item -Path $nsisSubDir.FullName -Destination $nsisDir -Force
        }
        else {
            New-Item -ItemType Directory -Force -Path $nsisDir | Out-Null
            Get-ChildItem -LiteralPath $extractDir | ForEach-Object { Move-Item -Path $_.FullName -Destination $nsisDir -Force }
        }
        Remove-Item -Recurse -Force -LiteralPath $extractDir -ErrorAction SilentlyContinue
        Remove-Item -Force -LiteralPath $nsisZip -ErrorAction SilentlyContinue
        if (-not (Test-Path -LiteralPath $nsisMake)) {
            throw "NSIS extraction did not produce makensis.exe at $nsisMake"
        }
    }
    else {
        Write-Host "NSIS toolset already present, skipping download."
    }

    # --- Tauri NSIS plugin (nsis_tauri_utils.dll) ---
    # Recent bundlers expect Plugins/x86-unicode/additional/nsis_tauri_utils.dll; older
    # ones expect Plugins/x86-unicode/nsis_tauri_utils.dll. Populate both so the required
    # files check passes regardless of the pinned CLI's convention. A hash mismatch (e.g.
    # the CLI pins a different plugin revision) only triggers a small re-download of the
    # dll by the bundler, never a full NSIS re-extraction.
    $pluginDir = Join-Path $nsisDir "Plugins\x86-unicode"
    $additionalDir = Join-Path $pluginDir "additional"
    $dllAdditional = Join-Path $additionalDir "nsis_tauri_utils.dll"
    $dllMain = Join-Path $pluginDir "nsis_tauri_utils.dll"
    if (-not (Test-Path -LiteralPath $dllAdditional)) {
        Write-Host "Preparing nsis_tauri_utils.dll plugin..."
        New-Item -ItemType Directory -Force -Path $additionalDir | Out-Null
        $dllTmp = Join-Path $env:TEMP "nsis_tauri_utils.dll"
        Invoke-DownloadWithRetry -Url "https://github.com/tauri-apps/nsis-tauri-utils/releases/download/nsis_tauri_utils-v0.5.3/nsis_tauri_utils.dll" -Destination $dllTmp
        Copy-Item -Path $dllTmp -Destination $dllAdditional -Force
        Copy-Item -Path $dllTmp -Destination $dllMain -Force
        Remove-Item -Force -LiteralPath $dllTmp -ErrorAction SilentlyContinue
    }
    else {
        Write-Host "nsis_tauri_utils.dll already present, skipping download."
    }
}

function Invoke-TauriBuildWithRetry {
    param(
        [Parameter(Mandatory = $true)][string]$CliVersion,
        [int]$MaxAttempts = 3,
        [int]$RetryDelaySec = 20
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        Write-Host "Building Tauri installers (attempt $attempt/$MaxAttempts) with CLI $CliVersion..."
        & npm exec --yes --package "@tauri-apps/cli@$CliVersion" -- tauri build
        if ($LASTEXITCODE -eq 0) { return }
        Write-Warning "Tauri build attempt $attempt failed (exit $LASTEXITCODE)."
        if ($attempt -eq $MaxAttempts) {
            throw "Tauri build failed after $MaxAttempts attempts (last exit code: $LASTEXITCODE)."
        }
        Start-Sleep -Seconds $RetryDelaySec
    }
}

Push-Location $root
try {
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    $ProgressPreference = "SilentlyContinue"

    foreach ($command in @("python", "node", "npm", "cargo")) {
        Require-Command $command
    }

    Invoke-Checked -Command "python" -Arguments @("-c", "import PyInstaller")
    Invoke-Checked -Command "python" -Arguments @("-c", "from PIL import Image")

    Write-Host "[1/5] Generate Tauri icon"
    Invoke-Checked -Command "python" -Arguments @("scripts/generate_icon.py")

    if ($SkipBackend) {
        Write-Host "[2/5] Reuse existing PyInstaller backend artifact"
    }
    else {
        Write-Host "[2/5] Build PyInstaller backend"
        Push-Location backend
        try {
            Invoke-Checked -Command "python" -Arguments @("-m", "PyInstaller", "patwiki_backend.spec", "--noconfirm", "--clean")
        }
        finally {
            Pop-Location
        }
    }

    $backendExe = Join-Path $root "backend\dist\patwiki-backend\patwiki-backend.exe"
    if (-not (Test-Path -LiteralPath $backendExe -PathType Leaf)) {
        throw "PyInstaller completed but the backend artifact was not found: $backendExe"
    }
    $backendSize = [math]::Round((Get-Item -LiteralPath $backendExe).Length / 1MB, 1)
    Write-Host "Backend artifact: $backendExe ($backendSize MB)"

    Write-Host "[3/5] Install and build frontend"
    Push-Location frontend
    try {
        Invoke-Checked -Command "npm" -Arguments @("ci")
        Invoke-Checked -Command "npm" -Arguments @("run", "build")
    }
    finally {
        Pop-Location
    }

    Write-Host "[4/5] Ensure Tauri Windows tooling & build installers (CLI $tauriCliVersion)"
    Ensure-TauriWindowsTools
    Push-Location src-tauri
    try {
        Invoke-TauriBuildWithRetry -CliVersion $tauriCliVersion
    }
    finally {
        Pop-Location
    }

    Write-Host "[5/5] Verify installer artifacts"
    $msiDir = Join-Path $root "src-tauri\target\release\bundle\msi"
    $nsisDir = Join-Path $root "src-tauri\target\release\bundle\nsis"
    $msiFiles = @()
    if (Test-Path -LiteralPath $msiDir) {
        $msiFiles = @(Get-ChildItem -LiteralPath $msiDir -Filter *.msi -File)
    }
    $nsisFiles = @()
    if (Test-Path -LiteralPath $nsisDir) {
        $nsisFiles = @(Get-ChildItem -LiteralPath $nsisDir -Filter *.exe -File)
    }

    if ($msiFiles.Count -eq 0) {
        throw "MSI installer was not found: $msiDir"
    }
    if ($nsisFiles.Count -eq 0) {
        throw "NSIS installer was not found: $nsisDir"
    }

    foreach ($installer in @($msiFiles) + @($nsisFiles)) {
        $size = [math]::Round($installer.Length / 1MB, 1)
        Write-Host "Installer: $($installer.FullName) ($size MB)"
    }
    Write-Host "Windows installer build completed."
}
finally {
    Pop-Location
}
