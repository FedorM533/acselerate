"""Тесты машины состояний: каждое правило раздела 8 ТЗ."""
import pytest

from focusfarm.clock import FakeClock
from focusfarm.session.state_machine import (
    DISTRACTED, FOCUS, MAYBE_DISTRACTED, NOTEBOOK, PAUSED, PHONE_OUT,
    Inputs, StateMachine,
)

TH = {
    "phone_grace_s": 30, "distraction_confirm_s": 30, "neutral_limit_s": 90,
    "idle_limit_s": 180, "maybe_to_distracted_s": 180, "recover_s": 5,
    "notebook_max_min": 45, "notebook_answer_s": 120,
}


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def sm():
    return StateMachine(TH)


def run(sm, clock, seconds, **inputs):
    """Тикает раз в секунду `seconds` раз с одинаковыми входами."""
    inp = Inputs(**inputs)
    state = sm.state
    for _ in range(seconds):
        state = sm.update(inp, clock.now())
        clock.advance(1)
    return state


# ---------- Правило 1: пауза ----------

def test_paused_wins_over_everything(sm, clock):
    assert run(sm, clock, 1, paused=True, phone_docked=False, category="distraction") == PAUSED


def test_resume_after_pause_goes_to_focus(sm, clock):
    run(sm, clock, 3, paused=True)
    assert run(sm, clock, 1, category="work") == FOCUS


def test_pause_resets_distraction_timer(sm, clock):
    run(sm, clock, 20, category="distraction")
    run(sm, clock, 5, paused=True)
    # После паузы отсчёт 30 с начинается заново.
    assert run(sm, clock, 20, category="distraction") == MAYBE_DISTRACTED


# ---------- Правило 2: телефон ----------

def test_phone_grace_keeps_previous_state(sm, clock):
    run(sm, clock, 10, category="work")
    assert run(sm, clock, 29, phone_docked=False) == FOCUS


def test_phone_out_after_grace(sm, clock):
    assert run(sm, clock, 31, phone_docked=False) == PHONE_OUT


def test_phone_out_beats_distraction(sm, clock):
    assert run(sm, clock, 60, phone_docked=False, category="distraction") == PHONE_OUT


def test_phone_back_within_grace_no_consequences(sm, clock):
    run(sm, clock, 20, phone_docked=False)
    assert run(sm, clock, 1, phone_docked=True) == FOCUS
    # Льготный период начинается заново при следующем вынимании.
    assert run(sm, clock, 20, phone_docked=False) == FOCUS


# ---------- Правило 3: развлечения ----------

def test_short_distraction_is_maybe(sm, clock):
    assert run(sm, clock, 10, category="distraction") == MAYBE_DISTRACTED


def test_long_distraction_is_distracted(sm, clock):
    assert run(sm, clock, 31, category="distraction") == DISTRACTED


def test_distraction_beats_notebook(sm, clock):
    assert run(sm, clock, 31, category="distraction", notebook_mode=True) == DISTRACTED


# ---------- Правило 4: тетрадь ----------

def test_notebook_ignores_idle(sm, clock):
    assert run(sm, clock, 10, category="neutral", idle_seconds=1000, notebook_mode=True) == NOTEBOOK


def test_notebook_limit_asks_presence(sm, clock):
    state = run(sm, clock, 45 * 60 + 1, notebook_mode=True, idle_seconds=999)
    assert state == NOTEBOOK
    assert sm.ask_presence is True


def test_notebook_no_answer_becomes_maybe(sm, clock):
    state = run(sm, clock, 45 * 60 + 121, notebook_mode=True, idle_seconds=999)
    assert state == MAYBE_DISTRACTED


def test_notebook_presence_confirmed_resets_limit(sm, clock):
    run(sm, clock, 45 * 60 + 60, notebook_mode=True)
    sm.confirm_presence(clock.now())
    assert sm.ask_presence is False
    assert run(sm, clock, 200, notebook_mode=True) == NOTEBOOK
    assert sm.ask_presence is False


# ---------- Правило 5: работа ----------

def test_work_with_input_is_focus(sm, clock):
    assert run(sm, clock, 100, category="work", idle_seconds=3) == FOCUS


# ---------- Правило 6: нейтральное окно / простой ----------

def test_neutral_short_is_focus(sm, clock):
    assert run(sm, clock, 89, category="neutral") == FOCUS


def test_neutral_long_is_maybe(sm, clock):
    assert run(sm, clock, 91, category="neutral") == MAYBE_DISTRACTED


def test_idle_long_in_work_is_maybe(sm, clock):
    assert run(sm, clock, 1, category="work", idle_seconds=180) == MAYBE_DISTRACTED


def test_maybe_too_long_becomes_distracted(sm, clock):
    # 90 с до MAYBE + 180 с в MAYBE → DISTRACTED
    assert run(sm, clock, 91 + 179, category="neutral") == MAYBE_DISTRACTED
    assert run(sm, clock, 2, category="neutral") == DISTRACTED


def test_idle_maybe_escalates(sm, clock):
    assert run(sm, clock, 181, category="work", idle_seconds=500) == DISTRACTED


# ---------- Правило 7: иначе фокус ----------

def test_unknown_category_defaults_to_focus(sm, clock):
    assert run(sm, clock, 5, category="unknown") == FOCUS


# ---------- Гистерезис ----------

def test_recover_from_distracted_needs_recover_s(sm, clock):
    run(sm, clock, 40, category="distraction")
    assert sm.state == DISTRACTED
    assert run(sm, clock, 4, category="work") == DISTRACTED
    assert run(sm, clock, 2, category="work") == FOCUS


def test_recover_from_phone_out(sm, clock):
    run(sm, clock, 40, phone_docked=False)
    assert run(sm, clock, 3, category="work") == PHONE_OUT
    assert run(sm, clock, 3, category="work") == FOCUS


def test_recover_from_maybe(sm, clock):
    run(sm, clock, 5, category="distraction")
    assert sm.state == MAYBE_DISTRACTED
    assert run(sm, clock, 2, category="work") == MAYBE_DISTRACTED
    assert run(sm, clock, 4, category="work") == FOCUS


def test_hysteresis_interrupted_by_bad_signal(sm, clock):
    run(sm, clock, 40, category="distraction")
    run(sm, clock, 4, category="work")
    # «Хорошие» секунды прервались: секунда YouTube — снова «кажется, отвлёкся»,
    # и отсчёт recover_s начинается заново.
    assert run(sm, clock, 1, category="distraction") == MAYBE_DISTRACTED
    assert run(sm, clock, 4, category="work") == MAYBE_DISTRACTED
    assert run(sm, clock, 2, category="work") == FOCUS


def test_no_hysteresis_for_focus_to_notebook(sm, clock):
    run(sm, clock, 5, category="work")
    assert run(sm, clock, 1, category="work", notebook_mode=True) == NOTEBOOK
