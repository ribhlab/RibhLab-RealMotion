@echo off
setlocal
chcp 65001 >nul
title RibhLab RealMotion - LAN Postprocessing Worker
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\start_remote_worker.ps1"
if errorlevel 1 pause
