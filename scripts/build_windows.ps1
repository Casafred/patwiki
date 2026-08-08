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

Push-Location $root
try {
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"

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

    Write-Host "[4/5] Build Tauri Windows installers (CLI $tauriCliVersion)"
    Push-Location src-tauri
    try {
        Invoke-Checked -Command "npm" -Arguments @("exec", "--yes", "--package", "@tauri-apps/cli@$tauriCliVersion", "--", "tauri", "build")
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
