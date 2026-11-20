@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Primero sigue la instalacion indicada en README.md.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -X utf8 iniciar.py %*
pause
