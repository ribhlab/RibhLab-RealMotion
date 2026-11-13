@echo off
setlocal
chcp 65001 >nul
title RibhLab RealMotion - Offline MuseTalk Lip Sync 1.5 Setup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\setup_lipsync.ps1"
if errorlevel 1 (
 echo.
 echo MuseTalk setup is incomplete. Check the error above and use LIPSYNC_SETUP.md.
 pause
)
