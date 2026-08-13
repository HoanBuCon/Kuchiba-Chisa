# CHISA AI - CLI Control Center Launcher
# Usage: .\chisa_cli.ps1
$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $PSScriptRoot
if (Test-Path "$PSScriptRoot\venv\Scripts\Activate.ps1") {
    & "$PSScriptRoot\venv\Scripts\Activate.ps1"
}
python chisa_cli.py
