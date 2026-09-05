@echo off
title Build Brother PT-P300BT Label Studio (Single Portable EXE)
cd /d "%~dp0"
echo =========================================================
echo Compiling Brother PT-P300BT Label Studio to Single .exe
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
