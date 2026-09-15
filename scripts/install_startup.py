import os
import subprocess

startup = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
shortcut_path = os.path.join(startup, "LarssonLineScanner.lnk")
script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "start_scanner_silent.vbs"))
work_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

ps_code = f"""
$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{shortcut_path}')
$Shortcut.TargetPath = 'wscript.exe'
$Shortcut.Arguments = '"{script_path}"'
$Shortcut.WorkingDirectory = '{work_dir}'
$Shortcut.Save()
"""

subprocess.run(["powershell", "-NoProfile", "-Command", ps_code], check=True)
if os.path.exists(shortcut_path):
    print(f"SUCCESS: Shortcut created at {shortcut_path}")
else:
    print("FAILED to create shortcut")
