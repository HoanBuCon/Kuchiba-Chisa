# ============================================================
# CHISA AI - Startup Script
# Configures Docker Dependencies, Backend (Uvicorn) and Frontend (Vite)
# Usage: .\start.ps1
# ============================================================

$ROOT = $PSScriptRoot

Write-Host ""
Write-Host "  CHISA AI - Starting up..." -ForegroundColor Red
Write-Host "  Backend  -> http://localhost:8000" -ForegroundColor DarkGray
Write-Host "  Frontend -> http://localhost:5173" -ForegroundColor DarkGray
Write-Host ""

# -- Docker Setup ---------------------------------------------
Write-Host "[1/3] Resetting Docker Containers (Database, Redis, Qdrant)..." -ForegroundColor Yellow
docker-compose down
# Bắt buộc chỉ chạy các Database gầm, KHÔNG chạy container 'app' để tránh chiếm port 8000
docker-compose up -d postgres redis qdrant

Write-Host "[+] Docker is ready!" -ForegroundColor Green
Write-Host ""
Start-Sleep -Seconds 2

# -- Backend --------------------------------------------------
Write-Host "[2/3] Launching Backend Server in new window..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ROOT'; Write-Host '[ BACKEND ]' -ForegroundColor Red; .\venv\Scripts\activate; uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload" -WindowStyle Normal

# Brief pause to let backend initialize first
Start-Sleep -Seconds 3

# -- Frontend -------------------------------------------------
Write-Host "[3/3] Launching Frontend Server in new window..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ROOT\frontend'; Write-Host '[ FRONTEND ]' -ForegroundColor Cyan; npm run dev" -WindowStyle Normal

Write-Host "  All services launched! Chat window will appear momentarily." -ForegroundColor Green
Write-Host "  Open: http://localhost:5173" -ForegroundColor Cyan
Write-Host ""
