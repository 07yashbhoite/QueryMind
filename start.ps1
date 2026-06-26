# QueryMind — quick start for presentation demo (PowerShell)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $env:GROQ_API_KEY) {
    if (Test-Path ".env") {
        Get-Content ".env" | ForEach-Object {
            if ($_ -match '^\s*GROQ_API_KEY\s*=\s*(.+)\s*$') {
                $env:GROQ_API_KEY = $matches[1].Trim().Trim('"').Trim("'")
            }
        }
    }
}

if (-not $env:GROQ_API_KEY -or $env:GROQ_API_KEY -eq "your_groq_api_key_here") {
    Write-Host ""
    Write-Host "GROQ_API_KEY is not set." -ForegroundColor Red
    Write-Host "1. Copy .env.example to .env"
    Write-Host "2. Add your key from https://console.groq.com"
    Write-Host "3. Run this script again"
    Write-Host ""
    exit 1
}

Write-Host "Starting QueryMind at http://localhost:5000" -ForegroundColor Green
python app.py
