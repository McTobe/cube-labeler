@echo off
title Build Cube Labeler (Single Portable EXE)
cd /d "%~dp0"
echo =========================================================
echo Compiling Cube Labeler to Single .exe
echo =========================================================
echo.
python build.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Compilation failed with error code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)
echo.
echo Build complete. The executable is located at:
echo dist\PrintLabel.exe
echo.
pause
