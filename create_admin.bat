@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Run setup_windows.bat first.& pause& exit /b 1)
call ".venv\Scripts\activate.bat"
echo IMPORTANT: use your EMAIL ADDRESS as the Username.
python manage.py createsuperuser
pause
