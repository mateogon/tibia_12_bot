@echo off

:: 1. Check for Administrator privileges
:: If 'fltmc' fails, we are not admin. Relaunch as Admin using PowerShell.
fltmc >nul 2>&1 || (
    echo Requesting Administrator privileges...
    PowerShell Start-Process -FilePath 'powershell' -ArgumentList '-NoExit', '-ExecutionPolicy Bypass', '-Command "cd ''C:\Users\mateo\Desktop\tibia_12_bot''; conda activate tibia; python main.py"' -Verb RunAs
    exit /b
)

:: Note: The script exits here because the new Elevated PowerShell window takes over.