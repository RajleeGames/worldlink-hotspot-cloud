@echo off
setlocal
cd /d "%~dp0"
echo ==============================================
echo  WORLDLINK HOTSPOT CLOUD - FIRST TIME SETUP
echo ==============================================
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv || goto :error
)
call ".venv\Scripts\activate.bat" || goto :error
python -m pip install --upgrade pip || goto :error
python -m pip install -r requirements.txt || goto :error
python scripts\init_env.py || goto :error
python manage.py migrate || goto :error
python manage.py check || goto :error
echo.
echo Setup complete. Run create_admin.bat to create a platform admin.
echo Then run run_windows.bat and open http://127.0.0.1:8000/
pause
exit /b 0
:error
echo.
echo Setup failed. Check your network, Python installation and error messages.
pause
exit /b 1
