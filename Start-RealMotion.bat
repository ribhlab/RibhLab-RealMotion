@echo off
setlocal
chcp 65001 >nul
title RibhLab RealMotion - Local NVIDIA Studio
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\start.ps1"
if errorlevel 1 (
  echo.
  echo RealMotion could not start. Read the diagnostic messages above.
  pause
)
