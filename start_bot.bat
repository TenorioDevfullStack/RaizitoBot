@echo off
title RaizitoBot
echo ================================
echo  Iniciando RaizitoBot...
echo ================================
cd /d "%~dp0"

:loop
echo [%date% %time%] Iniciando bot...
.venv\Scripts\python.exe main.py
echo [%date% %time%] Bot encerrado. Reiniciando em 5 segundos...
timeout /t 5 /nobreak
goto loop
