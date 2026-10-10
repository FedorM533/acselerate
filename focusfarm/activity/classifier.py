"""Классификатор: (имя процесса, заголовок окна) → категория.

Заголовок окна используется только здесь, в памяти, и никуда не сохраняется.
"""
from pathlib import Path

from focusfarm.config import CONFIG_DIR, ConfigError, load_yaml, save_yaml

CATEGORIES = ("work", "neutral", "distraction")
RULES_PATH = CONFIG_DIR / "rules.yaml"


def normalize_domain(value) -> str:
    """'https://www.YouTube.com/watch?v=1' → 'youtube.com'."""
    text = str(value).strip().lower()
    text = text.split("://", 1)[-1]
    text = text.split("/", 1)[0].split("?", 1)[0].split(":", 1)[0].strip(".")
    return text[4:] if text.startswith("www.") else text


def validate_rules(data: dict) -> dict:
    """Проверяет структуру правил и приводит слова к нижнему регистру."""
    default = data.get("default", "neutral")
    if default not in CATEGORIES:
        raise ConfigError(f"default должен быть одним из {CATEGORIES}")
    clean = []
    for i, rule in enumerate(data.get("rules") or [], start=1):
        if rule.get("category") not in CATEGORIES:
            raise ConfigError(f"Правило {i}: категория должна быть одной из {CATEGORIES}")
        item = {"category": rule["category"]}
        for key in ("process", "title_contains", "domains"):
            words = rule.get(key) or []
            if not isinstance(words, list):
                raise ConfigError(f"Правило {i}: {key} должен быть списком")
            if key == "domains":    # сайты для расширения браузера: только адрес, без https:// и пути
                words = [normalize_domain(w) for w in words]
            words = [str(w).strip().lower() for w in words if str(w).strip()]
            if words:
                item[key] = list(dict.fromkeys(words))
        if not any(key in item for key in ("process", "title_contains", "domains")):
            raise ConfigError(f"Правило {i}: нужен список process, title_contains или domains")
        clean.append(item)
    return {"default": default, "rules": clean}


def load_rules(path: Path = RULES_PATH) -> dict:
    return validate_rules(load_yaml(path))


def save_rules(data: dict, path: Path = RULES_PATH) -> dict:
    data = validate_rules(data)
    save_yaml(path, data)
    return data


class Classifier:
    def __init__(self, rules: dict):
        self.set_rules(rules)

    def set_rules(self, rules: dict):
        self.rules = validate_rules(rules)

    def classify(self, process_name: str, window_title: str = "") -> str:
        process = (process_name or "").lower()
        title = (window_title or "").lower()
        for rule in self.rules["rules"]:
            if process and process in rule.get("process", []):
                return rule["category"]
            if any(word in title for word in rule.get("title_contains", [])):
                return rule["category"]
        return self.rules["default"]
