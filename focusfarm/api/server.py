"""Локальный веб-сервер: REST + WebSocket + статика интерфейса.

Слушает только 127.0.0.1 (см. __main__.py). Раз в секунду вызывает
manager.tick() и рассылает состояние всем открытым вкладкам по /ws.
"""
import asyncio
import contextlib
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from focusfarm.activity.classifier import RULES_PATH, save_rules
from focusfarm.activity.monitor import create_monitor
from focusfarm.blocker.apps import AppBlocker
from focusfarm.config import ConfigError, deep_merge, load_settings
from focusfarm.device.dock import Dock
from focusfarm.game.engine import GameError
from focusfarm.phone.lan import LanServer, NoLan
from focusfarm.phone.qr import qr_svg
from focusfarm.session.manager import SessionManager
from focusfarm.session.stats import compute_stats
from focusfarm.storage.db import DEFAULT_PATH, Database
from focusfarm.tools import ext_install

log = logging.getLogger(__name__)
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# Какие разделы настроек можно менять из интерфейса.
EDITABLE_SETTINGS = ("mode", "demo_speed", "thresholds", "session", "sound", "device", "ui", "rewards",
                     "protection", "network", "pomodoro")


# ---------- тела запросов ----------

class StartBody(BaseModel):
    plot: list[int] | None = None
    crop: str | None = None
    length_min: float | None = None
    without_phone: bool = False


# Что можно менять в строгой сессии без пароля: внешний вид и звук.
SAFE_IN_STRICT = {"ui", "sound", "rewards"}


class NotebookBody(BaseModel):
    on: bool


class PasswordBody(BaseModel):
    password: str | None = None


class NewPasswordBody(BaseModel):
    new: str
    old: str | None = None


class PlotBody(BaseModel):
    x: int
    y: int


class HarvestBody(BaseModel):
    x: int
    y: int
    name: str = ""


class BuyBody(BaseModel):
    item: str


class PhoneBody(BaseModel):
    docked: bool


class UsbPairBody(BaseModel):
    id: str
    name: str = ""


class CategoryBody(BaseModel):
    category: str | None = None


# ---------- сборка приложения ----------

def build_manager(db_path=DEFAULT_PATH, cli_overrides: dict | None = None, **kwargs) -> SessionManager:
    """Создаёт менеджер с настоящими компонентами."""
    db = Database(db_path)
    settings = load_settings(overrides=deep_merge(db.get_overrides(), cli_overrides or {}))
    kwargs.setdefault("monitor", create_monitor())
    if "phone" not in kwargs and "device" not in kwargs:
        # Одна подставка = и датчик, и свет/звук; без порта — виртуальная.
        dock = Dock(settings.get("device", {}).get("serial_port", ""))
        kwargs["phone"] = kwargs["device"] = dock
    kwargs.setdefault("blocker", AppBlocker())
    manager = SessionManager(settings, db, **kwargs)
    manager.cli_overrides = cli_overrides or {}
    return manager


