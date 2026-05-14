@echo off
cd /d "%~dp0"
if exist "assets\app.ico" (
  pyinstaller --noconfirm --onefile --windowed --name InstaLight --icon=assets\app.ico gui.py
) else (
  pyinstaller --noconfirm --onefile --windowed --name InstaLight gui.py
)
