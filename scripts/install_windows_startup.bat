@echo off
setlocal
echo Installing Larsson Line Scanner to Windows Startup...

set "SCRIPT_PATH=%~dp0start_scanner_silent.vbs"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\LarssonLineScanner.lnk"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%SCRIPT_PATH%\"'; $s.WorkingDirectory = '%~dp0..'; $s.Save()"

if exist "%SHORTCUT_PATH%" (
    echo [OK] Successfully installed! The scanner will now automatically start on Windows boot in the background.
) else (
    echo [FAIL] Could not create startup shortcut.
)
pause
