from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import aiosqlite

from config import DATABASE_PATH
from services.database import get_link_by_gamertag


logger = logging.getLogger("sanity2x.kill_rewards")

ANIMAL_KILL_REWARD = int(os.getenv("ANIMAL_KILL_REWARD", "5"))
SCIENTIST_KILL_REWARD = int(os.getenv("SCIENTIST_KILL_REWARD", "15"))
PLAYER_KILL_REWARD = int(os.getenv("PLAYER_KILL_REWARD", "30"))

PLAYER_KILL_COOLDOWN_SECONDS = int(
    os.getenv("PLAYER_KILL_COOLDOWN_SECONDS", "1800")
)

KILL_REWARD_LOG_CHANNEL_ID = int(
    os.getenv("KILL_REWARD_LOG_CHANNEL_ID", "0") or 0
)

DEBUG_KILL_EVENTS = (
    os.getenv("DEBUG_KILL_EVENTS", "false").lower()
    in {"1", "true", "yes", "on"}
)

ANIMAL_WORDS = {
    "bear",
    "boar",
    "chicken",
    "deer",
    "horse",
    "polar bear",
    "polarbear",
    "shark",
    "stag",
    "wolf",
}

SCIENTIST_WORDS = {
    "scientist",
    "heavy scientist",
    "heavyscientist",
    "peacekeeper scientist",
    "tunnel dweller",
    "tunneldweller",
    "murderer",
    "npc",
}

