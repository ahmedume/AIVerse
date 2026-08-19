@echo off
cd /d "%~dp0backend"
uv run uvicorn app.main:app --app-dir src --host 127.0.0.1 --port 8001
if errorlevel 1 pause