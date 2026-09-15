Set WshShell = CreateObject("WScript.Shell")
strPath = WshShell.CurrentDirectory & "\scripts\start_scanner.bat"
WshShell.Run Chr(34) & strPath & Chr(34), 0, False
Set WshShell = Nothing
