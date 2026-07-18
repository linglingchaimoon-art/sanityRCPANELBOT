import json
import os

from dotenv import load_dotenv

load_dotenv(override=True)


def env_int(name: str, default: int = 0) -> int:
    value = os.getenv(name, str(default)).strip()

    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(
            f"{name} must be an integer, got {value!r}"
        ) from exc


def env_bool(name: str, default: bool = False) -> bool:
    fallback = "true" if default else "false"

    return os.getenv(name, fallback).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def env_float(name: str, default: float = 0.0) -> float:
    value = os.getenv(name, str(default)).strip()

    try:
        return float(value)
    except ValueError as exc:
        raise RuntimeError(
            f"{name} must be a number, got {value!r}"
        ) from exc


def env_id_set(name: str) -> set[int]:
    result: set[int] = set()

    for part in os.getenv(name, "").split(","):
        part = part.strip()

        if not part:
            continue

        try:
            result.add(int(part))
        except ValueError as exc:
            raise RuntimeError(
                f"{name} contains invalid ID {part!r}"
            ) from exc

    return result


def env_string_set(
    name: str,
    default: str = "",
) -> set[str]:
    return {
        part.strip()
        for part in os.getenv(name, default).split(",")
        if part.strip()
    }


def env_commands(name: str) -> list[str]:
    raw = os.getenv(name, "[]").strip()

    if not raw:
        return []

    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{name} contains invalid JSON. "
            f"Current value: {raw!r}"
        ) from exc

    if (
        not isinstance(value, list)
        or not all(isinstance(item, str) for item in value)
    ):
        raise RuntimeError(
            f"{name} must be a JSON list of strings"
        )

    return value


# Discord

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = env_int("GUILD_ID")


# VIP roles

VIP_ROLE_ID = env_int("VIP_ROLE_ID")
DIAMOND_VIP_ROLE_ID = env_int("DIAMOND_VIP_ROLE_ID")
ULTIMATE_VIP_ROLE_ID = env_int("ULTIMATE_VIP_ROLE_ID")


# Staff roles

STAFF_ROLE_IDS = env_id_set("STAFF_ROLE_IDS")
HR_ROLE_IDS = env_id_set("HR_ROLE_IDS")


# Linking

LINKED_NICKNAME_PREFIX = os.getenv(
    "LINKED_NICKNAME_PREFIX",
    "🔗",
).strip()


# Booster

BOOSTER_CUSTOM_ROLE_ID = env_int(
    "BOOSTER_CUSTOM_ROLE_ID"
)

BOOSTER_NICKNAME_PREFIX = os.getenv(
    "BOOSTER_NICKNAME_PREFIX",
    "💎",
).strip()


# LOA

LOA_ROLE_ID = env_int("LOA_ROLE_ID")
LOA_REVIEW_CHANNEL_ID = env_int("LOA_REVIEW_CHANNEL_ID")
LOA_LOG_CHANNEL_ID = env_int("LOA_LOG_CHANNEL_ID")


# RCON

RCON_HOST = os.getenv(
    "RCON_HOST",
    "127.0.0.1",
).strip()

RCON_PORT = env_int(
    "RCON_PORT",
    28016,
)

RCON_PASSWORD = os.getenv(
    "RCON_PASSWORD",
    "",
).strip()

RCON_USE_SSL = env_bool(
    "RCON_USE_SSL",
    False,
)

RCON_MOCK_COMMANDS = env_bool(
    "RCON_MOCK_COMMANDS",
    False,
)

DEBUG_RCON_MESSAGES = env_bool(
    "DEBUG_RCON_MESSAGES",
    True,
)


# In-game messages

INGAME_MESSAGES_ENABLED = env_bool(
    "INGAME_MESSAGES_ENABLED",
    True,
)

SERVER_MESSAGE_PREFIX = os.getenv(
    "SERVER_MESSAGE_PREFIX",
    "[Sanity2X]",
).strip()


# Reward cooldowns

VIP_COOLDOWN_SECONDS = env_int(
    "VIP_COOLDOWN_SECONDS",
    86400,
)

DIAMOND_COOLDOWN_SECONDS = env_int(
    "DIAMOND_COOLDOWN_SECONDS",
    86400,
)

ULTIMATE_COOLDOWN_SECONDS = env_int(
    "ULTIMATE_COOLDOWN_SECONDS",
    86400,
)


# Outpost

OUTPOST_X = env_float("OUTPOST_X", 0.0)
OUTPOST_Y = env_float("OUTPOST_Y", 0.0)
OUTPOST_Z = env_float("OUTPOST_Z", 0.0)

OUTPOST_COOLDOWN_SECONDS = env_int(
    "OUTPOST_COOLDOWN_SECONDS",
    1800,
)

OUTPOST_CONFIRM_SECONDS = env_int(
    "OUTPOST_CONFIRM_SECONDS",
    15,
)


# Quick-chat triggers

VIP_TRIGGERS = env_string_set(
    "VIP_TRIGGERS",
    "d11_quick_chat_i_need_phrase_format wood",
)

DIAMOND_TRIGGERS = env_string_set(
    "DIAMOND_TRIGGERS",
    "d11_quick_chat_i_have_phrase_format pickaxe",
)

ULTIMATE_TRIGGERS = env_string_set(
    "ULTIMATE_TRIGGERS",
    "d11_quick_chat_i_need_phrase_format metal.refined",
)

OUTPOST_TRIGGERS = env_string_set(
    "OUTPOST_TRIGGERS",
    "d11_quick_chat_orders_slot_5",
)

OUTPOST_CONFIRM_TRIGGERS = env_string_set(
    "OUTPOST_CONFIRM_TRIGGERS",
    "d11_quick_chat_responses_slot_0",
)


# Reward commands

VIP_COMMANDS = env_commands("VIP_COMMANDS_JSON")
DIAMOND_COMMANDS = env_commands("DIAMOND_COMMANDS_JSON")
ULTIMATE_COMMANDS = env_commands("ULTIMATE_COMMANDS_JSON")


# Logging

CLAIM_LOG_CHANNEL_ID = env_int(
    "CLAIM_LOG_CHANNEL_ID"
)


# Database

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "data/sanity2x.db",
).strip()


def validate_config() -> None:
    missing: list[str] = []

    if not DISCORD_TOKEN:
        missing.append("DISCORD_TOKEN")

    if not GUILD_ID:
        missing.append("GUILD_ID")

    if not RCON_MOCK_COMMANDS:
        if not RCON_HOST:
            missing.append("RCON_HOST")

        if not RCON_PORT:
            missing.append("RCON_PORT")

        if not RCON_PASSWORD:
            missing.append("RCON_PASSWORD")

    cooldown_values = {
        "VIP_COOLDOWN_SECONDS": VIP_COOLDOWN_SECONDS,
        "DIAMOND_COOLDOWN_SECONDS": DIAMOND_COOLDOWN_SECONDS,
        "ULTIMATE_COOLDOWN_SECONDS": ULTIMATE_COOLDOWN_SECONDS,
        "OUTPOST_COOLDOWN_SECONDS": OUTPOST_COOLDOWN_SECONDS,
    }

    for name, value in cooldown_values.items():
        if value < 0:
            raise RuntimeError(
                f"{name} cannot be negative"
            )

    if OUTPOST_CONFIRM_SECONDS <= 0:
        raise RuntimeError(
            "OUTPOST_CONFIRM_SECONDS must be greater than 0"
        )

    if missing:
        raise RuntimeError(
            "Missing required variables: "
            + ", ".join(missing)
        )