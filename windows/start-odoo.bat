@echo off
REM ==========================================================================
REM  Demarre le serveur Odoo et ouvre le navigateur.
REM  Fermez cette fenetre ou faites Ctrl+C pour arreter le serveur.
REM ==========================================================================
setlocal
title Odoo saas~19.2
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Odoo.ps1" -Open %*
echo.
pause
endlocal
