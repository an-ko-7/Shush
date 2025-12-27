param(
    [switch]$NoInstall,
    [switch]$Dev
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

if (-not $PSBoundParameters.ContainsKey("NoInstall")) {
    if (Test-Path "node_modules") {
        $NoInstall = $true
    }
}

if (-not (Test-Path ".env")) {
    Write-Host "WARNING: .env not found. Create it from .env.example and set the Modal URL." -ForegroundColor Yellow
}

$bun = Get-Command bun -ErrorAction SilentlyContinue
$npm = Get-Command npm -ErrorAction SilentlyContinue

function HasBuildCache {
    return Test-Path ".next\\BUILD_ID"
}

if ($bun) {
    if (-not $NoInstall) {
        bun install
    }
    if (-not $Dev) {
        if (-not (HasBuildCache)) {
            bun run build
        }
        bun run start
    } else {
        bun run dev
    }
}
elseif ($npm) {
    if (-not $NoInstall) {
        npm install
    }
    if (-not $Dev) {
        if (-not (HasBuildCache)) {
            npm run build
        }
        npm run start
    } else {
        npm run dev
    }
}
else {
    Write-Error "Neither bun nor npm was found. Install bun or Node.js first."
}
