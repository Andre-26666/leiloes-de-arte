@echo off
chcp 65001 > nul
title Cancelar Agendamento

set TASK_NAME=CatalogoPinturas_LeiloesBR

schtasks /delete /tn "%TASK_NAME%_Manha" /f
schtasks /delete /tn "%TASK_NAME%_Noite" /f

echo.
echo [OK] Atualizacao automatica cancelada.
echo.
pause
