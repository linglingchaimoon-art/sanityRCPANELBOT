import asyncio
import json
import logging
from typing import Optional

import websockets # type: ignore

from config import (
    DEBUG_RCON_MESSAGES,
    DIAMOND_TRIGGERS,
    OUTPOST_CONFIRM_SECONDS,
    OUTPOST_CONFIRM_TRIGGERS,
    OUTPOST_TRIGGERS,
    RCON_HOST,
    RCON_MOCK_COMMANDS,
    RCON_PASSWORD,
    RCON_PORT,
    RCON_USE_SSL,
    ULTIMATE_TRIGGERS,
    VIP_TRIGGERS,
)
from services.rewards import (
    announce,
    handle_outpost_trigger,
    handle_reward_trigger,
)

logger = logging.getLogger("sanity2x.rcon")


def normalized(value: str) -> str:
    return " ".join(
        value.replace("\u0000", "").strip().lower().split()
    )


TRIGGER_MAP: dict[str, str] = {}

for phrase in VIP_TRIGGERS:
    TRIGGER_MAP[normalized(phrase)] = "vip"

for phrase in DIAMOND_TRIGGERS:
    TRIGGER_MAP[normalized(phrase)] = "diamond"

for phrase in ULTIMATE_TRIGGERS:
    TRIGGER_MAP[normalized(phrase)] = "ultimate"

for phrase in OUTPOST_TRIGGERS:
    TRIGGER_MAP[normalized(phrase)] = "outpost"


CONFIRM_TRIGGER_SET = {
    normalized(phrase)
    for phrase in OUTPOST_CONFIRM_TRIGGERS
}


