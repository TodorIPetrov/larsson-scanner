@echo off
title Larsson Line Web Dashboard
cd /d "%~dp0\.."
echo ========================================================
echo   Larsson Line Market Scanner - Web Dashboard Server
echo ========================================================
echo.
echo Starting web server at http://localhost:8080 ...
echo Opening browser...
start http://localhost:8080
echo.
echo Press Ctrl+C in this window to stop the server.
echo.
python -m http.server 8080 -d dashboard
