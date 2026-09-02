@echo off
REM ==========================================================================
REM  Installe Odoo saas~19.2 sur ce PC Windows.
REM  Le script PowerShell demande lui-meme l'elevation des privileges (UAC)
REM  et poursuit dans une console administrateur.
REM ==========================================================================
setlocal
title Installation d'Odoo saas~19.2
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Odoo.ps1" %*
echo.
pause
endlocal
