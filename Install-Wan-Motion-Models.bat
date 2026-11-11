@echo off
setlocal
chcp 65001 >nul
title Install Wan 2.2 Models for Local NVIDIA
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\install_models.ps1"
if errorlevel 1 (
 echo.
 echo Model installer stopped. Read the messages above.
 pause
)
