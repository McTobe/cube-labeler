@echo off
title Cube Labeler (web)
cd /d "%~dp0"
echo Starting Cube Labeler web...
python web\serve.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo The web server stopped with an error.
    pause
)
