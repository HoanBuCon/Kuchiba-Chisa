# ============================================================
# CHISA AI - Startup Script
# Configures Docker Dependencies, Backend (Uvicorn) and Frontend (Vite)
# Usage: .\start.ps1
# ============================================================

$ROOT = $PSScriptRoot

# ── Cleanup Helpers ──────────────────────────────────────────────

function Stop-ProcessTree {
    param([int]$TargetProcessId)
    taskkill.exe /F /T /PID $TargetProcessId 2>$null | Out-Null
    Stop-Process -Id $TargetProcessId -Force -ErrorAction SilentlyContinue
}

function Stop-ProcessOnPort {
    param([int]$Port)

    Write-Host "  [cleanup] Checking port $Port ..." -ForegroundColor DarkGray
    $killedPids = @()

    # ── Method 1: Get-NetTCPConnection (preferred, fast) ──
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($connections) {
        foreach ($conn in $connections) {
            $procId = $conn.OwningProcess
            if ($procId -and $procId -notin $killedPids) {
                Write-Host "  [cleanup] Killing PID $procId on port $Port" -ForegroundColor Red
                Stop-ProcessTree $procId
                $killedPids += $procId
            }
        }
    }

    # ── Method 2: netstat fallback (catches edge cases) ──
    $netstatLines = cmd /c "netstat -ano 2>NUL" | Select-String "LISTENING" | Select-String ":$Port\b"
    foreach ($line in $netstatLines) {
        $parts = -split $line.ToString().Trim()
        if ($parts.Count -ge 5) {
            $procId = [int]$parts[-1]
            if ($procId -ne 0 -and $procId -notin $killedPids) {
                Write-Host "  [cleanup] Killing PID $procId on port $Port (netstat)" -ForegroundColor Red
                Stop-ProcessTree $procId
                $killedPids += $procId
            }
        }
    }
}

function Stop-AllLegacyProcesses {
    Write-Host "[Chisa AI] Phase 0 - Don dep tien trinh cu..." -ForegroundColor Yellow

    # ── 1. Kill ALL Python processes (backend) ──
    $pythonProcesses = @(Get-Process -Name "python*" -ErrorAction SilentlyContinue)
    if ($pythonProcesses.Count -gt 0) {
        Write-Host "  [cleanup] Found $($pythonProcesses.Count) Python process(es) - terminating..." -ForegroundColor Red
        foreach ($p in $pythonProcesses) {
            Stop-ProcessTree $p.Id
        }
    }

    # ── 2. Kill ALL Node.js processes (frontend + discord bot) ──
    $nodeProcesses = @(Get-Process -Name "node*" -ErrorAction SilentlyContinue)
    if ($nodeProcesses.Count -gt 0) {
        Write-Host "  [cleanup] Found $($nodeProcesses.Count) Node.js process(es) - terminating..." -ForegroundColor Red
        foreach ($p in $nodeProcesses) {
            Stop-ProcessTree $p.Id
        }
    }

    # ── 3. Kill processes on project ports (defense-in-depth) ──
    Stop-ProcessOnPort 8000   # Backend (Uvicorn)
    Stop-ProcessOnPort 5173   # Frontend (Vite primary)
    Stop-ProcessOnPort 5174   # Frontend (Vite secondary)

    # ── 4. Wait & verify ──
    Start-Sleep -Seconds 2

    $remaining = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
    $remaining += @(Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue)
    $remaining += @(Get-NetTCPConnection -LocalPort 5174 -State Listen -ErrorAction SilentlyContinue)
    if ($remaining.Count -gt 0) {
        Write-Host "  [cleanup] WARNING: $($remaining.Count) process(es) still on target ports - forcing..." -ForegroundColor Red
        foreach ($conn in $remaining) {
            Stop-ProcessTree $conn.OwningProcess
        }
        Start-Sleep -Seconds 1
    }

    Write-Host "  [cleanup] Don dep hoan tat!" -ForegroundColor Green
}

# ── Execute Cleanup ───────────────────────────────────────────

Stop-AllLegacyProcesses

Write-Host ""
Write-Host "  CHISA AI - Starting up..." -ForegroundColor Red
Write-Host "  Backend  -> http://localhost:8000" -ForegroundColor DarkGray
Write-Host "  Frontend -> http://localhost:5173" -ForegroundColor DarkGray
Write-Host ""

# -- Docker Setup ---------------------------------------------
Write-Host "[1/3] Resetting Docker Containers (Database, Redis, Qdrant)..." -ForegroundColor Yellow
docker-compose down
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [!] docker-compose down failed (exit code $LASTEXITCODE). Is Docker Desktop running?" -ForegroundColor Red
    exit 1
}

# Chi chay cac Database ngam, KHONG chay container 'app' de tranh chiem port 8000
docker-compose up -d postgres redis qdrant
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [!] docker-compose up failed (exit code $LASTEXITCODE). Is Docker Desktop running?" -ForegroundColor Red
    exit 1
}

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