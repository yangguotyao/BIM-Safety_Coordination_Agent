@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp002_网站源码\scripts\start.ps1" %*
set "demo_exit_code=%errorlevel%"
if not "%demo_exit_code%"=="0" pause
exit /b %demo_exit_code%
