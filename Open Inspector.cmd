@echo off
python -B "%~dp0inspector.py"
if errorlevel 1 pause
