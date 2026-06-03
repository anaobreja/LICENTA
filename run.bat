@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1 (
  py -3 "%~dp0run.py" %*
  exit /b %ERRORLEVEL%
)
where python >nul 2>&1 (
  python "%~dp0run.py" %*
  exit /b %ERRORLEVEL%
)

echo Nu s-a gasit Python. Instaleaza Python 3 de la https://www.python.org/downloads/
echo Bifeaza "Add python.exe to PATH" la instalare.
exit /b 1
