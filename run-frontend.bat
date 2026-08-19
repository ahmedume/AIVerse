@echo off
cd /d "%~dp0frontend"
pnpm dev -p 3001
if errorlevel 1 pause