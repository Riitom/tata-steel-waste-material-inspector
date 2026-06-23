$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath "models\final.pt")) {
    throw "Final model not found: models\final.pt"
}

if (-not (Test-Path -LiteralPath "web\frontend\dist\index.html")) {
    throw "Frontend build not found. Run npm install and npm run build in web\frontend."
}

python scripts\run_web.py
