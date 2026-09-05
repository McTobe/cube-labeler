@echo off
title Brother PT-P300BT Label Studio
cd /d "%~dp0"
echo Starting Brother PT-P300BT Label Studio...
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application exited with an error.
    pause
)
