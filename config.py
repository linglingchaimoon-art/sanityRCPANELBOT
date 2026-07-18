import json
import os

from dotenv import load_dotenv

load_dotenv(override=True)


def env_int(name: str, default: int = 0) -> int:
    value = os.getenv(name, str(default)).strip()
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {value!r}") from exc


def env_bool(name: str, default: bool = False) -> bool:
    fallback = "true" if default else "false"
    return os.getenv(name, fallback).strip().lower() in {"1", "true", "yes", "on"}


def env_id_set(name: str) -> set[int]:
    result: set[int] = set()

    for part in os.getenv(name, "").split(","):
        part = part.strip()

        if not part:
            continue

        try:
            result.add(int(part))
        except ValueError as exc:
            raise RuntimeError(f"{name} contains invalid ID {part!r}") from exc

    return result


def env_commands(name: str) -> list[str]:
    raw = os.getenv(name, "[]").strip()

    if not raw:
        return []

    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{name} contains invalid JSON.\nCurrent value: {raw!r}"
        ) from exc

    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RuntimeError(f"{name} must be a JSON list of strings")

    return value


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = env_int("GUILD_ID")

VIP_ROLE_ID = env_int("VIP_ROLE_ID")
DIAMOND_VIP_ROLE_ID = env_int("DIAMOND_VIP_ROLE_ID")
ULTIMATE_VIP_ROLE_ID = env_int("ULTIMATE_VIP_ROLE_ID")

STAFF_ROLE_IDS = env_id_set("STAFF_ROLE_IDS")
HR_ROLE_IDS = env_id_set("HR_ROLE_IDS")

LINKED_NICKNAME_PREFIX = os.getenv("LINKED_NICKNAME_PREFIX", "🔗").strip()

BOOSTER_CUSTOM_ROLE_ID = env_int("BOOSTER_CUSTOM_ROLE_ID")
BOOSTER_NICKNAME_PREFIX = os.getenv("BOOSTER_NICKNAME_PREFIX", "💎").strip()

LOA_ROLE_ID = env_int("LOA_ROLE_ID")
LOA_REVIEW_CHANNEL_ID = env_int("LOA_REVIEW_CHANNEL_ID")
LOA_LOG_CHANNEL_ID = env_int("LOA_LOG_CHANNEL_ID")

RCON_HOST = os.getenv("RCON_HOST", "127.0.0.1").strip()
RCON_PORT = env_int("RCON_PORT", 28016)
RCON_PASSWORD = os.getenv("RCON_PASSWORD", "test")
RCON_USE_SSL = env_bool("RCON_USE_SSL")
RCON_MOCK_COMMANDS = env_bool("RCON_MOCK_COMMANDS", True)
DEBUG_RCON_MESSAGES = env_bool("DEBUG_RCON_MESSAGES", True)

REWARD_COOLDOWN_SECONDS = env_int("REWARD_COOLDOWN_SECONDS", 86400)
CLAIM_LOG_CHANNEL_ID = env_int("CLAIM_LOG_CHANNEL_ID")

VIP_COMMANDS = env_commands("VIP_COMMANDS_JSON")
DIAMOND_COMMANDS = env_commands("DIAMOND_COMMANDS_JSON")
ULTIMATE_COMMANDS = env_commands("ULTIMATE_COMMANDS_JSON")

DATABASE_PATH = os.getenv("DATABASE_PATH", "data/sanity2x.db").strip()


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

    if missing:
        raise RuntimeError("Missing required variables: " + ", ".join(missing))
