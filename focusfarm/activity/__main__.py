"""Консольная проверка монитора: python -m focusfarm.activity

Раз в секунду печатает простой, процесс и категорию. Заголовок окна
выводится только на экран и нигде не сохраняется.
"""
import argparse
import time

from focusfarm import fix_console_encoding
from focusfarm.activity.classifier import Classifier, load_rules
from focusfarm.activity.monitor import SafeMonitor, create_monitor


def main():
    fix_console_encoding()
    parser = argparse.ArgumentParser(description="Проверка монитора активности")
    parser.add_argument("--count", type=int, default=0, help="сколько раз напечатать (0 — бесконечно)")
    args = parser.parse_args()

    monitor = SafeMonitor(create_monitor())
    classifier = Classifier(load_rules())
    print(f"Монитор: {monitor.name}. Ctrl+C — выход.")
    if not monitor.available:
        print("Внимание: монитор активности недоступен, работает только датчик телефона.")
    printed = 0
    try:
        while args.count == 0 or printed < args.count:
            s = monitor.sample()
            category = classifier.classify(s.process_name, s.window_title)
            print(f"простой {s.idle_seconds:6.1f} с | {category:11} | "
                  f"{s.process_name:20} | {s.window_title[:60]}", flush=True)
            printed += 1
            time.sleep(1)
    except KeyboardInterrupt:
        print("Пока!")


if __name__ == "__main__":
    main()
