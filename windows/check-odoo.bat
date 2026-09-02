@echo off
REM ==========================================================================
REM  Diagnostic : verifie Python, PostgreSQL, wkhtmltopdf, le venv et la
REM  configuration, sans rien installer ni modifier.
REM ==========================================================================
setlocal
title Diagnostic de l'installation Odoo
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Odoo.ps1" -CheckOnly %*
echo.
pause
endlocal
