#!/usr/bin/env sh
# Демо для защиты: ускорение x30, чистая ферма в data/demo.db (основная ферма не трогается).
cd "$(dirname "$0")"
./run.sh --demo 30 --db data/demo.db --fresh "$@"
