# ============================================================
# CHISA AI - Startup Script
# Launches Backend (Uvicorn) and Frontend (Vite) concurrently
# Usage: .\start.ps1
# ============================================================

$ROOT = $PSScriptRoot

Write-Host ""
Write-Host "  CHISA AI - Starting up..." -ForegroundColor Red
Write-Host "  Backend  -> http://localhost:8000" -ForegroundColor DarkGray
Write-Host "  Frontend -> http://localhost:5173" -ForegroundColor DarkGray
Write-Host ""

# -- Backend --------------------------------------------------
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ROOT'; Write-Host '[ BACKEND ]' -ForegroundColor Red; .\venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000" -WindowStyle Normal

# Brief pause to let backend initialize first
Start-Sleep -Seconds 2

# -- Frontend -------------------------------------------------
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ROOT\frontend'; Write-Host '[ FRONTEND ]' -ForegroundColor Cyan; npm run dev" -WindowStyle Normal

Write-Host "  Both servers launched in separate windows!" -ForegroundColor Green
Write-Host "  Open: http://localhost:5173" -ForegroundColor Yellow
Write-Host ""
