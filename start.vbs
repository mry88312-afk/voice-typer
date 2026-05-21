' Voice Typer - Silent Launcher
' Double-click to run, no console window, only tray icon

Option Explicit

Dim objFSO, objShell, scriptDir, pythonw, mainPy

Set objFSO = CreateObject("Scripting.FileSystemObject")
Set objShell = CreateObject("WScript.Shell")

scriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
pythonw = scriptDir & "\venv\Scripts\pythonw.exe"
mainPy = scriptDir & "\main.py"

If Not objFSO.FileExists(pythonw) Then
    MsgBox "pythonw.exe not found at:" & vbCrLf & pythonw & vbCrLf & vbCrLf & _
           "Please run install.bat first.", vbCritical, "Voice Typer"
    WScript.Quit 1
End If

If Not objFSO.FileExists(mainPy) Then
    MsgBox "main.py not found at:" & vbCrLf & mainPy, vbCritical, "Voice Typer"
    WScript.Quit 1
End If

' Run pythonw.exe main.py
'   0 = hide window
'   False = do not wait
objShell.CurrentDirectory = scriptDir
objShell.Run """" & pythonw & """ """ & mainPy & """", 0, False
