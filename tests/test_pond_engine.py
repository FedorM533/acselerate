"""Движок пруда: все тест-векторы из carpo-pond-kit (config/progress_test_vectors.json)."""
import json
from pathlib import Path

import pytest

from focusfarm.pond.engine import compute_pond, merge_unlocked, percent_ceil

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config" / "pond" / "progression.json").read_text(encoding="utf-8"))
VECTORS = json.loads((Path(__file__).parent / "data" / "progress_test_vectors.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["name"])
def test_vector(case):
    result = compute_pond(case["input"], CONFIG)
    exp = case["expected"]
    assert result["drops"] == exp["drops"]
    assert result["focusDays"] == exp["focusDays"]
    assert result["stage"] == exp["stage"]
    assert result["unlocked"] == exp["unlocked"]
    assert result["sessions"] == exp["sessions"]


def test_there_are_19_vectors():
    assert len(VECTORS["cases"]) == 19


def test_percent_is_integer_math():
    assert percent_ceil(45, 20) == 9          # 0.2 * 45 в float дало бы 10
    assert percent_ceil(0, 20) == 0


def test_unlocked_never_shrinks():
    assert merge_unlocked(["a", "b"], ["b"]) == ["a", "b"]
    assert compute_pond([], CONFIG, ["first_pad"])["unlocked"] == ["first_pad"]
