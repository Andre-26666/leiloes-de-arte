@echo off
chcp 65001 > nul
title Agendador — Catálogo de Pinturas

set PYTHON=C:\Users\andre\AppData\Local\Python\bin\python.exe
set SCRIPT=%~dp0catalogo_leiloesbr.py
set TASK_NAME=CatalogoPinturas_LeiloesBR

echo Criando tarefa agendada: %TASK_NAME%
echo Execucao: 08:00 e 20:00 todos os dias
echo.

schtasks /delete /tn "%TASK_NAME%_Manha" /f >nul 2>&1
schtasks /delete /tn "%TASK_NAME%_Noite" /f >nul 2>&1

schtasks /create /tn "%TASK_NAME%_Manha" /tr "\"%PYTHON%\" \"%SCRIPT%\"" /sc daily /st 08:00 /f /rl highest
schtasks /create /tn "%TASK_NAME%_Noite" /tr "\"%PYTHON%\" \"%SCRIPT%\"" /sc daily /st 20:00 /f /rl highest

if %errorlevel% == 0 (
    echo.
    echo [OK] Tarefas criadas com sucesso!
    echo      Executa todo dia as 08:00 e as 20:00
    echo      Para cancelar: execute CANCELAR_ATUALIZACAO.bat
) else (
    echo.
    echo [ERRO] Execute este arquivo como Administrador:
    echo        Botao direito - Executar como administrador
)

echo.
pause
