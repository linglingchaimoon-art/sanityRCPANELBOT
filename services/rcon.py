import asyncio
import json
import logging
from typing import Optional
import websockets

from config import (
    DEBUG_RCON_MESSAGES,
    DIAMOND_TRIGGERS,
    OUTPOST_TRIGGERS,
    RCON_HOST,
    RCON_MOCK_COMMANDS,
    RCON_PASSWORD,
    RCON_PORT,
    RCON_USE_SSL,
    ULTIMATE_TRIGGERS,
    VIP_TRIGGERS,
)
from services.rewards import handle_outpost_trigger, handle_reward_trigger

logger = logging.getLogger("sanity2x.rcon")


def normalized(value: str) -> str:
    return " ".join(value.replace("\u0000", "").strip().lower().split())


TRIGGER_MAP = {}
for phrase in VIP_TRIGGERS:
    TRIGGER_MAP[normalized(phrase)] = "vip"
for phrase in DIAMOND_TRIGGERS:
    TRIGGER_MAP[normalized(phrase)] = "diamond"
for phrase in ULTIMATE_TRIGGERS:
    TRIGGER_MAP[normalized(phrase)] = "ultimate"
for phrase in OUTPOST_TRIGGERS:
    TRIGGER_MAP[normalized(phrase)] = "outpost"


class RconService:
    def __init__(self, bot):
        self.bot = bot
        self.websocket = None
        self.listener_task: Optional[asyncio.Task] = None
        self.identifier = 0
        self.send_lock = asyncio.Lock()
        self.recent_events: dict[tuple[str, str], float] = {}

    def _url(self) -> str:
        scheme = "wss" if RCON_USE_SSL else "ws"
        return f"{scheme}://{RCON_HOST}:{RCON_PORT}/{RCON_PASSWORD}"

    def start(self) -> None:
        if RCON_MOCK_COMMANDS:
            logger.warning("RCON mock mode enabled; live connection disabled.")
            return
        if self.listener_task is None:
            self.listener_task = asyncio.create_task(self._listener_loop())

    async def stop(self) -> None:
        if self.listener_task is not None:
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass
            self.listener_task = None
        if self.websocket is not None:
            await self.websocket.close()
            self.websocket = None
        logger.info("RCON service stopped.")

    async def send_command(self, command: str) -> tuple[bool, str]:
        if RCON_MOCK_COMMANDS:
            logger.warning("[MOCK RCON COMMAND] %s", command)
            return True, "Mock mode"
        if self.websocket is None:
            return False, "RCON is not connected."
        async with self.send_lock:
            self.identifier += 1
            payload = {"Identifier": self.identifier, "Message": command, "Name": "WebRcon"}
            try:
                await self.websocket.send(json.dumps(payload))
                logger.info("[RCON SENT] %s", command)
                return True, f"Sent with identifier {self.identifier}"
            except Exception as exc:
                logger.exception("Failed to send RCON command")
                return False, str(exc)

    def _extract_chat(self, raw_message: str):
        try:
            outer = json.loads(raw_message)
        except json.JSONDecodeError:
            return None
        if outer.get("Type") != "Chat":
            return None
        outer_message = str(outer.get("Message", "")).replace("\u0000", "").strip()
        try:
            chat = json.loads(outer_message)
        except json.JSONDecodeError:
            return None
        if not isinstance(chat, dict):
            return None
        username = str(chat.get("Username", "")).strip()
        phrase = str(chat.get("Message", "")).replace("\u0000", "").strip()
        user_id = chat.get("UserId")
        try:
            user_id = int(user_id) if user_id is not None else None
        except (TypeError, ValueError):
            user_id = None
        if not username or not phrase:
            return None
        return username, phrase, user_id

    def _is_duplicate(self, player_name: str, phrase: str) -> bool:
        now = asyncio.get_running_loop().time()
        key = (player_name.casefold(), normalized(phrase))
        last = self.recent_events.get(key, 0.0)
        self.recent_events[key] = now
        self.recent_events = {k: t for k, t in self.recent_events.items() if now - t < 15}
        return now - last < 3

    async def _handle_message(self, raw_message: str) -> None:
        if DEBUG_RCON_MESSAGES:
            logger.info("[RCON RECEIVED] %s", raw_message)
        chat = self._extract_chat(raw_message)
        if chat is None:
            return
        player_name, phrase, user_id = chat
        action = TRIGGER_MAP.get(normalized(phrase))
        if action is None:
            # Helpful while discovering the exact internal quick-chat phrases.
            if "quick_chat" in phrase.lower() or phrase.lower().startswith("d11_"):
                logger.info("[UNMAPPED QUICK CHAT] Player=%s Phrase=%s", player_name, phrase)
            return
        if self._is_duplicate(player_name, phrase):
            return
        logger.info("[ACTION TRIGGER] Player=%s Action=%s Phrase=%s", player_name, action, phrase)
        try:
            if action == "outpost":
                result = await handle_outpost_trigger(self.bot, self, player_name, phrase, user_id)
            else:
                result = await handle_reward_trigger(self.bot, self, player_name, phrase, action)
            logger.info("[ACTION RESULT] Player=%s Action=%s Result=%s", player_name, action, result)
        except Exception:
            logger.exception("Failed to process action %s for %s", action, player_name)

    async def _listener_loop(self) -> None:
        reconnect_delay = 5
        while not self.bot.is_closed():
            try:
                logger.info("Connecting to RCON at %s:%s", RCON_HOST, RCON_PORT)
                async with websockets.connect(
                    self._url(), open_timeout=30, ping_interval=20, ping_timeout=20,
                    close_timeout=10, max_size=4 * 1024 * 1024,
                ) as websocket:
                    self.websocket = websocket
                    reconnect_delay = 5
                    logger.info("RCON connected")
                    async for raw_message in websocket:
                        await self._handle_message(str(raw_message))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("RCON disconnected. Reconnecting in %s seconds.", reconnect_delay)
            finally:
                self.websocket = None
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 60)
