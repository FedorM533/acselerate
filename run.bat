@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv (
    echo Создаю виртуальное окружение...
    py -3 -m venv .venv || python -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt
)
.venv\Scripts\python -m focusfarm %*
