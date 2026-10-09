@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m orbit
) else (
    if exist ".deps\PySide6" set "PYTHONPATH=%CD%\.deps;%PYTHONPATH%"
    python -m orbit
)
