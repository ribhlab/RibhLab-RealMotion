@echo off
setlocal
chcp 65001 >nul
title RibhLab RealMotion - Offline Arabic Piper Voice
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\setup_voice.ps1"
if errorlevel 1 (
 echo.
 echo Offline voice setup did not complete.
 pause
)
