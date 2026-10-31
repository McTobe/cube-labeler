@echo off
title Cube Labeler cut test
cd /d "%~dp0.."
python tools\cut_test.py %*
if %ERRORLEVEL% NEQ 0 pause
