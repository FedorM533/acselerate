"""Загрузка и проверка конфигов из папки config/."""
import copy
import os
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

MODES = ("normal", "dev", "demo")
PHONE_SOURCES = ("auto", "usb", "serial", "mock")   # как определяем «телефон подключён»
STRICTNESS_LEVELS = ("soft", "hard")                # мягкая защита / жёсткая блокировка
PROTECTION_TARGETS = ("pc", "phone", "both")        # где защищаем

# Пороги, которые обязаны быть в settings.yaml, и их допустимые границы.
THRESHOLD_KEYS = [
    "phone_grace_s", "distraction_confirm_s", "neutral_limit_s", "idle_limit_s",
    "maybe_to_distracted_s", "recover_s", "notebook_max_min", "notebook_answer_s",
]


class ConfigError(ValueError):
    """Ошибка в конфиге — с понятным текстом для человека."""


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def deep_merge(base: dict, extra: dict) -> dict:
    """Рекурсивно накладывает extra поверх base (base не меняется)."""
    result = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def validate_settings(s: dict) -> dict:
    """Проверяет настройки. Бросает ConfigError, если что-то не так."""
    if s.get("mode", "normal") not in MODES:
        raise ConfigError(f"mode должен быть одним из {MODES}")
    th = s.get("thresholds", {})
    for key in THRESHOLD_KEYS:
        value = th.get(key)
        if not isinstance(value, (int, float)) or value < 0:
            raise ConfigError(f"thresholds.{key} должен быть неотрицательным числом")
    speed = s.get("demo_speed", 1)
    if not isinstance(speed, (int, float)) or not 1 <= speed <= 1000:
        raise ConfigError("demo_speed должен быть числом от 1 до 1000")
    for section in ("ui", "rewards", "protection"):
        if not isinstance(s.get(section, {}), dict):
            raise ConfigError(f"{section} должен быть набором настроек")
    protection = s.get("protection", {})
    if protection.get("strictness", "soft") not in STRICTNESS_LEVELS:
        raise ConfigError(f"protection.strictness должен быть одним из {STRICTNESS_LEVELS}")
    if protection.get("targets", "pc") not in PROTECTION_TARGETS:
        raise ConfigError(f"protection.targets должен быть одним из {PROTECTION_TARGETS}")
    ui = s.get("ui", {})
    if "pond_fish_max" in ui:
        n = ui["pond_fish_max"]
        if isinstance(n, bool) or not isinstance(n, int) or not 0 <= n <= 60:
            raise ConfigError("ui.pond_fish_max должен быть целым числом от 0 до 60")
    rewards = s.get("rewards", {})
    if "enabled" in rewards and not isinstance(rewards["enabled"], bool):
        raise ConfigError("rewards.enabled должен быть true или false")
    source = s.get("device", {}).get("phone_source", "auto")
    if source not in PHONE_SOURCES:
        raise ConfigError(f"device.phone_source должен быть одним из {PHONE_SOURCES}")
    length = s.get("session", {}).get("default_length_min", 25)
    if not isinstance(length, (int, float)) or length <= 0:
        raise ConfigError("session.default_length_min должен быть больше нуля")
    for crop_id, crop in s.get("game", {}).get("crops", {}).items():
        for key in ("focus_min", "coins", "price"):
            if not isinstance(crop.get(key), (int, float)) or crop[key] < 0:
                raise ConfigError(f"game.crops.{crop_id}.{key} должен быть числом ≥ 0")
    return s


def load_settings(config_dir: Path = CONFIG_DIR, overrides: dict | None = None) -> dict:
    """Читает settings.yaml, накладывает изменения из интерфейса и
    переменную окружения FOCUSFARM_DEMO_SPEED."""
    settings = deep_merge(load_yaml(config_dir / "settings.yaml"), overrides or {})
    env_speed = os.environ.get("FOCUSFARM_DEMO_SPEED")
    if env_speed:
        settings["mode"] = "demo"
        settings["demo_speed"] = float(env_speed)
    return validate_settings(settings)


def speed_of(settings: dict) -> float:
    """Во сколько раз ускорено время (1 — обычный режим)."""
    return float(settings.get("demo_speed", 1)) if settings.get("mode") == "demo" else 1.0
