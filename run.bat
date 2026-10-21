@echo off
title Cube Labeler
cd /d "%~dp0"
echo Starting Cube Labeler...
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application exited with an error.
    pause
)
