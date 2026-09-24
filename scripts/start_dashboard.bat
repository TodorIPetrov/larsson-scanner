@echo off
title Larsson Line Web Dashboard
cd /d "%~dp0\.."
echo ========================================================
echo   Larsson Line Market Scanner - Web Dashboard Server
echo ========================================================
echo.

:: Detect Python executable
set PYTHON_CMD=python
if exist "%~dp0\..\.venv\Scripts\python.exe" (
    set "PYTHON_CMD=%~dp0\..\.venv\Scripts\python.exe"
)

:: Check if port 8080 is already listening
netstat -ano | findstr /R /C:":8080 .*LISTENING" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [INFO] Web server is already running on port 8080!
    echo Opening browser at http://localhost:8080 ...
    start http://localhost:8080
    echo.
    echo Dashboard is active. You can close this window.
    pause
    exit /b 0
)

echo Starting web server at http://localhost:8080 ...
echo Opening browser...
start http://localhost:8080
echo.
echo Press Ctrl+C in this window to stop the server.
echo.

"%PYTHON_CMD%" -m http.server 8080 -d dashboard
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Failed to start server on port 8080.
    echo Make sure Python is installed and port 8080 is not blocked.
    pause
)
