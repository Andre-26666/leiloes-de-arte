@echo off
chcp 65001 > nul
title Catálogo de Pinturas — LeilõesBR
cd /d "%~dp0"
python catalogo_leiloesbr.py
