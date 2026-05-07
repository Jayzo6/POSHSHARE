"""
server.py — FastAPI WebSocket bridge for the Poshshare web dashboard.

Run:
    pip install fastapi uvicorn websockets
    python server.py

Then open http://localhost:8000 in your browser.
"""

import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# ── Allow running from either the project root or poshshare/ subfolder ──
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

try:
    from poshshare.models import ClosetTarget, parse_closets_lines, format_closets_lines
    from poshshare.automation import Sharer
    from poshshare.app_paths import get_closets_path, get_credentials_path
except ImportError:
    from models import ClosetTarget, parse_closets_lines, format_closets_lines
    from automation import Sharer
    from app_paths import get_closets_path, get_credentials_path

import json as _json

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="Poshshare Dashboard")

# Serve the compiled dashboard HTML as the root
DASHBOARD_PATH = ROOT / "dashboard.html"


@app.get("/", response_class=HTMLResponse)
async def root():
    if DASHBOARD_PATH.exists():
        return HTMLResponse(DASHBOARD_PATH.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>dashboard.html not found — build it first.</h2>")


# ── Connection manager ────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, msg: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(json.dumps(msg))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)


manager = ConnectionManager()

# Thread-safe queue so the worker thread can push events to async land
_event_queue: asyncio.Queue = None  # initialised in lifespan


# ── Bot state ─────────────────────────────────────────────────────────────────
class BotState:
    def __init__(self):
        self.running = False
        self.stop_event = threading.Event()
        self.worker: Optional[threading.Thread] = None
        self.targets: list[ClosetTarget] = []
        self.completed: list[str] = []
        self.total_shared = 0
        self.start_time: Optional[float] = None
        self._twofa_event = threading.Event()
        self._twofa_code: str = ""
        self._last_ui_log: str = ""

    # Called from the worker thread — thread-safe via queue
    def emit(self, event: dict):
        if _event_queue:
            asyncio.run_coroutine_threadsafe(
                _event_queue.put(event), _loop
            )

    def _normalize_log_message(self, msg: str) -> Optional[str]:
        """Convert verbose automation logs into user-friendly dashboard logs."""
        m = msg.strip()
        l = m.lower()

        # Drop noisy internal/debug details
        noisy_tokens = [
            "[debug]",
            "using selector:",
            "selector:",
            "role-based search",
            "popup button",
            "page title:",
            "attempt with iframe",
            "frame locator attempt failed",
            "direct click failed",
            "page contains",
            "specifically searching for",
            "found actual clickable",
            "element type:",
            "successfully clicked actual",
            "waiting for modal to close automatically",
            "modal closed automatically",
            "waiting for share modal to appear",
            "trying to load more items",
            "no more items to load",
        ]
        if any(t in l for t in noisy_tokens):
            return None

        # Login flow
        if "starting login process" in l:
            return "Logging in..."
        if "navigating to login page" in l:
            return "Opening login page..."
        if "waiting for login form" in l:
            return "Waiting for login form..."
        if "filled username" in l or "username/email field" in l:
            return "Inputting email..."
        if "filled password" in l or "password field" in l:
            return "Inputting password..."
        if "clicked login button" in l or "looking for login button" in l:
            return "Submitting login..."
        if "waiting for login or 2fa prompt" in l:
            return "Waiting for login response..."
        if "detected 2fa" in l or "2fa verification code required" in l:
            return "2FA detected."
        if "received 2fa code" in l:
            return "2FA code received."
        if "2fa code entered and submitted successfully" in l:
            return "Submitting 2FA code..."
        if "2fa completed successfully" in l:
            return "2FA complete."
        if "login successful" in l:
            return "Login successful."
        if "login failed" in l or "[error] login process failed" in l:
            return "Login failed."

        # CAPTCHA
        if "recaptcha detected" in l or "captcha detected" in l:
            return "CAPTCHA detected."
        if "automatically clicking captcha checkbox" in l:
            return "Attempting CAPTCHA checkbox..."
        if "using 2captcha to solve captcha" in l:
            return "Solving CAPTCHA with 2captcha..."
        if "captcha cleared" in l:
            return "CAPTCHA cleared."
        if "still waiting for captcha to be solved" in l:
            return "Waiting for CAPTCHA to be solved..."

        # Sharing flow
        if "starting to process" in l and "closets" in l:
            return m.replace("[*]", "").strip()
        if "processing closet" in l:
            return m.replace("[*]", "").strip()
        if "loading items" in l:
            return "Loading closet items..."
        if "shared item" in l:
            return m.replace("[✓]", "").strip()
        if "closet" in l and "items shared" in l:
            return m.replace("[✓]", "").strip()
        if "total shares so far" in l:
            return m.replace("[*]", "").strip()
        if "sharing complete" in l:
            return "Sharing complete."
        if "stop requested" in l:
            return "Stop requested..."

        # Keep concise warnings/errors by default
        if m.startswith("[!]") or "error" in l or "failed" in l or "warning" in l:
            return m

        # Drop verbose lines that don't add value
        if m.startswith("    "):
            return None

        # Default: keep the message
        return m

    def log(self, msg: str):
        ui_msg = self._normalize_log_message(msg)
        if not ui_msg:
            return
        # Avoid spamming exact duplicate lines back-to-back
        if ui_msg == self._last_ui_log:
            return
        self._last_ui_log = ui_msg

        # Classify message for frontend colouring
        low = ui_msg.lower()
        if ui_msg.startswith("[✓]") or "successful" in low or "complete" in low:
            kind = "success"
        elif ui_msg.startswith("[!]") or "error" in low or "failed" in low:
            kind = "err"
        elif "warning" in low or "detected" in low:
            kind = "warn"
        elif ui_msg.startswith("[*]") or "loading" in low or "waiting" in low:
            kind = "info"
        else:
            kind = ""
        self.emit({"type": "log", "msg": ui_msg, "kind": kind})

    def on_closet_completed(self, username: str, shared_count: int):
        self.completed.append(username)
        self.total_shared += shared_count
        elapsed = time.time() - (self.start_time or time.time())
        rate = round(self.total_shared / elapsed * 60, 1) if elapsed > 5 else 0
        self.emit({
            "type": "closet_done",
            "user": username,
            "shared": shared_count,
            "total_shared": self.total_shared,
            "completed": len(self.completed),
            "queue": len(self.targets) - len(self.completed),
            "rate": rate,
        })

    def prompt_2fa(self) -> str:
        """Block worker thread until the client sends the code."""
        self._twofa_code = ""
        self._twofa_event.clear()
        self.emit({"type": "twofa_required"})
        self._twofa_event.wait(timeout=120)
        return self._twofa_code

    def receive_twofa(self, code: str):
        self._twofa_code = code
        self._twofa_event.set()


bot = BotState()
_loop: asyncio.AbstractEventLoop = None


# ── Lifespan (replaces @app.on_event) ────────────────────────────────────────
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_queue, _loop
    _loop = asyncio.get_running_loop()
    _event_queue = asyncio.Queue()
    asyncio.create_task(_event_pump())

    # Load persisted closets on startup
    _load_saved_closets()
    yield


app.router.lifespan_context = lifespan


async def _event_pump():
    """Forward worker-thread events to all WebSocket clients."""
    while True:
        event = await _event_queue.get()
        await manager.broadcast(event)


# ── Persistence helpers ───────────────────────────────────────────────────────
def _load_saved_closets():
    path = get_closets_path()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        bot.targets = parse_closets_lines(lines, default_max=7)


def _save_closets():
    if bot.targets:
        with open(get_closets_path(), "w", encoding="utf-8") as f:
            f.write(format_closets_lines(bot.targets) + "\n")


def _load_credentials() -> dict:
    path = get_credentials_path()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            try:
                return _json.load(f)
            except Exception:
                return {}
    return {}


def _save_credentials(data: dict):
    path = get_credentials_path()
    existing = _load_credentials()
    existing.update(data)
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(existing, f, indent=2)


# ── WebSocket endpoint ────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)

    # Send current state on connect
    creds = _load_credentials()
    await ws.send_text(json.dumps({
        "type": "init",
        "targets": [{"user": t.user, "max": t.max_items} for t in bot.targets],
        "credentials": {
            "username": creds.get("username", ""),
            "remember": creds.get("remember", False),
            "has_captcha_key": bool(creds.get("2captcha_api_key", "")),
        },
        "stats": {
            "queue": len(bot.targets),
            "shared": bot.total_shared,
            "completed": len(bot.completed),
        },
        "running": bot.running,
    }))

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            await _handle_message(msg)
    except WebSocketDisconnect:
        manager.disconnect(ws)


async def _handle_message(msg: dict):
    action = msg.get("action")

    if action == "start":
        await _start_bot(msg)

    elif action == "stop":
        bot.stop_event.set()
        bot.running = False
        await manager.broadcast({"type": "stopped"})

    elif action == "add_closets":
        default_max = int(msg.get("default_max", 7))
        users = msg.get("users", [])
        existing = {t.user for t in bot.targets}
        added = []
        for u in users:
            if u not in existing:
                bot.targets.append(ClosetTarget(user=u, max_items=default_max))
                added.append({"user": u, "max": default_max})
        _save_closets()
        await manager.broadcast({"type": "closets_updated",
                                  "targets": [{"user": t.user, "max": t.max_items} for t in bot.targets],
                                  "added": added})

    elif action == "remove_closet":
        user = msg.get("user")
        bot.targets = [t for t in bot.targets if t.user != user]
        _save_closets()
        await manager.broadcast({"type": "closets_updated",
                                  "targets": [{"user": t.user, "max": t.max_items} for t in bot.targets]})

    elif action == "update_closet":
        user = msg.get("user")
        new_max = int(msg.get("max", 7))
        for t in bot.targets:
            if t.user == user:
                t.max_items = new_max
        _save_closets()

    elif action == "clear_closets":
        bot.targets.clear()
        _save_closets()
        await manager.broadcast({"type": "closets_updated", "targets": []})

    elif action == "twofa_response":
        bot.receive_twofa(msg.get("code", ""))

    elif action == "save_credentials":
        creds = {}
        if msg.get("remember"):
            creds["username"] = msg.get("username", "")
            # Don't erase a remembered password when the UI sends an empty field.
            if "password" in msg and msg.get("password", ""):
                creds["password"] = msg.get("password", "")
            creds["remember"] = True
        if msg.get("captcha_key"):
            creds["2captcha_api_key"] = msg["captcha_key"]
        _save_credentials(creds)

    elif action == "get_state":
        await manager.broadcast({
            "type": "state",
            "targets": [{"user": t.user, "max": t.max_items} for t in bot.targets],
            "running": bot.running,
            "stats": {
                "queue": len(bot.targets) - len(bot.completed),
                "shared": bot.total_shared,
                "completed": len(bot.completed),
            }
        })


async def _start_bot(msg: dict):
    if bot.running:
        await manager.broadcast({"type": "log", "msg": "Bot is already running.", "kind": "warn"})
        return
    if not bot.targets:
        await manager.broadcast({"type": "log", "msg": "No closets in queue.", "kind": "warn"})
        return

    username = msg.get("username", "").strip()
    password = msg.get("password", "").strip()
    # Allow app restarts to use remembered credentials when fields are blank.
    if not username or not password:
        creds = _load_credentials()
        if creds.get("remember"):
            username = username or creds.get("username", "").strip()
            password = password or creds.get("password", "").strip()
    if not username or not password:
        await manager.broadcast({"type": "log", "msg": "Username and password required.", "kind": "err"})
        return

    import random
    targets = list(bot.targets)
    if msg.get("shuffle", True):
        random.shuffle(targets)

    bot.stop_event.clear()
    bot.running = True
    bot.completed.clear()
    bot.total_shared = 0
    bot.start_time = time.time()

    await manager.broadcast({"type": "started"})

    def _worker():
        try:
            sharer = Sharer(
                log=bot.log,
                stop_event=bot.stop_event,
                on_closet_completed=bot.on_closet_completed,
                twofa_callback=bot.prompt_2fa,
            )
            sharer.run(
                username=username,
                password=password,
                targets=targets,
                party=msg.get("party", "").strip() or None,
                headful=msg.get("headful", False),
                slowmo_ms=0,
                total_shares_limit=str(msg.get("total_limit", "")),
                twocaptcha_api_key=msg.get("captcha_key", ""),
            )
        except Exception as e:
            bot.emit({"type": "log", "msg": f"Worker error: {e}", "kind": "err"})
        finally:
            bot.running = False
            bot.emit({"type": "stopped"})

    bot.worker = threading.Thread(target=_worker, daemon=True)
    bot.worker.start()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
