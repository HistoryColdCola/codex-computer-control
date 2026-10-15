@echo off
cd /d "%~dp0"
node codex-computer-control\scripts\install.js
if errorlevel 1 pause
