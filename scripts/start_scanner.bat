@echo off
title Larsson Line Scanner Background Service
cd /d "%~dp0\.."
echo Starting Larsson Line Scanner Scheduler...
call .venv\Scripts\activate.bat
python src\main.py --scheduler
