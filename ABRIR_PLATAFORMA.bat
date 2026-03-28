@echo off
chcp 65001 > nul
title Plataforma de Pinturas — LeilõesBR
cd /d "%~dp0"
echo Iniciando plataforma...
echo Acesse: http://localhost:8501
echo.
echo Para fechar: Ctrl+C nesta janela
echo.
C:\Users\andre\AppData\Local\Python\bin\python.exe -m streamlit run plataforma.py --server.headless false
pause
