"""Звуки-«возвращалки»: чем дольше отвлекаешься, тем настойчивее сигнал.

Звуки рисуем сами (без аудиофайлов) и проигрываем системным плеером компьютера, поэтому они
слышны, даже если вкладка с интерфейсом закрыта. Четыре уровня:
1 — тихий мягкий «дзынь», 2 — бодрое восходящее арпеджио, 3 — настойчивый двойной сигнал,
4 — тревожная «сирена» (самая злая, но не громче остальных: растёт резкость, а не громкость).
"""
import io
import logging
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import wave
from pathlib import Path

log = logging.getLogger(__name__)

RATE = 22050
LEVELS = 4

# Нота: (частота Гц, начало с, длительность с). Форма волны и «зубчатость» задаются на уровень.
# shape: sine — мягкий, tri — чуть ярче, square — резкий.
_PATTERNS = {
    1: {"shape": "sine", "notes": [(523, 0.00, 0.35), (659, 0.28, 0.55)]},
    2: {"shape": "tri", "notes": [(523, 0.00, 0.16), (659, 0.14, 0.16), (784, 0.28, 0.16), (1047, 0.42, 0.45)]},
    3: {"shape": "tri", "notes": [(880, 0.00, 0.14), (880, 0.20, 0.14), (880, 0.40, 0.14),
                                  (698, 0.62, 0.14), (698, 0.82, 0.14), (698, 1.02, 0.30)]},
    4: {"shape": "square", "notes": [(f, i * 0.22, 0.2) for i, f in enumerate([1000, 700] * 4)]},
}


def _wave_value(shape: str, phase: float) -> float:
    """phase — доля периода, 0..1."""
    if shape == "sine":
        return math.sin(2 * math.pi * phase)
    if shape == "tri":
        return 4 * abs(phase - 0.5) - 1
    return 1.0 if phase < 0.5 else -1.0


def render_wav(level: int, volume: float = 0.6) -> bytes:
    """Возвращает готовый WAV (моно, 16 бит) для уровня 1..4."""
    level = max(1, min(LEVELS, int(level)))
    volume = max(0.05, min(1.0, float(volume)))
    pattern = _PATTERNS[level]
    total = max(start + dur for _, start, dur in pattern["notes"]) + 0.05
    samples = [0.0] * int(total * RATE)
    # Резкий уровень делаем тише по амплитуде: у прямоугольной волны громкость субъективно выше.
    amp = volume * (0.35 if pattern["shape"] == "square" else 0.8)
    for freq, start, dur in pattern["notes"]:
        first, count = int(start * RATE), int(dur * RATE)
        attack = max(1, int(0.015 * RATE))
        for i in range(count):
            if first + i >= len(samples):
                break
            env = min(1.0, i / attack) * (1.0 - i / count) ** 1.5   # быстрый вход, плавное затухание
            samples[first + i] += amp * env * _wave_value(pattern["shape"], (freq * i / RATE) % 1.0)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767)) for s in samples))
    return buf.getvalue()


def _linux_player() -> list[str] | None:
    for cmd in (["paplay"], ["pw-play"], ["aplay", "-q"], ["afplay"]):
        if shutil.which(cmd[0]):
            return cmd
    return None


def play_system(level: int, volume: float = 0.6) -> bool:
    """Проигрывает звук системным плеером, не блокируя программу. True — если запустили."""
    try:
        data = render_wav(level, volume)
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_ASYNC)
            return True
        player = _linux_player()
        if player is None:
            return False
        threading.Thread(target=_play_file, args=(player, data), daemon=True).start()
        return True
    except Exception as exc:   # звук — не повод ронять программу
        log.warning("Не получилось проиграть системный звук: %s", exc)
        return False


def _play_file(player: list[str], data: bytes):
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(data)
            path = Path(f.name)
        subprocess.run([*player, str(path)], timeout=15, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        log.warning("Плеер не сработал: %s", exc)
    finally:
        if path:
            path.unlink(missing_ok=True)