class RconService:
    def __init__(self, bot):
        self.bot = bot
        self.websocket = None
        self.listener_task: Optional[asyncio.Task] = None
        self.identifier = 0
        self.send_lock = asyncio.Lock()

        self.recent_events: dict[tuple[str, str], float] = {}

        # Key:
        # Player name in lowercase
        #
        # Value:
        # {
        #     "player_name": str,
        #     "user_id": int | None,
        #     "phrase": str,
        #     "expires_at": float,
        # }
        self.pending_outpost: dict[str, dict] = {}

    def _url(self) -> str:
        scheme = "wss" if RCON_USE_SSL else "ws"
        return f"{scheme}://{RCON_HOST}:{RCON_PORT}/{RCON_PASSWORD}"

    def start(self) -> None:
        if RCON_MOCK_COMMANDS:
            logger.warning(
                "RCON mock mode enabled; live connection disabled."
            )
            return

        if self.listener_task is None:
            self.listener_task = asyncio.create_task(
                self._listener_loop()
            )

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

        self.pending_outpost.clear()

        logger.info("RCON service stopped.")

    async def send_command(
        self,
        command: str,
    ) -> tuple[bool, str]:
        if RCON_MOCK_COMMANDS:
            logger.warning(
                "[MOCK RCON COMMAND] %s",
                command,
            )
            return True, "Mock mode"

        if self.websocket is None:
            return False, "RCON is not connected."

        async with self.send_lock:
            self.identifier += 1

            payload = {
                "Identifier": self.identifier,
                "Message": command,
                "Name": "WebRcon",
            }

            try:
                await self.websocket.send(
                    json.dumps(payload)
                )

                logger.info(
                    "[RCON SENT] %s",
                    command,
                )

                return (
                    True,
                    f"Sent with identifier {self.identifier}",
                )

            except Exception as exc:
                logger.exception(
                    "Failed to send RCON command"
                )
                return False, str(exc)

    def _extract_chat(self, raw_message: str):
        try:
            outer = json.loads(raw_message)
        except json.JSONDecodeError:
            return None

        if outer.get("Type") != "Chat":
            return None

        outer_message = (
            str(outer.get("Message", ""))
            .replace("\u0000", "")
            .strip()
        )

        try:
            chat = json.loads(outer_message)
        except json.JSONDecodeError:
            return None

        if not isinstance(chat, dict):
            return None

        username = str(
            chat.get("Username", "")
        ).strip()

        phrase = (
            str(chat.get("Message", ""))
            .replace("\u0000", "")
            .strip()
        )

        user_id = chat.get("UserId")

        try:
            user_id = (
                int(user_id)
                if user_id is not None
                else None
            )
        except (TypeError, ValueError):
            user_id = None

        if not username or not phrase:
            return None

        return username, phrase, user_id

    def _is_duplicate(
        self,
        player_name: str,
        phrase: str,
    ) -> bool:
        now = asyncio.get_running_loop().time()

        key = (
            player_name.casefold(),
            normalized(phrase),
        )

        last = self.recent_events.get(key, 0.0)

        self.recent_events[key] = now

        self.recent_events = {
            stored_key: timestamp
            for stored_key, timestamp
            in self.recent_events.items()
            if now - timestamp < 15
        }

        return now - last < 3

    def _cleanup_expired_confirmations(self) -> None:
        now = asyncio.get_running_loop().time()

        self.pending_outpost = {
            player_key: request
            for player_key, request
            in self.pending_outpost.items()
            if request["expires_at"] > now
        }

    async def _create_outpost_confirmation(
        self,
        player_name: str,
        phrase: str,
        user_id: int | None,
    ) -> dict:
        self._cleanup_expired_confirmations()

        player_key = player_name.casefold()
        now = asyncio.get_running_loop().time()

        self.pending_outpost[player_key] = {
            "player_name": player_name,
            "user_id": user_id,
            "phrase": phrase,
            "expires_at": now + OUTPOST_CONFIRM_SECONDS,
        }

        await announce(
            self,
            (
                f"{player_name}: teleport to Outpost? "
                f"Select Yes within "
                f"{OUTPOST_CONFIRM_SECONDS} seconds."
            ),
        )

        logger.info(
            "[OUTPOST CONFIRMATION CREATED] "
            "Player=%s UserId=%s ExpiresIn=%ss",
            player_name,
            user_id,
            OUTPOST_CONFIRM_SECONDS,
        )

        return {
            "delivered": False,
            "reason": "confirmation_required",
            "expires_in": OUTPOST_CONFIRM_SECONDS,
        }

    async def _confirm_outpost(
        self,
        player_name: str,
        phrase: str,
        current_user_id: int | None,
    ) -> dict:
        player_key = player_name.casefold()

        request = self.pending_outpost.get(player_key)

        if request is None:
            logger.info(
                "[OUTPOST CONFIRMATION IGNORED] "
                "Player=%s Reason=no_pending_request",
                player_name,
            )

            return {
                "delivered": False,
                "reason": "no_pending_request",
            }

        now = asyncio.get_running_loop().time()

        if request["expires_at"] <= now:
            self.pending_outpost.pop(
                player_key,
                None,
            )

            await announce(
                self,
                (
                    f"{player_name}: your Outpost "
                    f"teleport request expired. "
                    f"Select Let's Go again."
                ),
            )

            logger.info(
                "[OUTPOST CONFIRMATION EXPIRED] "
                "Player=%s",
                player_name,
            )

            return {
                "delivered": False,
                "reason": "confirmation_expired",
            }

        stored_user_id = request.get("user_id")

        # Prefer the user ID stored when Let's Go was selected.
        # Use the confirmation message ID as a fallback.
        user_id = stored_user_id or current_user_id

        # Block confirmation when the IDs unexpectedly differ.
        if (
            stored_user_id is not None
            and current_user_id is not None
            and stored_user_id != current_user_id
        ):
            logger.warning(
                "[OUTPOST CONFIRMATION USER ID MISMATCH] "
                "Player=%s Stored=%s Current=%s",
                player_name,
                stored_user_id,
                current_user_id,
            )

            return {
                "delivered": False,
                "reason": "user_id_mismatch",
            }

        self.pending_outpost.pop(
            player_key,
            None,
        )

        logger.info(
            "[OUTPOST CONFIRMED] "
            "Player=%s UserId=%s",
            player_name,
            user_id,
        )

        return await handle_outpost_trigger(
            self.bot,
            self,
            player_name,
            request["phrase"],
            user_id,
        )

    async def _handle_message(
        self,
        raw_message: str,
    ) -> None:
        if DEBUG_RCON_MESSAGES:
            logger.info(
                "[RCON RECEIVED] %s",
                raw_message,
            )

        chat = self._extract_chat(raw_message)

        if chat is None:
            return

        player_name, phrase, user_id = chat
        normalized_phrase = normalized(phrase)

        # Handle Yes before the normal trigger map.
        if normalized_phrase in CONFIRM_TRIGGER_SET:
            if self._is_duplicate(
                player_name,
                phrase,
            ):
                return

            logger.info(
                "[CONFIRMATION TRIGGER] "
                "Player=%s Phrase=%s",
                player_name,
                phrase,
            )

            try:
                result = await self._confirm_outpost(
                    player_name,
                    phrase,
                    user_id,
                )

                logger.info(
                    "[CONFIRMATION RESULT] "
                    "Player=%s Result=%s",
                    player_name,
                    result,
                )

            except Exception:
                logger.exception(
                    "Failed to process confirmation for %s",
                    player_name,
                )

            return

        action = TRIGGER_MAP.get(
            normalized_phrase
        )

        if action is None:
            # Helpful while discovering exact quick-chat phrases.
            if (
                "quick_chat" in phrase.lower()
                or phrase.lower().startswith("d11_")
            ):
                logger.info(
                    "[UNMAPPED QUICK CHAT] "
                    "Player=%s Phrase=%s",
                    player_name,
                    phrase,
                )

            return

        if self._is_duplicate(
            player_name,
            phrase,
        ):
            return

        logger.info(
            "[ACTION TRIGGER] "
            "Player=%s Action=%s Phrase=%s",
            player_name,
            action,
            phrase,
        )

        try:
            if action == "outpost":
                result = (
                    await self._create_outpost_confirmation(
                        player_name,
                        phrase,
                        user_id,
                    )
                )
            else:
                result = await handle_reward_trigger(
                    self.bot,
                    self,
                    player_name,
                    phrase,
                    action,
                )

            logger.info(
                "[ACTION RESULT] "
                "Player=%s Action=%s Result=%s",
                player_name,
                action,
                result,
            )

        except Exception:
            logger.exception(
                "Failed to process action %s for %s",
                action,
                player_name,
            )

    async def _listener_loop(self) -> None:
        reconnect_delay = 5

        while not self.bot.is_closed():
            try:
                logger.info(
                    "Connecting to RCON at %s:%s",
                    RCON_HOST,
                    RCON_PORT,
                )

                async with websockets.connect(
                    self._url(),
                    open_timeout=30,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=10,
                    max_size=4 * 1024 * 1024,
                ) as websocket:
                    self.websocket = websocket
                    reconnect_delay = 5

                    logger.info("RCON connected")

                    async for raw_message in websocket:
                        await self._handle_message(
                            str(raw_message)
                        )

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception(
                    "RCON disconnected. "
                    "Reconnecting in %s seconds.",
                    reconnect_delay,
                )

            finally:
                self.websocket = None

            await asyncio.sleep(
                reconnect_delay
            )

            reconnect_delay = min(
                reconnect_delay * 2,
                60,
            )