# These patterns are intentionally strict. Add the exact event wording
# your server outputs if DEBUG_KILL_EVENTS reveals a different format.
TEXT_PATTERNS = (
    re.compile(
        r"(?P<killer>[^:\n]+?)\s+killed\s+"
        r"(?P<victim>[^:\n]+?)"
        r"(?:\s+using\s+(?P<weapon>.+))?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<victim>[^:\n]+?)\s+was killed by\s+"
        r"(?P<killer>[^:\n]+?)"
        r"(?:\s+using\s+(?P<weapon>.+))?$",
        re.IGNORECASE,
    ),
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat()


def clean_name(value: Any) -> str:
    return " ".join(
        str(value or "")
        .replace("\u0000", "")
        .replace('"', "'")
        .strip()
        .split()
    )


async def init_kill_reward_database() -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS shop_wallets (
                discord_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                lifetime_earned INTEGER NOT NULL DEFAULT 0,
                lifetime_spent INTEGER NOT NULL DEFAULT 0,
                reputation_xp INTEGER NOT NULL DEFAULT 0,
                daily_claimed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS kill_reward_events (
                event_hash TEXT PRIMARY KEY,
                killer_name TEXT NOT NULL,
                victim_name TEXT NOT NULL,
                victim_type TEXT NOT NULL,
                reward INTEGER NOT NULL,
                discord_id INTEGER,
                rewarded INTEGER NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS player_kill_cooldowns (
                killer_name TEXT NOT NULL,
                victim_name TEXT NOT NULL,
                rewarded_at TEXT NOT NULL,
                PRIMARY KEY (killer_name, victim_name)
            );

            CREATE INDEX IF NOT EXISTS idx_kill_reward_killer
            ON kill_reward_events (killer_name, created_at DESC);
            """
        )
        await db.commit()


def _first_value(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    lowered = {
        str(key).casefold(): value
        for key, value in data.items()
    }

    for key in keys:
        if key.casefold() in lowered:
            value = lowered[key.casefold()]
            if value not in (None, ""):
                return value

    return None


def _find_event_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        killer = _first_value(
            value,
            (
                "killer",
                "killername",
                "attacker",
                "attackername",
                "sourceplayer",
                "initiator",
            ),
        )
        victim = _first_value(
            value,
            (
                "victim",
                "victimname",
                "target",
                "targetname",
                "entityname",
                "killed",
            ),
        )

        if killer and victim:
            return value

        for nested in value.values():
            result = _find_event_dict(nested)
            if result:
                return result

    elif isinstance(value, list):
        for nested in value:
            result = _find_event_dict(nested)
            if result:
                return result

    elif isinstance(value, str):
        text = value.strip()
        if text.startswith(("{", "[")):
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                return None
            return _find_event_dict(decoded)

    return None


def _extract_text_candidates(value: Any) -> list[str]:
    candidates: list[str] = []

    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).casefold() in {
                "message",
                "text",
                "msg",
                "description",
                "log",
            }:
                if isinstance(nested, str):
                    candidates.append(nested)

            candidates.extend(
                _extract_text_candidates(nested)
            )

    elif isinstance(value, list):
        for nested in value:
            candidates.extend(
                _extract_text_candidates(nested)
            )

    elif isinstance(value, str):
        candidates.append(value)

        text = value.strip()
        if text.startswith(("{", "[")):
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                decoded = None

            if decoded is not None:
                candidates.extend(
                    _extract_text_candidates(decoded)
                )

    return candidates


def _classify_victim(
    victim_name: str,
    victim_type_hint: str = "",
    is_player_hint: Any = None,
) -> str:
    victim = victim_name.casefold()
    hint = victim_type_hint.casefold()

    if isinstance(is_player_hint, bool):
        if is_player_hint:
            return "player"

    if any(word in victim or word in hint for word in SCIENTIST_WORDS):
        return "scientist"

    if any(word in victim or word in hint for word in ANIMAL_WORDS):
        return "animal"

    if hint in {"player", "human", "survivor"}:
        return "player"

    # Unknown names are not treated as players automatically.
    return "unknown"


def parse_kill_event(
    raw_message: str,
) -> dict[str, str] | None:
    try:
        decoded: Any = json.loads(raw_message)
    except json.JSONDecodeError:
        decoded = raw_message

    event_dict = _find_event_dict(decoded)

    if event_dict:
        killer = clean_name(
            _first_value(
                event_dict,
                (
                    "killer",
                    "killername",
                    "attacker",
                    "attackername",
                    "sourceplayer",
                    "initiator",
                ),
            )
        )
        victim = clean_name(
            _first_value(
                event_dict,
                (
                    "victim",
                    "victimname",
                    "target",
                    "targetname",
                    "entityname",
                    "killed",
                ),
            )
        )
        victim_type_hint = clean_name(
            _first_value(
                event_dict,
                (
                    "victimtype",
                    "targettype",
                    "entitytype",
                    "type",
                    "category",
                ),
            )
        )
        weapon = clean_name(
            _first_value(
                event_dict,
                (
                    "weapon",
                    "weaponname",
                    "damageweapon",
                    "item",
                ),
            )
        )
        is_player_hint = _first_value(
            event_dict,
            (
                "isplayer",
                "victimisplayer",
                "targetisplayer",
            ),
        )

        if killer and victim:
            return {
                "killer": killer,
                "victim": victim,
                "victim_type": _classify_victim(
                    victim,
                    victim_type_hint,
                    is_player_hint,
                ),
                "weapon": weapon,
            }

    for text in _extract_text_candidates(decoded):
        cleaned = clean_name(text)

        for pattern in TEXT_PATTERNS:
            match = pattern.search(cleaned)
            if not match:
                continue

            killer = clean_name(match.group("killer"))
            victim = clean_name(match.group("victim"))
            weapon = clean_name(match.groupdict().get("weapon"))

            if killer and victim:
                return {
                    "killer": killer,
                    "victim": victim,
                    "victim_type": _classify_victim(victim),
                    "weapon": weapon,
                }

    return None


def _event_hash(
    killer: str,
    victim: str,
    victim_type: str,
    weapon: str,
    raw_message: str,
) -> str:
    # The raw event is included so two separate kills can still be recorded.
    payload = "|".join(
        (
            killer.casefold(),
            victim.casefold(),
            victim_type,
            weapon.casefold(),
            raw_message.strip(),
        )
    )

    return hashlib.sha256(
        payload.encode("utf-8", errors="ignore")
    ).hexdigest()


async def _already_processed(
    event_hash: str,
) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        row = await (
            await db.execute(
                """
                SELECT 1
                FROM kill_reward_events
                WHERE event_hash = ?
                """,
                (event_hash,),
            )
        ).fetchone()

    return row is not None


async def _player_kill_on_cooldown(
    killer: str,
    victim: str,
) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        row = await (
            await db.execute(
                """
                SELECT rewarded_at
                FROM player_kill_cooldowns
                WHERE killer_name = ?
                  AND victim_name = ?
                """,
                (
                    killer.casefold(),
                    victim.casefold(),
                ),
            )
        ).fetchone()

    if not row:
        return False

    rewarded_at = datetime.fromisoformat(row[0])
    available_at = rewarded_at + timedelta(
        seconds=PLAYER_KILL_COOLDOWN_SECONDS
    )

    return utcnow() < available_at


async def _record_event(
    *,
    event_hash: str,
    killer: str,
    victim: str,
    victim_type: str,
    reward: int,
    discord_id: int | None,
    rewarded: bool,
    reason: str,
) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO kill_reward_events (
                event_hash,
                killer_name,
                victim_name,
                victim_type,
                reward,
                discord_id,
                rewarded,
                reason,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_hash,
                killer,
                victim,
                victim_type,
                reward,
                discord_id,
                int(rewarded),
                reason,
                utcnow_iso(),
            ),
        )
        await db.commit()


async def _award_coins(
    discord_id: int,
    reward: int,
) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")

        await db.execute(
            """
            INSERT OR IGNORE INTO shop_wallets (discord_id)
            VALUES (?)
            """,
            (discord_id,),
        )

        await db.execute(
            """
            UPDATE shop_wallets
            SET
                balance = balance + ?,
                lifetime_earned = lifetime_earned + ?
            WHERE discord_id = ?
            """,
            (
                reward,
                reward,
                discord_id,
            ),
        )

        row = await (
            await db.execute(
                """
                SELECT balance
                FROM shop_wallets
                WHERE discord_id = ?
                """,
                (discord_id,),
            )
        ).fetchone()

        await db.commit()

    return int(row[0])


async def _set_player_kill_cooldown(
    killer: str,
    victim: str,
) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT INTO player_kill_cooldowns (
                killer_name,
                victim_name,
                rewarded_at
            )
            VALUES (?, ?, ?)
            ON CONFLICT (killer_name, victim_name)
            DO UPDATE SET rewarded_at = excluded.rewarded_at
            """,
            (
                killer.casefold(),
                victim.casefold(),
                utcnow_iso(),
            ),
        )
        await db.commit()


async def _send_reward_log(
    bot,
    *,
    killer: str,
    victim: str,
    victim_type: str,
    reward: int,
    balance: int,
    weapon: str,
) -> None:
    if not KILL_REWARD_LOG_CHANNEL_ID:
        return

    channel = bot.get_channel(
        KILL_REWARD_LOG_CHANNEL_ID
    )

    if channel is None:
        try:
            channel = await bot.fetch_channel(
                KILL_REWARD_LOG_CHANNEL_ID
            )
        except Exception:
            logger.exception(
                "Could not fetch kill reward log channel"
            )
            return

    import discord

    embed = discord.Embed(
        title="⚔️ Kill Reward",
        description=(
            f"`{killer}` earned Sanity Coins."
        ),
        color=discord.Color.gold(),
        timestamp=utcnow(),
    )

    embed.add_field(
        name="Target",
        value=f"`{victim}`",
        inline=True,
    )
    embed.add_field(
        name="Type",
        value=f"**{victim_type.title()}**",
        inline=True,
    )
    embed.add_field(
        name="Reward",
        value=f"🪙 **+{reward} SC**",
        inline=True,
    )
    embed.add_field(
        name="New Balance",
        value=f"🪙 **{balance:,} SC**",
        inline=True,
    )

    if weapon:
        embed.add_field(
            name="Weapon",
            value=f"`{weapon}`",
            inline=True,
        )

    await channel.send(
        embed=embed,
        allowed_mentions=discord.AllowedMentions.none(),
    )


async def handle_kill_event(
    bot,
    raw_message: str,
) -> bool:
    """
    Inspect a raw WebRCON message.

    Returns True when it recognized a kill event, even if no reward
    was granted. Returns False when the message was not a kill event.
    """
    await init_kill_reward_database()

    event = parse_kill_event(raw_message)

    if event is None:
        if DEBUG_KILL_EVENTS:
            lowered = raw_message.casefold()
            if any(
                word in lowered
                for word in (
                    "kill",
                    "death",
                    "died",
                    "scientist",
                    "bear",
                    "boar",
                    "wolf",
                )
            ):
                logger.info(
                    "[UNPARSED POSSIBLE KILL EVENT] %s",
                    raw_message,
                )
        return False

    killer = event["killer"]
    victim = event["victim"]
    victim_type = event["victim_type"]
    weapon = event["weapon"]

    if DEBUG_KILL_EVENTS:
        logger.info(
            "[PARSED KILL EVENT] killer=%s victim=%s type=%s weapon=%s",
            killer,
            victim,
            victim_type,
            weapon,
        )

    event_hash = _event_hash(
        killer,
        victim,
        victim_type,
        weapon,
        raw_message,
    )

    if await _already_processed(event_hash):
        return True

    if killer.casefold() == victim.casefold():
        await _record_event(
            event_hash=event_hash,
            killer=killer,
            victim=victim,
            victim_type=victim_type,
            reward=0,
            discord_id=None,
            rewarded=False,
            reason="self_kill",
        )
        return True

    reward_map = {
        "animal": ANIMAL_KILL_REWARD,
        "scientist": SCIENTIST_KILL_REWARD,
        "player": PLAYER_KILL_REWARD,
    }

    reward = reward_map.get(victim_type, 0)

    if reward <= 0:
        await _record_event(
            event_hash=event_hash,
            killer=killer,
            victim=victim,
            victim_type=victim_type,
            reward=0,
            discord_id=None,
            rewarded=False,
            reason="unknown_victim_type",
        )
        return True

    link = await get_link_by_gamertag(killer)

    if not link:
        await _record_event(
            event_hash=event_hash,
            killer=killer,
            victim=victim,
            victim_type=victim_type,
            reward=reward,
            discord_id=None,
            rewarded=False,
            reason="killer_not_linked",
        )
        return True

    discord_id = int(link["discord_id"])

    if (
        victim_type == "player"
        and await _player_kill_on_cooldown(
            killer,
            victim,
        )
    ):
        await _record_event(
            event_hash=event_hash,
            killer=killer,
            victim=victim,
            victim_type=victim_type,
            reward=reward,
            discord_id=discord_id,
            rewarded=False,
            reason="same_victim_cooldown",
        )
        return True

    balance = await _award_coins(
        discord_id,
        reward,
    )

    if victim_type == "player":
        await _set_player_kill_cooldown(
            killer,
            victim,
        )

    await _record_event(
        event_hash=event_hash,
        killer=killer,
        victim=victim,
        victim_type=victim_type,
        reward=reward,
        discord_id=discord_id,
        rewarded=True,
        reason="rewarded",
    )

    logger.info(
        "[KILL REWARD] killer=%s victim=%s type=%s reward=%s balance=%s",
        killer,
        victim,
        victim_type,
        reward,
        balance,
    )

    try:
        await _send_reward_log(
            bot,
            killer=killer,
            victim=victim,
            victim_type=victim_type,
            reward=reward,
            balance=balance,
            weapon=weapon,
        )
    except Exception:
        logger.exception(
            "Failed to send kill reward Discord log"
        )

    return True
