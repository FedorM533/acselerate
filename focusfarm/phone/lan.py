"""Сервер для телефона в локальной сети.

Это ОТДЕЛЬНОЕ маленькое приложение. Основное (интерфейс, настройки, управление
сессией) по-прежнему слушает только 127.0.0.1. Сюда выведены только два входа:
  POST /pair   — обмен одноразового секрета из QR-кода на токен;
  WS   /phone  — постоянная связь по токену (состояние ← ПК, отчёты → ПК).

Защита: включается только в настройках (network.lan_enabled), слушает только
частный адрес вашей сети (192.168.x.x, 10.x.x.x, 172.16–31.x.x), пускает только
клиентов из частных сетей и требует токен.
Подробный протокол — docs/PHONE_PROTOCOL.md.
"""
import asyncio
import ipaddress
import logging
import socket
import threading
import time

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from focusfarm.phone.hub import PairingError

log = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
HELLO_TIMEOUT_S = 5       # после подключения телефон обязан сразу прислать hello с токеном
IDLE_TIMEOUT_S = 45       # телефон шлёт heartbeat раз в 15 с; тишина дольше — связь потеряна
HEARTBEAT_S = 15          # как часто повторяем состояние, даже если оно не менялось
SEND_POLL_S = 1.0         # как часто проверяем, не изменилось ли состояние (в тестах уменьшают)
MAX_MESSAGE_BYTES = 65536


def is_private_client(host: str | None) -> bool:
    """Пускаем только свои: локальная сеть или этот же компьютер."""
    try:
        ip = ipaddress.ip_address(host or "")
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


def local_ip() -> str | None:
    """Адрес ПК в домашней сети. Пакеты никуда не уходят: UDP-«соединение» только выбирает интерфейс."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        host = sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()
    ip = ipaddress.ip_address(host)
    return host if ip.is_private and not ip.is_loopback else None


class PairBody(BaseModel):
    secret: str = Field(max_length=100)
    name: str = Field(default="", max_length=100)


def build_phone_app(manager, allow_client=is_private_client) -> FastAPI:
    hub = manager.phones
    app = FastAPI(title="Фокус-пруд: телефон", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def only_private(request: Request, call_next):
        host = request.client.host if request.client else None
        if not allow_client(host):
            return JSONResponse({"detail": "forbidden"}, status_code=403)
        return await call_next(request)

    @app.post("/pair")
    def pair(body: PairBody):
        try:
            device_id, token = hub.complete_pairing(body.secret, body.name)
        except PairingError as exc:
            raise HTTPException(403, str(exc))
        return {"v": PROTOCOL_VERSION, "device_id": device_id, "token": token}

    @app.websocket("/phone")
    async def phone_ws(ws: WebSocket):
        await ws.accept()
        host = ws.client.host if ws.client else None
        if not allow_client(host):
            await ws.close(code=4403)
            return
        device = await _handshake(ws, hub)
        if device is None:
            return
        hub.set_online(device["id"], device["name"], True)
        sender = asyncio.create_task(_send_loop(ws, manager, hub, device["id"]))
        try:
            await ws.send_json({"type": "hello_ok", "v": PROTOCOL_VERSION, "name": device["name"]})
            while True:
                msg = await asyncio.wait_for(ws.receive_json(), IDLE_TIMEOUT_S)
                kind = msg.get("type") if isinstance(msg, dict) else None
                if kind == "report":
                    n = hub.accept_report(device["id"], msg.get("events"))
                    await ws.send_json({"type": "report_ok", "accepted": n})
                # heartbeat и неизвестные сообщения просто подтверждают, что телефон жив
        except Exception:    # обрыв, тишина, не-JSON: всё это конец связи
            pass
        finally:
            sender.cancel()
            hub.set_online(device["id"], device["name"], False)
            await _close(ws, 1000)

    return app


async def _handshake(ws: WebSocket, hub) -> dict | None:
    try:
        first = await asyncio.wait_for(ws.receive_json(), HELLO_TIMEOUT_S)
    except Exception:
        await _close(ws, 4408)
        return None
    if not isinstance(first, dict) or first.get("type") != "hello":
        await _close(ws, 4400)
        return None
    device = hub.authenticate(first.get("token"))
    if device is None:
        await _send_quiet(ws, {"type": "error", "reason": "bad_token"})
        await _close(ws, 4401)
        return None
    return device


async def _send_loop(ws: WebSocket, manager, hub, device_id: str):
    """Шлём телефону состояние: при изменении и раз в HEARTBEAT_S. Отозвали — закрываем."""
    last, last_at = None, 0.0
    try:
        while True:
            if not hub.still_valid(device_id):
                await _send_quiet(ws, {"type": "revoked"})
                await _close(ws, 4403)
                return
            state = manager.phone_state()
            now = time.monotonic()
            if state != last or now - last_at >= HEARTBEAT_S:
                await ws.send_json({"type": "state", "v": PROTOCOL_VERSION, **state})
                last, last_at = state, now
            await asyncio.sleep(SEND_POLL_S)
    except asyncio.CancelledError:
        raise
    except Exception:
        return    # соединение закрылось — обработчик в phone_ws завершится сам


async def _send_quiet(ws, payload):
    try:
        await ws.send_json(payload)
    except Exception:
        pass


async def _close(ws, code):
    try:
        await ws.close(code=code)
    except Exception:
        pass


class NoLan:
    """Заглушка, когда сетевой сервер не нужен (тесты, выключено)."""
    error = ""

    def sync(self, settings): ...
    def stop(self): ...
    def address(self): return None


class LanServer:
    """Запускает и останавливает сервер для телефона по настройке network.lan_enabled."""

    def __init__(self, manager):
        self.manager = manager
        self.error = ""
        self._server = None
        self._thread = None
        self._host = None
        self._port = None

    def sync(self, settings: dict):
        net = settings.get("network", {})
        enabled, port = bool(net.get("lan_enabled")), int(net.get("port", 8766))
        if not enabled:
            self.error = ""
            self.stop()
        elif (self._server is None or port != self._port
              or (self._thread is not None and not self._thread.is_alive())       # сервер упал (порт был занят)
              or self._address_changed()):                                          # у ПК сменился адрес в сети
            self.stop()
            self._start(port)

    def _address_changed(self) -> bool:
        ip = local_ip()
        return ip is not None and self._host is not None and ip != self._host

    def address(self) -> tuple[str, int] | None:
        server = self._server
        return (self._host, self._port) if server is not None and server.started else None

    def _start(self, port: int):
        host = local_ip()
        if host is None:
            self.error = "Не вижу домашнюю сеть Wi-Fi. Подключите ПК к той же сети, что и телефон."
            return
        config = uvicorn.Config(build_phone_app(self.manager), host=host, port=port,
                                log_level="warning", ws_max_size=MAX_MESSAGE_BYTES)
        server = uvicorn.Server(config)

        def run():
            try:
                server.run()
            except (SystemExit, Exception):     # например, порт занят
                log.exception("Сервер для телефона остановился")
                self.error = f"Не удалось запустить связь с телефоном на порту {port} (занят?)."

        self.error = ""
        self._server, self._host, self._port = server, host, port
        self._thread = threading.Thread(target=run, name="phone-lan", daemon=True)
        self._thread.start()
        log.info("Связь с телефоном: %s:%s", host, port)

    def stop(self):
        server, thread = self._server, self._thread
        self._server = self._thread = self._host = self._port = None
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=3)
