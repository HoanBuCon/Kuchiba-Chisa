@echo off
title CHISA AI CONTROL CENTER
cd /d "%~dp0"
if exist ".\venv\Scripts\activate.bat" (
    call ".\venv\Scripts\activate.bat"
)
python chisa_cli.py
pause
