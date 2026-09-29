@echo off
chcp 65001 >nul
rem Демо для защиты: ускорение x30, чистая ферма в data\demo.db (основная ферма не трогается).
cd /d "%~dp0"
call run.bat --demo 30 --db data\demo.db --fresh %*
