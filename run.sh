#!/usr/bin/env sh
# Запуск «Фокус-пруда» на Linux и macOS. При первом запуске создаёт .venv и ставит зависимости.
cd "$(dirname "$0")"

if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    echo "Нужен Python 3.11 или новее (python3). Debian/Ubuntu: sudo apt install python3"
    exit 1
fi

# Метка .venv/.ready появляется только после успешной установки: оборванная установка повторится.
if [ ! -f .venv/.ready ]; then
    echo "Создаю виртуальное окружение..."
    rm -rf .venv
    if ! python3 -m venv .venv 2>/dev/null; then
        # В Debian/Ubuntu модуль venv с pip — отдельный пакет python3-venv. Без sudo
        # создаём окружение без pip и ставим pip официальным установщиком get-pip.py.
        echo "В системе нет python3-venv (лучше: sudo apt install python3-venv). Ставлю pip сам..."
        rm -rf .venv
        python3 -m venv --without-pip .venv || exit 1
        if command -v curl >/dev/null; then
            curl -sSfL https://bootstrap.pypa.io/get-pip.py -o .venv/get-pip.py
        else
            wget -qO .venv/get-pip.py https://bootstrap.pypa.io/get-pip.py
        fi
        .venv/bin/python .venv/get-pip.py -q || { echo "Не удалось поставить pip (нет интернета?)"; exit 1; }
    fi
    .venv/bin/python -m pip install --retries 10 -r requirements.txt \
        || { echo "Не удалось установить зависимости (нет интернета?). Запустите run.sh ещё раз."; exit 1; }
    touch .venv/.ready
fi
.venv/bin/python -m focusfarm "$@"
