@echo off
chcp 65001 >nul
title Larsson Line Market Scanner & Top 15 Cockpit
cls
echo ======================================================================
echo   🚀 СТАРТИРАНЕ НА LARSSON LINE MARKET SCANNER & ТОП 15 РОТАЦИЯ
echo ======================================================================
echo.
echo [1/2] Генериране на пресни пазарни данни и преизчисляване на Топ 15...
.\.venv\Scripts\python.exe src\main.py --export-dashboard

echo.
echo [2/2] Стартиране на локалния визуален кокпит...
echo Таблото ще се отвори автоматично на http://localhost:8000
echo За спиране затворете този прозорец.
echo.
start http://localhost:8000
.\.venv\Scripts\python.exe -m http.server 8000 --directory dashboard
