@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Run setup_windows.bat first.& pause& exit /b 1)
call ".venv\Scripts\activate.bat"
echo Open http://127.0.0.1:8000/
python manage.py runserver 127.0.0.1:8000
pause