def create_app(manager: SessionManager | None = None, run_loop: bool = True,
               rules_path: Path = RULES_PATH, lan=None) -> FastAPI:
    manager = manager or build_manager()
    # Сервер для телефона по Wi-Fi: настоящий только в рабочем запуске (в тестах — заглушка).
    lan = lan if lan is not None else (LanServer(manager) if run_loop else NoLan())
    clients: set[WebSocket] = set()

    async def broadcast():
        if not clients:
            manager.take_events()   # никто не слушает — события не копим
            return
        payload = {**manager.snapshot(), "events": manager.take_events()}
        for ws in list(clients):
            try:
                await ws.send_json(payload)
            except Exception:
                clients.discard(ws)

    async def tick_loop():
        n = 0
        while True:
            n += 1
            try:
                manager.tick()
                if n % 30 == 0:
                    lan.sync(manager.settings)    # поднимет связь, если порт освободился или сменился адрес ПК
            except Exception:
                log.exception("Ошибка в тике — продолжаем работу")
            await broadcast()
            await asyncio.sleep(1)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(tick_loop()) if run_loop else None
        lan.sync(manager.settings)
        yield
        lan.stop()
        if task:
            task.cancel()
        closer = getattr(manager, "close", None)
        if closer:
            closer()

    app = FastAPI(title="Фокус-пруд", lifespan=lifespan)
    app.state.manager = manager

    @app.exception_handler(GameError)
    async def game_error(request: Request, exc: GameError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(ConfigError)
    async def config_error(request: Request, exc: ConfigError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    def require_dev():
        if not manager.dev_tools:
            raise HTTPException(403, "Доступно только в режимах dev и demo")

    # ---------- состояние и сессия ----------

    @app.get("/api/hello")
    def hello():
        return {"message": "Hello, Фокус-пруд!"}

    @app.get("/api/state")
    def get_state():
        return manager.snapshot()

    @app.post("/api/session/start")
    def session_start(body: StartBody):
        return manager.start_session(body.plot, body.crop, body.length_min, body.without_phone)

    @app.post("/api/session/pause")
    def session_pause(body: PasswordBody | None = None):
        if manager.on_break():      # отдыхать пароль не нужен: паузу ставить незачем
            raise HTTPException(400, "Сейчас перерыв: пауза не нужна, отдыхай ☕")
        manager.require_unlock(body.password if body else None)
        manager.pause()
        return manager.snapshot()

    @app.post("/api/session/resume")
    def session_resume():
        manager.resume()
        return manager.snapshot()

    @app.post("/api/session/break/skip")
    def session_break_skip():
        return manager.skip_break()

    @app.post("/api/session/notebook")
    def session_notebook(body: NotebookBody):
        manager.set_notebook(body.on)
        return manager.snapshot()

    @app.post("/api/session/presence")
    def session_presence():
        manager.confirm_presence()
        return manager.snapshot()

    @app.post("/api/session/end")
    def session_end(body: PasswordBody | None = None):
        manager.require_unlock(body.password if body else None)
        manager.end_session("manual")
        return manager.snapshot()

    # ---------- ферма и магазин ----------

    @app.post("/api/farm/harvest")
    def farm_harvest(body: HarvestBody):
        return manager.harvest(body.x, body.y, body.name)

    @app.post("/api/farm/weed")
    def farm_weed(body: PlotBody):
        manager.weed(body.x, body.y)
        return manager.snapshot()

    @app.post("/api/shop/buy")
    def shop_buy(body: BuyBody):
        manager.buy(body.item)
        return manager.snapshot()

    # ---------- коллекция, задания и ачивки ----------

    @app.get("/api/collection")
    def collection():
        summary = manager.db.collection_summary()
        species = [{"id": c.id, "name": c.name, "count": summary.get(c.id, {}).get("count", 0),
                    "best_stars": summary.get(c.id, {}).get("best_stars", 0),
                    "unlocked": c.id in manager.game.unlocks}
                   for c in manager.game.crops.values()]
        return {"fish": manager.db.list_fish(), "species": species}

    @app.get("/api/rewards")
    def rewards():
        return manager.rewards.view()

    @app.post("/api/rewards/seen")
    def rewards_seen():
        manager.rewards.mark_seen()
        return manager.snapshot()

    # ---------- статистика ----------

    @app.get("/api/stats")
    def stats(range: str = "day"):  # noqa: A002 — имя параметра задано в ТЗ
        if range not in ("day", "week"):
            raise HTTPException(400, "range должен быть day или week")
        return compute_stats(manager.db, manager.clock.now(), range)

    # ---------- настройки и правила ----------

    @app.get("/api/settings")
    def get_settings():
        return {k: manager.settings.get(k) for k in EDITABLE_SETTINGS}

    @app.put("/api/settings")
    def put_settings(body: dict):
        password = body.pop("password", None)
        unknown = set(body) - set(EDITABLE_SETTINGS)
        if unknown:
            raise HTTPException(400, f"Эти настройки нельзя менять: {', '.join(sorted(unknown))}")
        if set(body) - SAFE_IN_STRICT:        # в строгой сессии защиту, режим и скорость без пароля не менять
            manager.require_unlock(password)
        overrides = deep_merge(manager.db.get_overrides(), body)
        # Проверяем до сохранения: при ошибке ConfigError → 400, база не меняется.
        settings = load_settings(overrides=deep_merge(overrides, getattr(manager, "cli_overrides", {})))
        manager.db.set_overrides(overrides)
        manager.apply_settings(settings)
        lan.sync(settings)       # включили или выключили связь с телефоном
        return get_settings()

    @app.get("/api/strict")
    def strict_status():
        return manager.strict_view()

    @app.put("/api/strict/password")
    def strict_set_password(body: NewPasswordBody):
        manager.set_password(body.new, body.old)
        return manager.strict_view()

    @app.delete("/api/strict/password")
    def strict_clear_password(body: PasswordBody | None = None):
        manager.clear_password(body.password if body else None)
        return manager.strict_view()

    @app.get("/api/protection/sites")
    def protection_sites():
        """Для расширения браузера: что блокировать и надо ли это прямо сейчас."""
        return manager.sites_view()

    # ---------- установка расширения ----------

    @app.get("/api/extension/browsers")
    def extension_browsers():
        return {"browsers": [{"key": key, "name": ext_install.BROWSERS[key][0]}
                             for key in ext_install.installed_browsers()],
                "connected": manager.extension_connected()}

    @app.post("/api/extension/install")
    def extension_install(body: dict):
        browser = body.get("browser")
        if browser not in ext_install.BROWSERS:
            raise HTTPException(400, "Неизвестный браузер")
        try:
            return ext_install.install(browser)
        except OSError as exc:
            raise HTTPException(500, f"Не удалось подготовить расширение: {exc}")

    # ---------- телефон по Wi-Fi ----------

    @app.get("/api/wifi/status")
    def wifi_status():
        address = lan.address()
        return {
            "enabled": bool(manager.settings.get("network", {}).get("lan_enabled")),
            "running": address is not None,
            "address": f"{address[0]}:{address[1]}" if address else None,
            "error": lan.error,
            "pairing_open": manager.phones.pairing_open(),
            "devices": manager.phones.devices(),
        }

    @app.post("/api/wifi/pair")
    def wifi_pair():
        """Новый QR-код для сопряжения. Нужна включённая связь по Wi-Fi."""
        if not manager.settings.get("network", {}).get("lan_enabled"):
            # Обычному человеку незачем искать переключатель в настройках: кнопка включает связь сама.
            overrides = deep_merge(manager.db.get_overrides(), {"network": {"lan_enabled": True}})
            settings = load_settings(overrides=deep_merge(overrides, getattr(manager, "cli_overrides", {})))
            manager.db.set_overrides(overrides)
            manager.apply_settings(settings)
            lan.sync(settings)
        address = lan.address() or lan.wait_started()
        if address is None:
            raise HTTPException(409, lan.error or "Не удалось запустить связь с телефоном. Проверьте, что ПК в домашней сети Wi-Fi.")
        secret, ttl = manager.phones.open_pairing()
        host, port = address
        payload = f"focusfarm://pair?h={host}&p={port}&s={secret}"
        return {"payload": payload, "host": host, "port": port, "expires_in": ttl, "code": secret,
                "qr_svg": qr_svg(payload)}

    @app.delete("/api/wifi/pair")
    def wifi_pair_cancel():
        manager.phones.close_pairing()
        return {"ok": True}

    @app.delete("/api/wifi/devices/{device_id}")
    def wifi_remove_device(device_id: str):
        manager.forbid_in_strict("список телефонов")
        if not manager.phones.revoke(device_id):
            raise HTTPException(404, "Такого телефона нет")
        return {"ok": True}

    @app.get("/api/protection/running")
    def protection_running():
        """Программы с окнами сейчас — подсказка для составления белого списка."""
        names = sorted({name for _, name in manager.blocker.window_apps()})
        return {"apps": names}

    @app.get("/api/rules")
    def get_rules():
        return manager.classifier.rules

    @app.put("/api/rules")
    def put_rules(body: dict):
        manager.forbid_in_strict("правила отвлечений")
        manager.classifier.set_rules(body)          # сначала проверка
        return save_rules(manager.classifier.rules, rules_path)

    # ---------- привязка телефона по USB ----------

    def usb_sensor():
        usb = getattr(manager.phone, "usb", None)
        if usb is None:
            raise HTTPException(400, "USB-датчик недоступен")
        return usb

    def save_usb_pairing(device_id: str, name: str):
        """Запоминает телефон в настройках (в базе), как и остальные настройки из интерфейса."""
        manager.forbid_in_strict("привязку телефона")
        patch = {"device": {"usb_phone": {"id": device_id, "name": name}}}
        overrides = deep_merge(manager.db.get_overrides(), patch)
        settings = load_settings(overrides=deep_merge(overrides, getattr(manager, "cli_overrides", {})))
        manager.db.set_overrides(overrides)
        manager.apply_settings(settings)
        usb_sensor().poll()

    @app.get("/api/phone")
    def phone_info():
        return {"usb": manager.usb_view(), "docked": manager.phone.is_docked(),
                "source": manager.phone.source}

    @app.get("/api/phone/devices")
    def phone_devices():
        """Все USB-устройства — для ручного выбора, если автоопределение не сработало."""
        usb = usb_sensor()
        usb.poll()
        return {"devices": usb.devices, "error": usb.error}

    @app.post("/api/phone/pair/begin")
    def phone_pair_begin():
        """Шаг 1 мастера: телефон ещё НЕ подключён, запоминаем список устройств."""
        usb_sensor().pair_begin()
        return {"ok": True}

    @app.post("/api/phone/pair/finish")
    def phone_pair_finish():
        """Шаг 2: телефон подключили. Одно новое устройство — это он, и мы его запоминаем."""
        usb = usb_sensor()
        found = usb.pair_finish()
        if len(found) == 1:
            save_usb_pairing(found[0]["id"], found[0]["name"])
        return {"candidates": found, "paired": len(found) == 1, "usb": manager.usb_view()}

    @app.post("/api/phone/pair")
    def phone_pair(body: UsbPairBody):
        """Ручная привязка: выбрать устройство из списка."""
        save_usb_pairing(body.id, body.name)
        return manager.usb_view()

    @app.delete("/api/phone/pair")
    def phone_unpair():
        save_usb_pairing("", "")
        return manager.usb_view()

    @app.get("/api/ports")
    def ports():
        try:
            from serial.tools import list_ports
            return [{"device": p.device, "description": p.description} for p in list_ports.comports()]
        except Exception as exc:
            log.warning("Не удалось получить список портов: %s", exc)
            return []

    # ---------- панель разработчика ----------

    @app.post("/api/dev/phone")
    def dev_phone(body: PhoneBody):
        require_dev()
        manager.set_phone_docked(body.docked)
        return manager.snapshot()

    @app.post("/api/dev/category")
    def dev_category(body: CategoryBody):
        require_dev()
        manager.set_forced_category(body.category)
        return manager.snapshot()

    # ---------- WebSocket ----------

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        clients.add(ws)
        try:
            await ws.send_json({**manager.snapshot(), "events": []})
            while True:
                await ws.receive_text()   # клиент ничего не шлёт, просто держим связь
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(ws)

    # ---------- интерфейс ----------

    @app.get("/")
    def index():
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
    return app

