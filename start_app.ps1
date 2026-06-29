$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath "backend\models\final.pt")) {
    throw "Final model not found: backend\models\final.pt"
}

if (-not (Test-Path -LiteralPath "frontend\dist\index.html")) {
    throw "Frontend build not found. Run npm install and npm run build in frontend."
}

python backend\scripts\run_web.py
