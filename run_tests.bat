@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Run setup_windows.bat first.& pause& exit /b 1)
call ".venv\Scripts\activate.bat"
python manage.py test cloud -v 2
pause
