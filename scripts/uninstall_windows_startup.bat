@echo off
set "SHORTCUT_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\LarssonLineScanner.lnk"
if exist "%SHORTCUT_PATH%" (
    del "%SHORTCUT_PATH%"
    echo [OK] Removed LarssonLineScanner from Windows Startup.
) else (
    echo [INFO] LarssonLineScanner was not found in Windows Startup.
)
pause
